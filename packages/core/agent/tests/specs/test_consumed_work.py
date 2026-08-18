"""Tests for `taiyi_core_agent.consumed_work` — the log fold."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from taiyi_core_agent.consumed_work import (
    ConsumedWork,
    accounts_for_claim,
    fold_consumed_work,
)

# ---------------------------------------------------------------------------
# accounts_for_claim
# ---------------------------------------------------------------------------


def test_accounts_for_claim_completed_returns_false() -> None:
    """A `completed` turn ending does NOT account for the input it took."""
    assert accounts_for_claim({"kind": "completed"}) is False


def test_accounts_for_claim_blocked_returns_true() -> None:
    """A `blocked` turn ending accounts for the input it took."""
    assert accounts_for_claim({"kind": "blocked"}) is True


def test_accounts_for_claim_aborted_returns_true() -> None:
    """An `aborted` turn ending accounts for the input it took."""
    assert accounts_for_claim({"kind": "aborted", "reason": {"kind": "user"}}) is True


def test_accounts_for_claim_interrupted_returns_true() -> None:
    """An `interrupted` turn ending accounts for the input it took."""
    assert accounts_for_claim({"kind": "interrupted"}) is True


def test_accounts_for_claim_error_returns_true() -> None:
    """An `error` turn ending accounts for the input it took."""
    assert accounts_for_claim({"kind": "error", "error": {"code": "x"}}) is True


def test_accounts_for_claim_unknown_kind_returns_true() -> None:
    """An unnameable kind defaults to ``True`` (safe default)."""
    assert accounts_for_claim({"kind": "exotic-addition"}) is True


def test_accounts_for_claim_non_mapping_returns_true() -> None:
    """A non-mapping reason defaults to ``True`` (defensive)."""
    assert accounts_for_claim("not a mapping")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# fold_consumed_work
# ---------------------------------------------------------------------------


def _event(event_type: str, data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"type": event_type, "data": dict(data or {})}


def test_fold_returns_no_end_and_not_dropped_for_empty_log() -> None:
    """Folding the empty log yields no accounting turn, no drop."""
    result = fold_consumed_work([])
    assert result == ConsumedWork(end=None, dropped_unrun=False)


def test_fold_returns_accounting_turn_after_step() -> None:
    """A `step/start` then `turn/end` produces an accounting turn."""
    events = [
        _event("turn/start", {"turn": 1}),
        _event("step/start", {"turn": 1}),
        _event("turn/end", {"turn": 1, "reason": {"kind": "completed"}}),
    ]
    result = fold_consumed_work(events)
    assert isinstance(result, ConsumedWork)
    assert result.end is not None
    assert result.end["type"] == "turn/end"
    assert result.dropped_unrun is False


def test_fold_claim_completed_turn_has_no_accounting() -> None:
    """A `completed` turn with a claim + no step has no accounting turn."""
    events = [
        _event("turn/start", {"turn": 2}),
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 2,
                "inserted": [],
            },
        ),
        _event("turn/end", {"turn": 2, "reason": {"kind": "completed"}}),
    ]
    result = fold_consumed_work(events)
    assert result.end is None
    assert result.dropped_unrun is False


def test_fold_claim_aborted_turn_has_accounting() -> None:
    """An `aborted` turn with a claim has an accounting turn."""
    events = [
        _event("turn/start", {"turn": 3}),
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "inserted": [],
            },
        ),
        _event(
            "turn/end",
            {"turn": 3, "reason": {"kind": "aborted", "reason": {"kind": "user"}}},
        ),
    ]
    result = fold_consumed_work(events)
    assert result.end is not None
    assert result.end["type"] == "turn/end"


def test_fold_canceled_without_insertion_marks_dropped_unrun() -> None:
    """A cancellation that drops messages marks ``dropped_unrun``."""
    events = [
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "outcome": "canceled",
                "inserted": [],
            },
        ),
    ]
    result = fold_consumed_work(events)
    assert result.dropped_unrun is True


def test_fold_canceled_with_replacement_does_not_drop() -> None:
    """A cancellation replaced by new insertions keeps the work alive."""
    events = [
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "outcome": "canceled",
                "inserted": [{"id": "new-msg"}],
            },
        ),
    ]
    result = fold_consumed_work(events)
    assert result.dropped_unrun is False


def test_fold_step_resets_dropped_unrun_after_turn_end() -> None:
    """An accounting turn end clears the dropped-after-it bookkeeping."""
    events = [
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "outcome": "canceled",
                "inserted": [],
            },
        ),
        _event("turn/start", {"turn": 9}),
        _event("step/start", {"turn": 9}),
        _event("turn/end", {"turn": 9, "reason": {"kind": "completed"}}),
    ]
    result = fold_consumed_work(events)
    assert result.dropped_unrun is False
    assert result.end is not None


def test_fold_multiple_turns_keeps_latest_accounting() -> None:
    """Only the latest closed accounting turn stays in the result."""
    events = [
        _event("turn/start", {"turn": 1}),
        _event("step/start", {"turn": 1}),
        _event("turn/end", {"turn": 1, "reason": {"kind": "completed"}}),
        _event("turn/start", {"turn": 2}),
        _event("step/start", {"turn": 2}),
        _event("turn/end", {"turn": 2, "reason": {"kind": "error", "error": {}}}),
    ]
    result = fold_consumed_work(events)
    assert result.end is not None
    assert result.end["data"]["turn"] == 2


def test_fold_unknown_event_types_are_skipped() -> None:
    """Non turn / step / inbox events pass through the fold."""
    events = [
        _event("user/message", {"id": "u1", "role": "user", "source": {"kind": "user"}, "content": []}),
        _event("tool/result", {"turn": 1, "step": 1, "message": {"id": "t1"}}),
    ]
    result = fold_consumed_work(events)
    assert result == ConsumedWork(end=None, dropped_unrun=False)


def test_fold_non_dict_events_are_skipped() -> None:
    """Non-dict events are tolerated by the fold."""
    events = ["not-an-event", None, 42]  # type: ignore[list-item]
    result = fold_consumed_work(events)  # type: ignore[arg-type]
    assert result == ConsumedWork(end=None, dropped_unrun=False)


def test_fold_inbox_event_without_open_turn_does_not_record_claim() -> None:
    """An inbox splice outside any turn does not contribute a claim."""
    events = [
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "inserted": [],
            },
        ),
    ]
    result = fold_consumed_work(events)
    assert result.end is None
    assert result.dropped_unrun is False


def test_fold_claim_inbox_event_no_removed_count_is_skipped() -> None:
    """A splice without ``removedCount`` is a pure insertion (no bookkeeping)."""
    events = [
        _event("turn/start", {"turn": 4}),
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "inserted": [{"id": "m1"}],
            },
        ),
        _event("turn/end", {"turn": 4, "reason": {"kind": "aborted", "reason": {"kind": "user"}}}),
    ]
    # No claim, no step → no accounting.
    result = fold_consumed_work(events)
    assert result.end is None


def test_fold_garbage_turn_data_does_not_break_log() -> None:
    """A `turn/end` with non-int turn / non-mapping reason is gracefully skipped."""
    events = [
        _event("turn/end", {"turn": "garbage", "reason": "garbage"}),
    ]
    result = fold_consumed_work(events)
    assert result == ConsumedWork(end=None, dropped_unrun=False)


def test_fold_uses_step_take_precedence_over_claim() -> None:
    """A turn with both a step and a claim accounts via step path first."""
    events = [
        _event("turn/start", {"turn": 5}),
        _event("step/start", {"turn": 5}),
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "inserted": [],
            },
        ),
        _event("turn/end", {"turn": 5, "reason": {"kind": "completed"}}),
    ]
    result = fold_consumed_work(events)
    assert result.end is not None
    # The step path consumed the bookkeeping; the result is `step/start`.
    assert result.end.get("data", {}).get("turn") == 5


def test_fold_claim_inbox_event_with_invalid_data() -> None:
    """An inbox splice with non-mapping data is skipped."""
    events = [
        _event("turn/start", {"turn": 6}),
        _event("agent/inbox/spliced", {"data": "not-a-mapping"}),
        _event("turn/end", {"turn": 6, "reason": {"kind": "completed"}}),
    ]
    result = fold_consumed_work(events)
    assert result.end is None


def test_fold_claim_with_no_open_turn_skips_claim() -> None:
    """An inbox splice outside any open turn does not contribute a claim."""
    events = [
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "inserted": [],
            },
        ),
    ]
    result = fold_consumed_work(events)
    assert result.dropped_unrun is False
    assert result.end is None


def test_fold_turn_end_with_garbage_data_continues() -> None:
    """A `turn/end` with garbage data flows past (no bookkeeping)."""
    events = [
        _event("turn/end", {"turn": 99, "reason": None}),
    ]
    result = fold_consumed_work(events)
    assert result == ConsumedWork(end=None, dropped_unrun=False)


def test_fold_without_turn_data_records_step() -> None:
    """A `step/start` with garbage turn data does not pollute bookkeeping."""
    events = [
        _event("turn/start", {"data": "garbage"}),
        _event("step/start", {"data": "garbage"}),
        _event(
            "turn/end",
            {
                "turn": 7,
                "reason": {"kind": "completed"},
            },
        ),
    ]
    result = fold_consumed_work(events)
    # The bookkeeping stays empty — no step / claim was attributed to `7`.
    assert result.end is None


def test_fold_inbox_no_removed_count_skips_removal_branch() -> None:
    """An inbox splice without ``removedCount`` exercises the early-return."""
    events = [
        _event("turn/start", {"turn": 8}),
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "inserted": [{"id": "m1"}],
            },
        ),
        _event("turn/end", {"turn": 8, "reason": {"kind": "completed"}}),
    ]
    result = fold_consumed_work(events)
    # Pure insertion does not register a claim.
    assert result.end is None
    assert result.dropped_unrun is False


def test_fold_inbox_cancellation_with_insertion_does_not_drop() -> None:
    """`outcome: canceled` AND inserted messages: replacement keeps the work."""

    events = [
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "outcome": "canceled",
                "inserted": [{"id": "m2"}],
            },
        ),
    ]
    result = fold_consumed_work(events)
    assert result.dropped_unrun is False


def test_fold_claim_taken_under_accounting_turn_paths() -> None:
    """The `turn in claimed and accounts_for_claim` branch is exercised."""
    events = [
        _event("turn/start", {"turn": 11}),
        _event(
            "agent/inbox/spliced",
            {
                "target": "next-step",
                "start": 0,
                "removedCount": 1,
                "inserted": [],
            },
        ),
        # ``accounts_for_claim`` returns True for `aborted`.
        _event(
            "turn/end",
            {
                "turn": 11,
                "reason": {"kind": "aborted", "reason": {"kind": "user"}},
            },
        ),
    ]
    result = fold_consumed_work(events)
    assert result.end is not None
    assert result.end["data"]["turn"] == 11
