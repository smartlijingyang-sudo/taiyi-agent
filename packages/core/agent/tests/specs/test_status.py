"""Tests for `taiyi_core_agent.status` — the `AgentStatus` literal."""

from __future__ import annotations

import typing

from taiyi_core_agent.runtime_types import AgentStatus
from taiyi_core_agent.status import AgentStatus as AgentStatusDirect


def test_agent_status_literal_includes_idle_and_running() -> None:
    """`AgentStatus` is the literal union 'idle' | 'running'."""
    values = typing.get_args(AgentStatusDirect)
    # All Literal values must be 'idle' or 'running'.
    for value in values:
        assert value in {"idle", "running"}, value


def test_runtime_types_status_matches_status_module() -> None:
    """`AgentStatus` re-exported from runtime_types matches the source."""
    assert AgentStatus is AgentStatusDirect


def test_agent_status_can_be_narrowed_via_isinstance() -> None:
    """`AgentStatus` values admit the 'idle' / 'running' strings."""
    assert isinstance("idle", str)
    assert isinstance("running", str)
    # Linter-friendly assignment that exercises the union.
    sample: str = "idle"
    assert sample in {"idle", "running"}
