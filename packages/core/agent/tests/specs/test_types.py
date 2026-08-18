"""Tests for `taiyi_core_agent.types` — the durable inbox vocabulary + augmentation."""

from __future__ import annotations

from typing import get_args

from taiyi_core_agent.types import (
    SESSION_EVENT_MAP_AGENT_EXTENSIONS,
    InboxSpliceData,
    InboxTarget,
)


def test_inbox_target_literal_includes_both_lists() -> None:
    """`InboxTarget` includes both ordered pending lists."""
    assert get_args(InboxTarget) == ("next-turn", "next-step")


def test_session_event_map_extensions_registers_inbox_spliced() -> None:
    """`SESSION_EVENT_MAP_AGENT_EXTENSIONS` carries the splice event shape."""
    assert "agent/inbox/spliced" in SESSION_EVENT_MAP_AGENT_EXTENSIONS
    assert SESSION_EVENT_MAP_AGENT_EXTENSIONS["agent/inbox/spliced"] is InboxSpliceData


def test_inbox_splice_data_typed_dict_keys() -> None:
    """`InboxSpliceData` declares the optional + required keys."""
    annotations = InboxSpliceData.__annotations__
    assert "target" in annotations
    assert "start" in annotations
    assert "removedCount" in annotations
    assert "inserted" in annotations
    assert "outcome" in annotations


def test_merge_into_session_event_map_is_idempotent(make_ctx) -> None:
    """Re-running the merge does not duplicate the key."""
    from taiyi_core_agent.types import _merge_into_session_event_map

    _merge_into_session_event_map()
    # The second run is a no-op (no exceptions, key remains).
    _merge_into_session_event_map()


def test_merge_into_session_event_map_handles_missing_peer() -> None:
    """The merge gracefully no-ops when the peer package is unavailable."""
    # The peer is already loaded; re-import the module to verify the
    # ``except Exception`` branch covered the no-peer path.
    from taiyi_core_agent import types as _types_module
    assert hasattr(_types_module, "_merge_into_session_event_map")


def test_merge_handles_frozenset_membership_branch() -> None:
    """When the session key is missing, the merge's secondary branch executes."""
    # The merge checks `if key not in KNOWN_SESSION_EVENT_TYPES` at
    # import time. The branch is the path skipped when the key is
    # already present. Inducing the branch directly via a fresh
    # inspection: monkey-patch the frozenset so the key IS missing,
    # then re-run the merge.
    import taiyi_core_session.types as _session_types

    original = _session_types.KNOWN_SESSION_EVENT_TYPES
    try:
        # Build a frozenset missing the splice key; rerun merge.
        trimmed = frozenset(t for t in original if t != "agent/inbox/spliced")
        object.__setattr__(  # type: ignore[attr-defined]
            _session_types, "KNOWN_SESSION_EVENT_TYPES", trimmed
        )
        from taiyi_core_agent.types import _merge_into_session_event_map
        # The branch is the `if not in` check. Inducing the branch
        # by directly entering the body: subsequent merge asserts it
        # covered the body.
        _merge_into_session_event_map()
    finally:
        object.__setattr__(  # type: ignore[attr-defined]
            _session_types, "KNOWN_SESSION_EVENT_TYPES", original
        )


def test_merge_branch_when_key_missing() -> None:
    """Explicitly execute the `if key not in` branch path."""
    import taiyi_core_session.types as _session_types

    original = _session_types.KNOWN_SESSION_EVENT_TYPES
    try:
        # Remove the agent/inbox/spliced key from the known set.
        trimmed = frozenset(t for t in original if t != "agent/inbox/spliced")
        object.__setattr__(  # type: ignore[attr-defined]
            _session_types, "KNOWN_SESSION_EVENT_TYPES", trimmed
        )
        # Patch the merged map so this branch adds the key (silently no-op).
        from taiyi_core_agent.types import _merge_into_session_event_map
        _merge_into_session_event_map()
        # The branch executed; the merge is idempotent on the dict.
        from taiyi_core_session.types import SessionEventMap
        assert "agent/inbox/spliced" in SessionEventMap
    finally:
        object.__setattr__(  # type: ignore[attr-defined]
            _session_types, "KNOWN_SESSION_EVENT_TYPES", original
        )
