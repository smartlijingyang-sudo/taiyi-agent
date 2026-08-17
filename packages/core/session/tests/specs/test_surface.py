"""1:1 tests for `taiyi_core_session.surface` (the type predicates)."""

from __future__ import annotations

import typing

from taiyi_core_session.surface import (
    ReplaceOpDict,
    SurfaceEventType,
    SurfaceIntent,
    SurfaceOp,
    is_surface_eligible_type,
    is_surface_op_append,
    is_surface_op_replace,
    make_replace_op,
)


def test_surface_event_type_literal_includes_three_types() -> None:
    args = set(typing.get_args(SurfaceEventType))
    assert args == {"user/message", "assistant/message", "tool/result"}


def test_surface_op_literal_includes_append_and_replace_dict() -> None:
    """`typing.get_args(SurfaceOp)` enumerates `Literal['append']` and the replace TypedDict."""
    args = typing.get_args(SurfaceOp)
    # First arg is the Literal 'append' (which itself contains 'append'); second is the ReplaceOpDict TypedDict.
    assert typing.get_args(args[0]) == ("append",)


def test_is_surface_eligible_type_for_message_types() -> None:
    assert is_surface_eligible_type("user/message") is True
    assert is_surface_eligible_type("assistant/message") is True
    assert is_surface_eligible_type("tool/result") is True


def test_is_surface_eligible_type_for_log_only_types() -> None:
    assert is_surface_eligible_type("turn/start") is False
    assert is_surface_eligible_type("assistant/chunk") is False
    assert is_surface_eligible_type("session/end-seed") is False


def test_make_replace_op_builds_correct_shape() -> None:
    op = make_replace_op(2, 5)
    assert op == {"op": "replace", "start": 2, "end": 5}


def test_make_replace_op_passes_replace_op_dict_type_check() -> None:
    """The constructed dict satisfies the ReplaceOpDict TypedDict shape."""
    op: ReplaceOpDict = make_replace_op(0, 0)
    assert op["op"] == "replace"
    assert op["start"] == 0
    assert op["end"] == 0


def test_is_surface_op_append() -> None:
    assert is_surface_op_append("append") is True
    assert is_surface_op_append({"op": "replace", "start": 0, "end": 0}) is False
    assert is_surface_op_append(None) is False


def test_is_surface_op_replace() -> None:
    """Loose predicate: any mapping whose `op` is `'replace'` counts."""
    assert is_surface_op_replace({"op": "replace", "start": 0, "end": 0}) is True
    assert is_surface_op_replace("append") is False
    assert is_surface_op_replace(None) is False
    # Wrong op value
    assert is_surface_op_replace({"op": "delete", "start": 0, "end": 0}) is False
    # Missing keys (loose predicate still says "is a replace op")
    assert is_surface_op_replace({"op": "replace", "start": 0}) is True


def test_surface_intent_with_surface_op_only() -> None:
    intent: SurfaceIntent = {"surfaceOp": "append"}
    assert intent["surfaceOp"] == "append"
    assert "sourceEventSeqs" not in intent


def test_surface_intent_with_both_fields() -> None:
    intent: SurfaceIntent = {
        "surfaceOp": {"op": "replace", "start": 1, "end": 3},
        "sourceEventSeqs": [0, 1, 2],
    }
    assert intent["surfaceOp"]["op"] == "replace"
    assert intent["sourceEventSeqs"] == [0, 1, 2]
