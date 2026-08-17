"""1:1 tests for `taiyi_core_session.types`."""

from __future__ import annotations

import pytest

from taiyi_core_session.session import (
    validate_restored_session_header,
    validate_session_header,
)
from taiyi_core_session.types import (
    KNOWN_SESSION_EVENT_TYPES,
    SessionEventMap,
    SessionEventType,
    SessionId,
    is_json_value,
    make_session_id,
)

# ---------------------------------------------------------------------------
# SessionId
# ---------------------------------------------------------------------------


def test_session_id_branding() -> None:
    """`SessionId` is a runtime string; the helper just returns a typed copy."""
    raw = "session-abc"
    id_ = make_session_id(raw)
    assert isinstance(id_, str)
    assert id_ == raw


def test_session_id_alias_passes_through() -> None:
    """Identity is by string equality (no extra wrapper object)."""
    id_a = make_session_id("session-abc")
    id_b = make_session_id("session-abc")
    assert id_a == id_b


# ---------------------------------------------------------------------------
# is_json_value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        1,
        -1,
        1.5,
        "",
        "x",
        [],
        [1, 2, 3],
        ["x", None, True],
        {},
        {"a": 1, "b": "c"},
        {"a": [1, 2], "b": {"c": "d"}},
        [[1, 2], [3, 4]],
        {"nested": [{"deep": True}]},
    ],
)
def test_is_json_value_accepts_json_safe_values(value: object) -> None:
    assert is_json_value(value) is True


@pytest.mark.parametrize(
    "value",
    [
        # Sets are not JSON.
        {1, 2},
        # Bytes are not JSON.
        b"abc",
        # Functions are not JSON.
        lambda: None,
        # Custom objects are not JSON.
        object(),
        # NaN / inf are not JSON-safe per upstream (allow_nan=False).
        float("nan"),
        float("inf"),
    ],
)
def test_is_json_value_rejects_non_json_safe_values(value: object) -> None:
    assert is_json_value(value) is False


def test_is_json_value_accepts_tuples_as_arrays() -> None:
    """Python json.dumps serializes tuples as JSON arrays."""
    assert is_json_value((1, 2)) is True


def test_is_json_value_accepts_non_string_key_dicts() -> None:
    """Python json.dumps stringifies non-string keys."""
    assert is_json_value({1: "x"}) is True


# ---------------------------------------------------------------------------
# SessionEventMap / KNOWN_SESSION_EVENT_TYPES
# ---------------------------------------------------------------------------


def test_known_session_event_types_has_44_entries() -> None:
    """44 distinct event types in the vocabulary."""
    assert len(KNOWN_SESSION_EVENT_TYPES) == 44


def test_known_session_event_types_is_frozenset() -> None:
    """The exported set is immutable (frozenset)."""
    assert isinstance(KNOWN_SESSION_EVENT_TYPES, frozenset)


def test_session_event_map_covers_all_known_types() -> None:
    """Every entry of KNOWN_SESSION_EVENT_TYPES appears in SessionEventMap."""
    for event_type in KNOWN_SESSION_EVENT_TYPES:
        assert event_type in SessionEventMap


def test_session_event_map_excludes_nonexistent() -> None:
    """An arbitrary string is not in the map."""
    assert "definitely/not/a/real/event" not in SessionEventMap


def test_session_event_type_literal_includes_all_44() -> None:
    """`typing.get_args(SessionEventType)` covers all 44 types exactly."""
    import typing

    args = set(typing.get_args(SessionEventType))
    assert args == set(KNOWN_SESSION_EVENT_TYPES)
    assert len(args) == 44


# ---------------------------------------------------------------------------
# validate_session_header
# ---------------------------------------------------------------------------


def _valid_header_kwargs(session_id: str) -> dict[str, object]:
    return {
        "version": 0,
        "id": session_id,
        "createdAt": 1700000000000,
    }


def test_validate_session_header_accepts_minimal() -> None:
    """A header with just version + id + createdAt passes."""
    header = validate_session_header(
        SessionId("session-abc"), _valid_header_kwargs("session-abc")
    )
    assert header["version"] == 0
    assert header["id"] == "session-abc"
    assert header["createdAt"] == 1700000000000


def test_validate_session_header_rejects_non_dict() -> None:
    for bad in (None, "string", 42, ["a"], (1, 2)):
        with pytest.raises(ValueError, match="plain JSON record"):
            validate_session_header(SessionId("s"), bad)


def test_validate_session_header_rejects_wrong_version() -> None:
    bad = _valid_header_kwargs("s")
    bad["version"] = 1
    with pytest.raises(ValueError, match="version must be 0"):
        validate_session_header(SessionId("s"), bad)


def test_validate_session_header_rejects_id_mismatch() -> None:
    bad = _valid_header_kwargs("alice")
    with pytest.raises(ValueError, match="does not match"):
        validate_session_header(SessionId("bob"), bad)


def test_validate_session_header_rejects_missing_created_at() -> None:
    bad = {"version": 0, "id": "s"}
    with pytest.raises(ValueError, match="createdAt"):
        validate_session_header(SessionId("s"), bad)


@pytest.mark.parametrize("bad_value", [-1, 1.5, "x", None, True, 2**53])
def test_validate_session_header_rejects_bad_created_at(bad_value: object) -> None:
    bad = {"version": 0, "id": "s", "createdAt": bad_value}
    with pytest.raises(ValueError, match="createdAt"):
        validate_session_header(SessionId("s"), bad)


def test_validate_session_header_rejects_relative_cwd() -> None:
    bad = _valid_header_kwargs("s")
    bad["cwd"] = "relative/path"
    with pytest.raises(ValueError, match="absolute path"):
        validate_session_header(SessionId("s"), bad)


def test_validate_session_header_accepts_absolute_cwd() -> None:
    h = _valid_header_kwargs("s")
    h["cwd"] = "/abs/path"
    out = validate_session_header(SessionId("s"), h)
    assert out["cwd"] == "/abs/path"


def test_validate_session_header_rejects_non_string_cwd() -> None:
    h = _valid_header_kwargs("s")
    h["cwd"] = 42
    with pytest.raises(ValueError, match="cwd must be a string"):
        validate_session_header(SessionId("s"), h)


def test_validate_session_header_rejects_non_string_parent_session() -> None:
    h = _valid_header_kwargs("s")
    h["parentSession"] = 42
    with pytest.raises(ValueError, match="parentSession must be a string"):
        validate_session_header(SessionId("s"), h)


@pytest.mark.parametrize("bad_value", [-1, 1.5, "x", None, True])
def test_validate_session_header_rejects_bad_seed_length(bad_value: object) -> None:
    h = _valid_header_kwargs("s")
    h["seedLength"] = bad_value
    with pytest.raises(ValueError, match="seedLength"):
        validate_session_header(SessionId("s"), h)


def test_validate_session_header_rejects_bad_origin() -> None:
    h = _valid_header_kwargs("s")
    h["origin"] = "user"
    with pytest.raises(ValueError, match="origin must be"):
        validate_session_header(SessionId("s"), h)


@pytest.mark.parametrize("bad_value", [-1, 1.5, "x", None, True])
def test_validate_session_header_rejects_bad_delegation_depth(bad_value: object) -> None:
    h = _valid_header_kwargs("s")
    h["delegationDepth"] = bad_value
    with pytest.raises(ValueError, match="delegationDepth"):
        validate_session_header(SessionId("s"), h)


def test_validate_session_header_rejects_non_string_agent_preset() -> None:
    h = _valid_header_kwargs("s")
    h["agentPreset"] = 42
    with pytest.raises(ValueError, match="agentPreset"):
        validate_session_header(SessionId("s"), h)


# ---------------------------------------------------------------------------
# validate_restored_session_header
# ---------------------------------------------------------------------------


def test_validate_restored_session_header_accepts_dict_instance() -> None:
    """A regular dict passes (Object.prototype-equivalent)."""
    payload = dict(_valid_header_kwargs("s"))
    out = validate_restored_session_header(SessionId("s"), payload)
    assert out["id"] == "s"


def test_validate_restored_session_header_rejects_arbitrary_class() -> None:
    class _NotDict:
        pass

    with pytest.raises(ValueError, match="plain JSON record"):
        validate_restored_session_header(SessionId("s"), _NotDict())
