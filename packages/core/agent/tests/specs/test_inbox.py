"""Tests for `taiyi_core_agent.inbox` — Inbox projection."""

from __future__ import annotations

from typing import Any

import pytest

from taiyi_core_agent.inbox import Inbox, InboxNotifications


class _FakeSession:
    """Minimal stand-in for the Session API the Inbox reads + writes.

    The upstream :class:`taiyi_core_session.session.Session` accepts
    ``id`` and a seed of events during construction. This stub models
    just the surface the Inbox reads (``events``, ``header``) and
    writes (``append``).
    """

    header: dict
    _log: list
    _publish_cb: Any

    def __init__(self, events: list | None = None, header: dict | None = None) -> None:
        self._log = list(events or [])
        self.header = dict(header or {})
        self.header.setdefault("seedLength", 0)

    @property
    def id(self) -> str:
        return "session-stub"

    @property
    def events(self) -> tuple:
        return tuple(self._log)

    def append(self, event_type: str, data: dict) -> dict:
        """Append a session event and notify + return the published event."""
        event = {
            "type": event_type,
            "seq": len(self._log),
            "time": 0,
            "data": dict(data),
        }
        self._log.append(event)
        return event


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_session(
    seed: list | None = None,
    header: dict | None = None,
) -> _FakeSession:
    return _FakeSession(seed, header)


def _notifications() -> tuple[InboxNotifications, list, list, list]:
    """Build a notifications triple plus the capture lists."""
    inserted: list = []
    discarded: list = []
    claimed: list = []

    def _inserted(message: Any) -> None:
        inserted.append(message)

    def _discarded(message: Any) -> None:
        discarded.append(message)

    def _claimed(message: Any, turn: int) -> None:
        claimed.append((message, turn))

    return InboxNotifications(
        inserted=_inserted,
        discarded=_discarded,
        claimed=_claimed,
    ), inserted, discarded, claimed


def _message(message_id: str = "m1") -> dict:
    return {"id": message_id, "role": "user", "source": {"kind": "user"}, "content": []}


# ---------------------------------------------------------------------------
# Construction + replay
# ---------------------------------------------------------------------------


def test_inbox_replays_existing_splices() -> None:
    """`Inbox.__init__` replays durable `agent/inbox/spliced` events."""
    splices = [
        {
            "type": "agent/inbox/spliced",
            "seq": 0,
            "time": 0,
            "data": {
                "target": "next-step",
                "start": 0,
                "removedCount": 0,
                "inserted": [_message("m-a")],
            },
        },
    ]
    session = _make_session(seed=splices)
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    assert inbox.next_step == [_message("m-a")]


def test_inbox_replay_raises_for_invalid_splice() -> None:
    """Invalid persisted splices raise ValueError on construction."""
    bad_splice = {
        "type": "agent/inbox/spliced",
        "seq": 0,
        "time": 0,
        "data": {"target": "next-step", "start": -1, "inserted": []},
    }
    session = _make_session(seed=[bad_splice])
    notifications, _, _, _ = _notifications()
    with pytest.raises(ValueError, match="invalid persisted inbox splice"):
        Inbox(session, notifications)


def test_inbox_replay_skips_non_splice_events() -> None:
    """Events with a different type are ignored during replay."""
    events = [
        {
            "type": "user/message",
            "seq": 0,
            "time": 0,
            "data": {"id": "u1", "role": "user", "source": {"kind": "user"}, "content": []},
        },
    ]
    session = _make_session(seed=events)
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    assert inbox.has_pending is False


# ---------------------------------------------------------------------------
# Read-only projections
# ---------------------------------------------------------------------------


def test_next_turn_and_next_step_start_empty() -> None:
    """A fresh inbox has no pending items."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    assert inbox.next_turn == []
    assert inbox.next_step == []
    assert inbox.has_pending is False


def test_has_pending_reflects_either_list() -> None:
    """`has_pending` is true if either list is non-empty."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("x"))
    assert inbox.has_pending is True


# ---------------------------------------------------------------------------
# Mutators
# ---------------------------------------------------------------------------


def test_append_records_durable_event() -> None:
    """`append(target, msg)` logs an `agent/inbox/spliced` and notifies `inserted`."""
    session = _make_session()
    notifications, inserted, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    msg = _message("a")
    inbox.append("next-turn", msg)
    assert session._log[-1]["type"] == "agent/inbox/spliced"
    assert inbox.next_turn[-1]["id"] == "a"
    assert inserted == [msg]


def test_prepend_inserts_at_zero_index() -> None:
    """`prepend` puts a message ahead of every existing item."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("b1"))
    inbox.prepend("next-turn", _message("b0"))
    ids = [msg["id"] for msg in inbox.next_turn]
    assert ids == ["b0", "b1"]


def test_remove_returns_true_and_notifies_discarded() -> None:
    """`remove(id)` returns True and notifies `discarded` when the id is pending."""
    session = _make_session()
    notifications, _, discarded, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("c1"))
    inbox.remove("c1")
    assert inbox.has_pending is False
    assert any(msg["id"] == "c1" for msg in discarded)


def test_remove_returns_false_for_unknown_id() -> None:
    """`remove(id)` returns False when the id is not pending."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    assert inbox.remove("missing") is False


def test_replace_with_distinct_identity_emits_inserted_and_discarded() -> None:
    """`replace` discards the old identity and inserts the new one."""
    session = _make_session()
    notifications, inserted, discarded, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("d1"))
    new = _message("d1-new")
    assert inbox.replace("d1", new) is True
    assert any(msg["id"] == "d1" for msg in discarded)
    assert inserted[-1]["id"] == "d1-new"


def test_replace_returns_false_for_unknown_id() -> None:
    """`replace` for a missing id returns False."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    assert inbox.replace("missing", _message("x")) is False


def test_replace_duplicate_id_raises() -> None:
    """Replacing into a list that already owns the new id's identity raises."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("e1"))
    inbox.append("next-turn", _message("e2"))
    with pytest.raises(ValueError, match="already pending"):
        inbox.replace("e1", _message("e2"))


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------


def test_claim_next_step_drains_step_list() -> None:
    """`claim('next-step', turn)` removes and returns the step list."""
    session = _make_session()
    notifications, _, _, claimed = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-step", _message("f1"))
    inbox.append("next-step", _message("f2"))
    claimed_batch = inbox.claim("next-step", turn=10)
    assert [m["id"] for m in claimed_batch] == ["f1", "f2"]
    assert inbox.next_step == []
    # Each claimed message gets a notification with the owning turn.
    assert [c[1] for c in claimed] == [10, 10]


def test_claim_next_turn_includes_one_queued_turn() -> None:
    """`claim('next-turn', turn)` drains step + one queued turn."""
    session = _make_session()
    notifications, _, _, claimed = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-step", _message("g-step"))
    inbox.append("next-turn", _message("g-turn"))
    claimed_batch = inbox.claim("next-turn", turn=11)
    ids = [m["id"] for m in claimed_batch]
    assert ids == ["g-step", "g-turn"]
    assert claimed == [
        ({**_message("g-step")}, 11),
        ({**_message("g-turn")}, 11),
    ]


def test_claim_with_empty_step_yields_one_turn() -> None:
    """With no step pending, `claim('next-turn', turn)` returns the turn only."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("h-turn"))
    claimed_batch = inbox.claim("next-turn", turn=12)
    assert [m["id"] for m in claimed_batch] == ["h-turn"]


# ---------------------------------------------------------------------------
# clear + splice
# ---------------------------------------------------------------------------


def test_clear_drains_step_then_turn() -> None:
    """`clear()` empties both pending lists, in step-before-turn order."""
    session = _make_session()
    notifications, _, discarded, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-step", _message("i1"))
    inbox.append("next-turn", _message("i2"))
    inbox.clear()
    assert inbox.has_pending is False
    assert len(discarded) == 2


def test_splice_with_normalize_start_negative() -> None:
    """Negative splice start counts from the tail, clamped to length."""
    session = _make_session()
    notifications, _, discarded, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-step", _message("j1"))
    inbox.append("next-step", _message("j2"))
    inbox.splice("next-step", -1, 0, [_message("j-new")])
    ids = [m["id"] for m in inbox.next_step]
    assert ids == ["j1", "j-new", "j2"]
    # No removal means no `discarded` notification.
    assert discarded == []


def test_splice_clamps_delete_count() -> None:
    """Over-large `deleteCount` is clamped to remaining length."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("k1"))
    inbox.splice("next-turn", 0, 99, [])
    assert inbox.has_pending is False


def test_splice_truncates_floats() -> None:
    """Float / stringified coordinates truncate like JS ``Math.trunc``."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("l1"))
    # 1.7 truncates to 1; -99 truncates to -99 → clamped to 0 (empty tail).
    inbox.splice("next-turn", 1.7, 0, [_message("l-new")])
    assert inbox.next_turn[0]["id"] == "l1"
    assert inbox.next_turn[1]["id"] == "l-new"


def test_splice_clamps_out_of_range_start_to_length() -> None:
    """`start > len` is clamped to ``len`` (no rejection) — mirrors ``Math.min``."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("m1"))
    # Start past length clamps to ``len`` — splice resolves as a pure insert.
    removed = inbox.splice("next-turn", 99, 0, [_message("m2")])
    assert removed == []
    assert [m["id"] for m in inbox.next_turn] == ["m1", "m2"]


def test_splice_clamps_negative_remove_count_to_zero() -> None:
    """A negative ``deleteCount`` clamps to 0 (no rejection) — mirrors ``Math.max``."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("n1"))
    removed = inbox.splice("next-turn", 0, -3, [_message("n2")])
    assert removed == []
    # Splice inserts [n2] before index 0, so ``n2`` lands before ``n1``.
    assert [m["id"] for m in inbox.next_turn] == ["n2", "n1"]


def test_splice_noop_returns_empty_removed_list() -> None:
    """A splice that deletes 0 and inserts 0 returns ``[]`` with no event appended."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("m1"))
    initial_event_count = len(session._log)
    removed = inbox.splice("next-turn", 0, 0, [])
    assert removed == []
    assert len(session._log) == initial_event_count


def test_splice_invalid_target_is_rejected() -> None:
    """Splices with unknown ``target`` raise ``invalid inbox splice``."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    with pytest.raises(ValueError, match="invalid inbox splice"):
        inbox._validate(
            {"target": "next-year", "start": 0, "inserted": []}
        )


def test_message_id_of_dict_with_string_key() -> None:
    """`_message_id_of` reads dict ``id``."""
    from taiyi_core_agent.inbox import _message_id_of
    assert _message_id_of({"id": "x"}) == "x"


def test_message_id_of_object_with_id_attribute() -> None:
    """An object exposing `.id` is keyed by that attribute."""

    class _Message:
        def __init__(self, ident: str) -> None:
            self.id = ident

    from taiyi_core_agent.inbox import _message_id_of
    assert _message_id_of(_Message("c1")) == "c1"


def test_inbox_notifications_optional_callbacks() -> None:
    """`InboxNotifications` constructed with no callbacks tolerates None."""
    from taiyi_core_agent.inbox import InboxNotifications

    notifs = InboxNotifications()
    notifs.inserted({"id": "x"})  # no-op, no exception
    notifs.discarded({"id": "x"})  # no-op
    notifs.claimed({"id": "x"}, 1)  # no-op


def test_message_id_of_returns_object_id_for_arbitrary_object() -> None:
    """An object without ``.id`` falls back to ``id()``."""
    from taiyi_core_agent.inbox import _message_id_of

    class _NoId:
        pass

    sentinel = _NoId()
    ident = _message_id_of(sentinel)
    assert ident == id(sentinel)


def test_locate_returns_none_for_unknown_id() -> None:
    """`Inbox._locate` returns None when the message id isn't pending."""
    session = _make_session()
    from taiyi_core_agent.inbox import Inbox as _Inbox
    inbox = _Inbox(session, _notifications()[0])
    assert inbox._locate("missing") is None


def test_locate_finds_message_in_next_step() -> None:
    """`Inbox._locate` finds the index in the right list."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-step", _message("find-me"))
    located = inbox._locate("find-me")
    assert located == ("next-step", 0)


def test_locate_finds_message_in_next_turn() -> None:
    """`Inbox._locate` finds the index in `next-turn`."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("turn-msg"))
    located = inbox._locate("turn-msg")
    assert located == ("next-turn", 0)


def test_mutate_truncate_returns_truncated_value() -> None:
    """`Inbox._mutate` truncates floats like JS's Math.trunc."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-step", _message("trunc-1"))
    inbox.append("next-step", _message("trunc-2"))
    # Float start (1.7) truncates to 1, effectively inserting at index 1.
    inbox.splice("next-step", 1.7, 0, [_message("trunc-3")])
    ids = [m["id"] for m in inbox.next_step]
    assert ids == ["trunc-1", "trunc-3", "trunc-2"]


def test_trunc_handles_string_value_as_none() -> None:
    """`_trunc` returns None for a value that cannot be coerced."""
    from taiyi_core_agent.inbox import _trunc
    assert _trunc("not-coercible") is None


def test_trunc_handles_int_value_returns_int() -> None:
    """`_trunc` returns the same int (covers the `return int(value)` path)."""
    from taiyi_core_agent.inbox import _trunc
    result = _trunc(7)
    assert result is not None
    assert isinstance(result, int)
    assert result == 7


def test_trunc_handles_float_value() -> None:
    """`_trunc` returns the int floor of a finite float."""
    from taiyi_core_agent.inbox import _trunc
    assert _trunc(3.7) == 3


def test_trunc_handles_object_value() -> None:
    """`_trunc` returns None for arbitrary objects."""

    class _Foo:
        pass

    from taiyi_core_agent.inbox import _trunc
    assert _trunc(_Foo()) is None


def test_message_id_of_dict_no_id_returns_object_id() -> None:
    """A dict with no `id` returns ``id(dict)`` as a stable fallback."""
    from taiyi_core_agent.inbox import _message_id_of
    sentinel = {"role": "user"}
    ident = _message_id_of(sentinel)
    assert ident == id(sentinel)


def test_mutate_neg_offset_branch() -> None:
    """`_mutate` with negative start computes offset = truncated start (positive)."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("n1"))
    inbox.append("next-turn", _message("n2"))
    # Negative start -1: offset = -1, actual_start = max(2 + -1, 0) = 1.
    inbox.splice("next-turn", -1, 0, [_message("n-neg")])
    ids = [m["id"] for m in inbox.next_turn]
    assert ids == ["n1", "n-neg", "n2"]


def test_mutate_truncated_start_branch() -> None:
    """`_mutate` takes the `offset = truncated_start` branch (non-NaN path)."""
    session = _make_session()
    notifications, _, _, _ = _notifications()
    inbox = Inbox(session, notifications)
    inbox.append("next-turn", _message("t1"))
    inbox.append("next-turn", _message("t2"))
    # Int start 1: offset = 1 (truncated_start is not None → branch).
    inbox.splice("next-turn", 1, 1, [_message("t-replace")])
    ids = [m["id"] for m in inbox.next_turn]
    assert ids == ["t1", "t-replace"]


def _make_session_typed() -> _FakeSession:  # type: ignore[name-defined]
    """Re-export so test annotations resolve."""
    return _make_session()
