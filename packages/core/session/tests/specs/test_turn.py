"""1:1 tests for `taiyi_core_session.turn`."""

from __future__ import annotations

import typing

from taiyi_core_session.turn import (
    SESSION_FORMAT_VERSION,
    AgentCancelCause,
    TurnEndAborted,
    TurnEndBlocked,
    TurnEndCompleted,
    TurnEndError,
    TurnEndInterrupted,
    TurnEndMaxTokens,
    TurnEndReason,
)


def test_session_format_version_is_zero() -> None:
    """The format version is pinned at 0 (pre-release)."""
    assert SESSION_FORMAT_VERSION == 0


def test_turn_end_reason_includes_all_variants() -> None:
    """`typing.get_args(TurnEndReason)` enumerates the 6 TypedDict variants, each carrying a distinct `kind`."""
    args = typing.get_args(TurnEndReason)
    kinds = {arg.__annotations__.get("kind") for arg in args}
    expected = {"completed", "aborted", "blocked", "error", "max-tokens", "interrupted"}
    assert kinds == expected
    assert len(args) == 6


def test_turn_end_reason_completed_payload() -> None:
    d: TurnEndCompleted = {"kind": "completed"}
    assert d["kind"] == "completed"


def test_turn_end_reason_aborted_payload() -> None:
    d: TurnEndAborted = {"kind": "aborted", "reason": {"kind": "user"}}
    assert d["kind"] == "aborted"
    assert d["reason"]["kind"] == "user"


def test_turn_end_reason_blocked_payload() -> None:
    d: TurnEndBlocked = {"kind": "blocked"}
    assert d["kind"] == "blocked"


def test_turn_end_reason_error_payload() -> None:
    d: TurnEndError = {"kind": "error", "error": {"code": "RATE_LIMIT"}}
    assert d["kind"] == "error"


def test_turn_end_reason_max_tokens_payload() -> None:
    d: TurnEndMaxTokens = {"kind": "max-tokens"}
    assert d["kind"] == "max-tokens"


def test_turn_end_reason_interrupted_payload() -> None:
    d: TurnEndInterrupted = {"kind": "interrupted"}
    assert d["kind"] == "interrupted"


def test_agent_cancel_cause_accepts_any_mapping() -> None:
    """AgentCancelCause is documented as a Mapping union; any mapping shape fits."""
    cause: AgentCancelCause = {"kind": "user"}
    assert cause["kind"] == "user"
    cause2: AgentCancelCause = {"kind": "hook", "reason": "pre-step veto"}
    assert cause2["reason"] == "pre-step veto"
