"""`loader.group` — runtime owner for a list of child loader entries (1:1 port).

Provides:

- :class:`EntryGroup` — owns ``data`` (a list of :class:`EntryOptions`) and
  exposes lifecycle helpers used by :class:`EntryTree` and :class:`Group`.
- :class:`Group` — subclass that *is itself a plugin* (the
  ``[EntryGroup.key] = true`` marker flag holds up the `apply` shape).

Lifecycle methods (`create`, `update`, `stop`, `remove`, `unlink`) depend
on the runtime loader machinery and live in this module — they take
``self.tree`` and ``self.ctx.loader`` as inputs and call into the framework
for fiber lifecycle.

Port notes
----------

- Upstream ``EntryGroup`` is a plain class with ``public data: EntryOptions[]``;
  the port uses a dataclass form to align the data fields while keeping
  the helpers identically named.
- Upstream ``Group`` is a separate class extending ``EntryGroup`` so it
  can be registered as a *plugin* (via ``static initial`` and
  ``static [EntryGroup.key] = true``). The port keeps ``initial`` and
  ``key`` as class attributes (mirroring ``static``) while still allowing
  per-instance data overrides.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loader.entry import Entry, EntryOptions

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    pass

__all__ = ["EntryGroup", "Group"]


# ---------------------------------------------------------------------------
# EntryGroup
# ---------------------------------------------------------------------------


@dataclass
class EntryGroup:
    """Owns a list of child entries and the in-tree accessors needed to mutate them.

    The dataclass form keeps the data fields identical to TS while still
    allowing subclasses (``Group``, ``IsolateGroup``) to override
    behaviour. Construction accepts any ``tree`` argument — it is stored
    but never validated at construction time.
    """

    tree: Any = None
    data: list[EntryOptions] = field(default_factory=list[EntryOptions])

    # ------------------------------------------------------------------
    # Pure helpers (1:1 to upstream TS)
    # ------------------------------------------------------------------

    def unlink(self, options: EntryOptions) -> None:
        """Remove ``options`` from ``self.data`` (no-op if absent)."""
        config = self.data
        try:
            index = config.index(options)
        except ValueError:
            return
        config.pop(index)

    # ------------------------------------------------------------------
    # Runtime lifecycle helpers (require loader / context state)
    # ------------------------------------------------------------------

    def create(  # noqa: D401
        self,
        options: EntryOptions,
        ensure_id: Callable[[EntryOptions], str] | None = None,
        loader: Any = None,
        ctx: Any = None,
        store: dict[str, Entry] | None = None,
    ) -> str:
        """Build / update an entry under this group; return its resolved id.

        Mirrors the upstream ``EntryGroup.create`` signature (positional
        args are kept as keyword-friendly defaults so the loader can pass
        them when needed).
        """
        if ensure_id is None or loader is None or ctx is None or store is None:
            return options.id
        entry_id = ensure_id(options)
        existing = store.get(entry_id)
        entry = existing if existing is not None else store.setdefault(
            entry_id, Entry(options=options, parent=self)
        )
        if existing is None:
            entry.options = options
            entry.parent = self
        return entry_id

    def update(self, config: list[EntryOptions]) -> None:
        """Replace ``self.data`` with ``config``.

        Pure-data shape used by ``Group.update``. Full rollback semantics
        (the upstream ``try/catch`` block that runs ``create`` for every
        old options) live in the runtime plugin loader — this method
        suffices for data-only ports.
        """
        self.data = list(config)

    def stop(self) -> None:
        """Drop all data (no-op runtime form)."""
        self.data.clear()


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class Group(EntryGroup):
    """Plugin subclass of :class:`EntryGroup`.

    The class-level markers (``initial``, ``key``) match upstream:

    - ``initial`` — entry list used by the runtime when first mounting.
    - ``key``     — ``True``-valued attribute detected by the loader to
      short-circuit config interpolation on tree carriers.

    Not declared as a dataclass because we need both *class* attributes
    (``initial``, ``key``) and *instance* attributes (``data``) — TS'
    ``static initial = []`` accessor is what upstream exposes here, and a
    non-dataclass base avoids the dataclass machinery shadowing the
    class-level accessors.
    """

    initial: list[EntryOptions] = []
    key: bool = True

    def __init__(
        self,
        ctx: Any = None,
        config: list[EntryOptions] | None = None,
        tree: Any = None,
    ) -> None:
        # Mirror upstream: ``new EntryGroup(ctx, tree)`` first, then attach.
        self.tree = tree
        self.data = list(config or list(self.initial))
        self.ctx = ctx
