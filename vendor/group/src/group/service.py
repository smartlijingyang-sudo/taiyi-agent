"""`taiyi-group.service` — Group service: transactional EntryGroup update with marker-key carrier.

1:1 Python port of `vendor/group` (3 LOC upstream) and the nested ``Group``
class defined in `vendor/loader/src/config/group.ts`. The upstream runtime
``Group`` extends ``EntryGroup`` from the loader; the Python ``cordis.loader``
already exposes an :class:`EntryGroup` dataclass used for serialization, so
this module layers the runtime mutation and transactional semantics on top
of it without coupling to the parallel-ported ``taiyi-loader``.

Public API
----------
- :class:`Group` — the nested-group service. Holds an :class:`EntryGroup`
  keyed by :data:`GROUP_MARKER` and a list of :class:`GroupEntry`.
- :class:`GroupEntry` — wraps a :class:`cordis.Entry` with optional async
  ``on_apply`` and ``on_dispose`` hooks used by the Group during
  transactional updates.
- :data:`GROUP_MARKER` — ``"cordis.group"``, the loader tree-carrier
  marker (1:1 with upstream ``Symbol.for('cordis.group')``).
- :func:`is_group_carrier`, :func:`carrier_key_of` — per-instance carrier
  detection helpers (mirroring ``vendor/scope`` semantics).
- :class:`GroupUpdateError` — surfaces a transactional update failure,
  optionally wrapping both the original failure and any rollback failures.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from cordis import Context, Entry, EntryGroup, Service

__all__ = [
    "Group",
    "GroupEntry",
    "GroupUpdateError",
    "GROUP_MARKER",
    "is_group_carrier",
    "carrier_key_of",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Marker key + carrier registry
# ---------------------------------------------------------------------------


# Mirror upstream ``Symbol.for('cordis.group')`` — the loader tree-carrier
# marker the loader uses to recognize a Group subtree (see upstream
# ``EntryGroup.key`` in `vendor/loader/src/config/group.ts`).
GROUP_MARKER: str = "cordis.group"


# Per-instance carrier keys. Keyed by ``id(group)`` so the Group does not
# need to opt into weak references just to keep the table tidy. Entries are
# added in :meth:`Group.__init__` and removed in :meth:`Group.dispose`.
_carrier_keys: dict[int, object] = {}


def is_group_carrier(value: object) -> bool:
    """Return True iff ``value`` is a registered Group carrier."""
    return isinstance(value, Group) and id(value) in _carrier_keys


def carrier_key_of(value: object) -> object | None:
    """Return the marker routing key for a Group carrier, else ``None``."""
    if not is_group_carrier(value):
        return None
    return _carrier_keys.get(id(value))


# ---------------------------------------------------------------------------
# GroupEntry — runtime wrapper around a cordis Entry.
# ---------------------------------------------------------------------------


@dataclass
class GroupEntry:
    """One entry owned by a Group (mirrors upstream loader ``Entry``).

    A :class:`GroupEntry` carries:

    - ``options`` — a :class:`cordis.Entry` (id, name, config, ...).
    - ``on_apply`` — optional async hook invoked when the Group installs the
      entry during :meth:`Group.update`. In real loader code this would
      create a Cordis fiber; tests use the hook to simulate creation and
      to inject failures for rollback coverage.
    - ``on_dispose`` — optional async hook invoked when the Group releases
      the entry during :meth:`Group.update` removal or :meth:`Group.dispose`.

    Both hooks default to no-ops. Id presence is enforced on ``options.id``
    by :meth:`Group.update` before apply runs (1:1 with upstream
    ``ensureId``).
    """

    options: Entry
    on_apply: Callable[[Entry], Awaitable[Any]] | None = None
    on_dispose: Callable[[Entry], Awaitable[Any]] | None = None

    async def apply(self) -> None:
        """Invoke the apply hook. No-op when no hook is set."""
        if self.on_apply is None:
            return
        result = self.on_apply(self.options)
        if asyncio.iscoroutine(result):
            await result

    async def dispose(self) -> None:
        """Invoke the dispose hook. No-op when no hook is set."""
        if self.on_dispose is None:
            return
        result = self.on_dispose(self.options)
        if asyncio.iscoroutine(result):
            await result


def _wrap(entry: Entry | GroupEntry) -> GroupEntry:
    """Coerce a raw Entry or existing GroupEntry into a GroupEntry."""
    if isinstance(entry, GroupEntry):
        return entry
    return GroupEntry(options=entry)


# ---------------------------------------------------------------------------
# Error type.
# ---------------------------------------------------------------------------


class GroupUpdateError(Exception):
    """A Group transactional update failed.

    Mirrors the upstream TS ``AggregateError`` path in
    ``EntryGroup.update``. ``original`` is the failure that triggered the
    rollback; ``rollback_errors`` contains any errors raised while trying
    to restore the previous state.
    """

    def __init__(
        self,
        original: BaseException,
        rollback_errors: Sequence[BaseException] = (),
    ) -> None:
        self.original: BaseException = original
        self.rollback_errors: list[BaseException] = list(rollback_errors)
        msg = f"group update failed: {type(original).__name__}: {original}"
        if self.rollback_errors:
            msg += f" (rollback errors: {len(self.rollback_errors)})"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Group Service.
# ---------------------------------------------------------------------------


def _normalize_id(options: Entry, seen: set[str]) -> str:
    """Return the entry id, raising on duplicates or missing ids."""
    entry_id = options.id
    if not entry_id:
        raise ValueError("group entry is missing required 'id'")
    if entry_id in seen:
        raise ValueError(f"duplicate loader entry id: {entry_id}")
    seen.add(entry_id)
    return entry_id


class Group(Service):
    """Nested plugin Group service (1:1 with vendor/group).

    Construction: ``Group(ctx, config=None, *, marker_key=None)``.

    - ``ctx`` — Cordis context; auto-registered for dispose.
    - ``config`` — initial list of :class:`cordis.Entry` or
      :class:`GroupEntry` instances. ``__init__`` does NOT apply it; call
      :meth:`update` explicitly. (See port decision #7 in the README.)
    - ``marker_key`` — optional explicit carrier routing key. Defaults to
      a UUID-4 string so two Groups never collide.

    Lifecycle:

    - :meth:`update` — transactional all-or-nothing multi-entry update
      with rollback on failure.
    - :meth:`dispose` — release every applied entry; deregister the
      carrier key (the base :class:`cordis.Service` wires this into
      ``ctx.dispose``).
    """

    MARKER: str = GROUP_MARKER
    """Tree-carrier marker (1:1 with upstream ``EntryGroup.key``)."""

    def __init__(
        self,
        ctx: Context,
        config: Sequence[Entry | GroupEntry] | None = None,
        *,
        marker_key: object | None = None,
    ) -> None:
        super().__init__(ctx)
        self.ctx: Context = ctx
        # Per-instance routing key: a distinct marker per Group. When the
        # caller doesn't supply one, mint a UUID string; UUID4 never
        # collides inside a process.
        self._marker_key: object = marker_key if marker_key is not None else uuid.uuid4().hex
        # Public EntryGroup reference (the dataclass form used by the
        # loader/invariant). The runtime list of entries lives below.
        self.entry_group: EntryGroup = EntryGroup(key=self.MARKER)
        # The currently applied entries.
        self._entries: list[GroupEntry] = []
        # Dispose flag mirrors the cordis Service.dispose idempotency.
        self._disposed: bool = False
        # Stash the initial config so callers can fetch it later if needed.
        self._initial_raw: list[GroupEntry] = [_wrap(e) for e in (config or [])]
        # Register as a scope carrier so is_group_carrier() identifies us.
        _carrier_keys[id(self)] = self._marker_key

    # ------------------------------------------------------------------
    # Accessors.
    # ------------------------------------------------------------------

    @property
    def marker_key(self) -> object:
        """The per-instance carrier routing key (distinct per Group)."""
        return self._marker_key

    @property
    def entries(self) -> list[GroupEntry]:
        """A snapshot of currently applied entries (defensive copy)."""
        return list(self._entries)

    @property
    def is_disposed(self) -> bool:
        """Whether :meth:`dispose` has run (entries released)."""
        return self._disposed

    # ------------------------------------------------------------------
    # Transactional update.
    # ------------------------------------------------------------------

    async def update(self, config: Sequence[Entry | GroupEntry]) -> None:
        """Apply ``config`` transactionally; rollback on any failure.

        Mirrors upstream ``EntryGroup.update``:

        1. Validate uniqueness of incoming entry ids (raises ``ValueError``
           on duplicates, matching upstream ``TypeError``).
        2. Build old/new maps keyed by id.
        3. Apply every new entry via ``asyncio.gather(..., return_exceptions=True)``
           (the asyncio analog of ``Promise.allSettled``).
        4. Inspect outcomes: if any apply failed, roll back.
        5. On success, dispose entries present in old but absent from new.
        6. Replace ``_entries`` with the new snapshot only after step 5
           completes.
        """
        # Step 1 — normalize & dedupe ids.
        seen: set[str] = set()
        new_entries: list[GroupEntry] = []
        for raw in config:
            entry = _wrap(raw)
            _normalize_id(entry.options, seen)
            new_entries.append(entry)

        new_map: dict[str, GroupEntry] = {e.options.id: e for e in new_entries}
        old_entries: list[GroupEntry] = list(self._entries)
        old_map: dict[str, GroupEntry] = {e.options.id: e for e in old_entries}

        # Step 2 — apply all new entries in parallel.
        outcomes: list[BaseException | None] = await asyncio.gather(
            *(self._apply(entry) for entry in new_entries),
            return_exceptions=True,
        )

        # Step 3 — collect apply failures.
        apply_errors: list[BaseException] = [
            outcome for outcome in outcomes if isinstance(outcome, BaseException)
        ]

        if apply_errors:
            # Step 3a — rollback and re-raise the update error. ``_rollback``
            # mutates ``self._entries`` back to the prior snapshot then
            # returns the ``GroupUpdateError`` to raise here; we keep the
            # raise in ``update`` so the rollback path is reachable from
            # the caller's frame.
            original = apply_errors[0]
            rollback = await self._rollback(new_map, old_map, old_entries, original)
            raise rollback from original

        # Step 4 — success path: dispose old entries not in new.
        for entry_id, entry in old_map.items():
            if entry_id in new_map:
                continue
            try:
                await self._safe_dispose(entry)
            except Exception as exc:  # noqa: BLE001 — propagate as update error
                # Match upstream semantics: dispose-time failure during a
                # successful update IS a real failure; rollback the
                # half-applied state.
                logger.warning(
                    "Group.update: dispose of stale entry %r raised %s: %s",
                    entry_id,
                    type(exc).__name__,
                    exc,
                )
                rollback = await self._rollback(
                    new_map,
                    old_map,
                    old_entries,
                    exc,
                    skip_dispose_already_applied=False,
                )
                raise rollback from exc

        self._entries = new_entries

    async def _apply(self, entry: GroupEntry) -> None:
        """Apply a single entry; let exceptions propagate to the gather."""
        await entry.apply()

    async def _safe_dispose(self, entry: GroupEntry) -> None:
        """Invoke ``entry.dispose`` swallowing exceptions into GroupUpdateError scope.

        Called from the success-path remove step; rollback reuses the same
        helper.
        """
        await entry.dispose()

    async def _rollback(
        self,
        new_map: dict[str, GroupEntry],
        old_map: dict[str, GroupEntry],
        old_entries: list[GroupEntry],
        original: BaseException,
        *,
        skip_dispose_already_applied: bool = True,
    ) -> GroupUpdateError:
        """Restore the previous state and return a :class:`GroupUpdateError`.

        Rollback order (1:1 with upstream):

        1. Reverse-order dispose of newly-created entries whose ids are NOT
           in the old set (i.e., entries that did not pre-exist).
        2. Re-apply every entry in the previous snapshot.

        The returned error wraps the original failure plus any rollback
        failures collected along the way. Callers re-raise the returned
        object so the exception is raised from ``update`` (avoids the
        unreachable ``raise`` after an always-raising awaited call).
        """
        rollback_errors: list[BaseException] = []

        # Step 1 — dispose newly-created (not-in-old) entries, reverse order.
        for entry_id in reversed(list(new_map.keys())):
            if entry_id in old_map:
                continue
            entry = new_map[entry_id]
            try:
                await self._safe_dispose(entry)
            except BaseException as exc:  # noqa: BLE001
                rollback_errors.append(exc)

        # Step 2 — re-apply old entries in order.
        for entry in old_entries:
            try:
                await self._apply(entry)
            except BaseException as exc:  # noqa: BLE001
                rollback_errors.append(exc)

        # Restore internal state to old snapshot regardless of rollback success.
        self._entries = old_entries

        if rollback_errors:
            return GroupUpdateError(original, rollback_errors)
        return GroupUpdateError(original)

    # ------------------------------------------------------------------
    # Disposal.
    # ------------------------------------------------------------------

    async def dispose(self) -> None:
        """Release every entry and deregister the carrier key.

        The base :class:`cordis.Service` already routes ``ctx.dispose``
        here; we only handle the Group-local cleanup. Idempotent.
        """
        if self._disposed:
            return
        self._disposed = True
        for entry in self._entries:
            try:
                await entry.dispose()
            except Exception as exc:  # noqa: BLE001 — defensive dispose
                logger.warning(
                    "Group.dispose: entry %r raised %s: %s",
                    entry.options.id,
                    type(exc).__name__,
                    exc,
                )
        self._entries.clear()
        _carrier_keys.pop(id(self), None)
