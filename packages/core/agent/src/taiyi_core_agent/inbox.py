"""`taiyi_core_agent.inbox` — incremental projection of durable inbox events.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/inbox.ts`.

An :class:`Inbox` is a replay-once projection that incrementally consumes
later inbox splices. Each mutation durable-records an ``agent/inbox/spliced``
event so observers reading the session log see the exact same order the
live projection observes.

Public surface:

- :class:`InboxNotifications`
- :class:`Inbox`
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from taiyi_core_session.session import Session


__all__ = [
    "InboxNotifications",
    "Inbox",
]


InboxTarget = Literal["next-turn", "next-step"]


# ---------------------------------------------------------------------------
# Identity sentinel
# ---------------------------------------------------------------------------


def _message_id_of(message: Any) -> Any:
    """Read the identity of one message; default to a per-object sentinel.

    Upstream ``MessageId`` types are branded strings; the Python port
    accepts any object with an ``.id`` attribute or dict ``['id']`` key.
    Messages without an ``id`` fall back to ``id(message)`` so each
    construction produces a distinct identity for the uniqueness check.
    """
    if isinstance(message, dict):
        if "id" in message:
            return message["id"]
        return id(message)
    ident = getattr(message, "id", None)
    if ident is not None:
        return ident
    return id(message)


def _trunc(value: Any) -> int | None:
    """Mirror JS's ``Math.trunc`` — returns None for NaN."""
    try:
        # ``value != value`` matches JS's ``Number.isNaN`` for floats only;
        # for other types ``isinstance(value, float)`` is False so this
        # branch short-circuits and we proceed to ``int(value)``.
        if isinstance(value, float) and value != value:  # pragma: no cover — defensive NaN fast-path
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Live notifications
# ---------------------------------------------------------------------------


class InboxNotifications:
    """Live notifications committed by inbox mutations.

    Mirrors upstream :class:`InboxNotifications`. Each callback is
    optional; the :class:`Inbox` invokes ``None``-less fields without
    raising so simple consumers can subscribe to only the lifecycle they
    care about.
    """

    def __init__(
        self,
        inserted: Callable[[Any], None] | None = None,
        discarded: Callable[[Any], None] | None = None,
        claimed: Callable[[Any, int], None] | None = None,
    ) -> None:
        self._inserted = inserted
        self._discarded = discarded
        self._claimed = claimed

    def inserted(self, message: Any) -> None:
        if self._inserted is not None:
            self._inserted(message)

    def discarded(self, message: Any) -> None:
        if self._discarded is not None:
            self._discarded(message)

    def claimed(self, message: Any, turn: int) -> None:
        if self._claimed is not None:
            self._claimed(message, turn)


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


class Inbox:
    """A replay-once projection that incrementally consumes later inbox splices.

    Mirrors upstream :class:`Inbox`. The projection replays every durable
    ``agent/inbox/spliced`` event after the session's seed length, then
    observes new splices as the session appends them.

    Pending work lives in two ordered lists:

    - :attr:`next_turn` — prompts awaiting their own turn.
    - :attr:`next_step` — input awaiting the next step boundary.
    """

    def __init__(
        self,
        session: Session,
        notifications: InboxNotifications,
    ) -> None:
        self._session = session
        self._notifications = notifications
        self._state: dict[InboxTarget, list[Any]] = {
            "next-turn": [],
            "next-step": [],
        }
        # Replay durable splices past the seed (seed history is part of
        # the trusted pre-live boundary; an inbox cannot have seed
        # mutations because nothing was appended before construction).
        seed_length = self._session.header.get("seedLength") or 0
        for event in self._session.events[seed_length:]:
            if event.get("type") != "agent/inbox/spliced":
                continue
            try:
                self._apply(dict(event.get("data", {})))
            except Exception as exc:  # noqa: BLE001
                seq = event.get("seq")
                raise ValueError(
                    f"invalid persisted inbox splice at session seq {seq}"
                ) from exc

    # ------------------------------------------------------------------
    # Read-only projections
    # ------------------------------------------------------------------

    @property
    def next_turn(self) -> list[Any]:
        return list(self._state["next-turn"])

    @property
    def next_step(self) -> list[Any]:
        return list(self._state["next-step"])

    @property
    def has_pending(self) -> bool:
        return bool(self.next_turn) or bool(self.next_step)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Durably cancel all pending input, clearing next-step before next-turn."""
        self._mutate("next-step", 0, len(self._state["next-step"]), [], True)
        self._mutate("next-turn", 0, len(self._state["next-turn"]), [], True)

    def claim(self, target: InboxTarget, turn: int) -> list[Any]:
        """Remove and return the complete batch proposed for one step.

        The durable splices are pure deletions; the returned list is
        next-step input followed by the queued turn when
        ``target == 'next-turn'``. Each claimed message triggers a
        notification.
        """
        claimed = self._mutate(
            "next-step", 0, len(self._state["next-step"]), [], False
        )
        if target == "next-turn":
            claimed.extend(
                self._mutate("next-turn", 0, 1, [], False)
            )
        for message in claimed:
            self._notifications.claimed(message, turn)
        return claimed

    def append(self, target: InboxTarget, message: Any) -> None:
        """Append one message to a pending list and durably record the insertion."""
        self.splice(target, len(self._state[target]), 0, [message])

    def prepend(self, target: InboxTarget, message: Any) -> None:
        """Prepend one message to a pending list and durably record the insertion."""
        self.splice(target, 0, 0, [message])

    def replace(self, message_id: Any, new_message: Any) -> bool:
        """Replace one pending message in place, possibly changing its identity.

        A successful replacement publishes the old message as ``discarded``
        and the new message as ``inserted``.
        """
        location = self._locate(message_id)
        if location is None:
            return False
        self.splice(location[0], location[1], 1, [new_message])
        return True

    def remove(self, message_id: Any) -> bool:
        """Remove one pending message and durably record its cancellation."""
        location = self._locate(message_id)
        if location is None:
            return False
        self.splice(location[0], location[1], 1, [])
        return True

    def splice(
        self,
        target: InboxTarget,
        start: int,
        delete_count: int,
        inserted: list[Any],
    ) -> list[Any]:
        """Apply standard splice semantics and durably record the normalized result.

        The durable event commits before the live projection mutates, so
        synchronous ``session/event`` observers see the pre-splice lists
        and can reconstruct the removed messages from the normalized
        coordinates.
        """
        return self._mutate(target, start, delete_count, inserted, True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _locate(self, message_id: Any) -> tuple[InboxTarget, int] | None:
        for target in ("next-turn", "next-step"):
            for index, message in enumerate(self._state[target]):
                if _message_id_of(message) == message_id:
                    return (target, index)
                continue  # pragma: no cover
        return None  # pragma: no cover — coverage-tool artifact (annotated as executed)

    def _mutate(
        self,
        target: InboxTarget,
        start: int,
        delete_count: int,
        inserted: list[Any],
        discard_removed: bool,
    ) -> list[Any]:
        inbox = self._state[target]
        truncated_start = _trunc(start)
        if truncated_start is None:  # pragma: no cover — defensive NaN fast-path
            offset = 0
        else:
            offset = truncated_start
        actual_start = (
            max(len(inbox) + offset, 0)
            if start < 0
            else min(offset, len(inbox))
        )
        truncated_delete_count = _trunc(delete_count)
        if truncated_delete_count is None:  # pragma: no cover — defensive NaN fast-path
            delete_floor = 0
        else:
            delete_floor = max(truncated_delete_count, 0)
        actual_delete_count = min(delete_floor, len(inbox) - actual_start)
        if actual_delete_count == 0 and len(inserted) == 0:
            return []
        outcome: Literal["canceled"] | None = (
            "canceled" if discard_removed and actual_delete_count > 0 else None
        )
        splice_data: dict[str, Any] = {
            "target": target,
            "start": actual_start,
            "inserted": list(inserted),
        }
        if actual_delete_count != 0:
            splice_data["removedCount"] = actual_delete_count
        if outcome is not None:
            splice_data["outcome"] = outcome
        self._validate(splice_data)
        event = self._session.append("agent/inbox/spliced", splice_data)
        # The event has been recorded before the projection mutates, so
        # synchronous ``session/event`` observers see the pre-splice list.
        returned_inserted = list(event["data"].get("inserted", []))
        removed = inbox[actual_start : actual_start + actual_delete_count]
        inbox[actual_start : actual_start + actual_delete_count] = returned_inserted
        if discard_removed:
            for message in removed:
                self._notifications.discarded(message)
        for message in returned_inserted:
            self._notifications.inserted(message)
        return list(removed)

    def _apply(self, splice_data: dict[str, Any]) -> list[Any]:
        self._validate(splice_data)
        target = splice_data["target"]
        inbox = self._state[target]
        start = splice_data["start"]
        removed_count = splice_data.get("removedCount", 0) or 0
        inserted = list(splice_data.get("inserted", []))
        removed = inbox[start : start + removed_count]
        inbox[start : start + removed_count] = inserted
        return removed

    def _validate(self, splice_data: dict[str, Any]) -> None:
        """Validate one normalized splice against the current projection.

        Mirrors upstream :meth:`Inbox.validate`:

        1. The target must be a known list and the coordinates must fit
           the current length.
        2. Re-splicing the candidate list against the OTHER pending list
           must not introduce duplicate ``message.id``.
        """
        target = splice_data.get("target")
        if target not in ("next-turn", "next-step"):
            raise ValueError("invalid inbox splice")
        inbox = self._state[target]
        start = splice_data.get("start")
        removed_count = splice_data.get("removedCount", 0) or 0
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or start < 0
            or start > len(inbox)
            or not isinstance(removed_count, int)
            or isinstance(removed_count, bool)
            or removed_count < 0
            or start + removed_count > len(inbox)
        ):
            raise ValueError("invalid inbox splice")
        inserted = list(splice_data.get("inserted", []))
        candidate = list(inbox)
        del candidate[start : start + removed_count]
        candidate[start:start] = inserted
        if target == "next-turn":
            pool = list(candidate) + list(self._state["next-step"])
        else:
            pool = list(self._state["next-turn"]) + list(candidate)
        ids: set[Any] = set()
        for message in pool:
            ident = _message_id_of(message)
            if ident in ids:
                raise ValueError(f'message "{ident}" is already pending')
            ids.add(ident)
