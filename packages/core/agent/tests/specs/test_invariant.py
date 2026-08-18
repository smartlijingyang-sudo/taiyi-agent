"""Tests for `taiyi_core_agent.invariant` — the agent/status no-op detector."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from taiyi_core_agent.invariant import apply


def _make_agent(agent_id: str = "a1") -> Any:
    return type("_AgentStub", (), {"id": agent_id})()


def test_invariant_apply_registers_listener(make_ctx) -> None:
    """`apply(ctx)` registers an `agent/status` listener."""
    apply(make_ctx)
    hooks = make_ctx.events._hooks  # type: ignore[attr-defined]
    assert "agent/status" in hooks
    assert len(hooks["agent/status"]) >= 1


def test_invariant_no_op_transition_succeeds_first_time(make_ctx) -> None:
    """The first emit of a status is fine."""
    apply(make_ctx)
    agent = _make_agent()
    listener = make_ctx.events._hooks["agent/status"][0].callback  # type: ignore[attr-defined]
    # Should not raise on the first transition.
    listener({"agent": agent, "status": "idle"})


def test_invariant_repeats_throws_via_listener(make_ctx) -> None:
    """A repeated status throws via the listener path."""
    apply(make_ctx)
    agent = _make_agent()
    listener = make_ctx.events._hooks["agent/status"][0].callback  # type: ignore[attr-defined]
    listener({"agent": agent, "status": "running"})
    # Second transition to the same status must throw.
    with pytest.raises(RuntimeError, match="agent/status repeated"):
        listener({"agent": agent, "status": "running"})


def test_invariant_opposite_transition_allowed(make_ctx) -> None:
    """`idle` -> `running` -> `idle` is allowed."""
    apply(make_ctx)
    agent = _make_agent()
    listener = make_ctx.events._hooks["agent/status"][0].callback  # type: ignore[attr-defined]
    listener({"agent": agent, "status": "idle"})
    listener({"agent": agent, "status": "running"})
    listener({"agent": agent, "status": "idle"})


def test_invariant_payload_without_agent_noop(make_ctx) -> None:
    """A status emit without `agent` is silently ignored."""
    apply(make_ctx)
    listener = make_ctx.events._hooks["agent/status"][0].callback  # type: ignore[attr-defined]
    listener({"status": "running"})


def test_invariant_apply_with_invariants_service(make_ctx) -> None:
    """When ``ctx.invariants`` is present, the registration goes through it."""

    registrations: list[tuple[str, Any]] = []

    def _noop_fail(_msg: str) -> None:
        pass

    def _noop_disposer() -> None:
        return None

    class _InvReg:
        def register(self, package_name: str, installer: Any) -> Callable[[], None]:
            registrations.append((package_name, installer))
            installer(make_ctx, _noop_fail)
            return _noop_disposer

    make_ctx.invariants = _InvReg()  # type: ignore[attr-defined]
    result = apply(make_ctx)
    assert registrations and registrations[0][0] == "@deepseek-ai/dsh-agent"
    assert callable(result)


def test_invariant_apply_handles_runtime_error(make_ctx) -> None:
    """When the accessor is already declared, the inner `RuntimeError` is caught."""

    def _noop_disposer() -> None:
        return None

    class _ReflectService:
        def __init__(self) -> None:
            self.provides: list[Any] = []
            self.accessors_declared = 0

        def provide(self, key: str, value: Any) -> Callable[[], None]:
            self.provides.append((key, value))
            return _noop_disposer

        def accessor(self, key: str, opts: dict) -> Callable[[], None]:
            self.accessors_declared += 1
            # First call: RuntimeError (already declared).
            if self.accessors_declared == 1:
                raise RuntimeError("already declared")
            return _noop_disposer

    make_ctx.reflect = _ReflectService()  # type: ignore[attr-defined]
    apply(make_ctx)  # must not raise
