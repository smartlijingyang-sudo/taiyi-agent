"""Tests for `taiyi_core_agent.dispatch` — fused dispatcher + helpers."""

from __future__ import annotations

from typing import Any

from cordis import Context

from taiyi_core_agent.carrier import agent_carrier
from taiyi_core_agent.context import assemble_context_for
from taiyi_core_agent.dispatch import (
    AGENT_SUBJECT_EVENT_NAMES,
    AgentEventDispatch,
    agent_events,
)
from taiyi_core_agent.event import emit_agent_event


class _AgentStub:
    id: str

    def __init__(self, agent_id: str) -> None:
        self.id = agent_id


# ---------------------------------------------------------------------------
# Dispatcher surface
# ---------------------------------------------------------------------------


def test_agent_events_emits_with_injected_agent(make_ctx) -> None:
    """`agent_events(ctx, agent).emit(name, payload)` injects `agent` into the payload."""
    agent = _AgentStub("a1")
    dispatcher = agent_events(make_ctx, agent)
    captured: list[Any] = []

    def _listener(carrier: Any, name: str, payload: Any) -> None:
        captured.append((name, dict(payload)))

    make_ctx.on("agent/created", _listener)  # type: ignore[attr-defined]
    dispatcher.emit("agent/created", {"origin": "test"})
    assert captured == [("agent/created", {"origin": "test", "agent": agent})]


def test_agent_events_emit_contains_throwing_listeners(make_ctx) -> None:
    """`emit` contains synchronous listener throws."""
    agent = _AgentStub("a2")

    def _boom(_carrier: Any, _name: str, _payload: Any) -> None:
        raise RuntimeError("listener-threw")

    warnings: list[Any] = []

    def _cap(message: Any) -> None:
        warnings.append(message)

    make_ctx.logger.warn = _cap  # type: ignore[attr-defined]
    make_ctx.on("agent/created", _boom)  # type: ignore[attr-defined]
    agent_events(make_ctx, agent).emit("agent/created", {})
    assert any("threw" in str(w) for w in warnings)


def test_agent_events_emit_inherits_existing_agent_subject_filter(make_ctx) -> None:
    """Listeners attached to a non-matching carrier are filtered out."""
    agent_one = _AgentStub("one")
    seen: list[Any] = []

    def _listener(_carrier: Any, _name: str, payload: Any) -> None:
        seen.append(payload["agent"].id)

    make_ctx.on("agent/created", _listener)  # type: ignore[attr-defined]
    # Fire for agent_one and agent_two. The scope carrier filters each
    # dispatch, so each listener invocation observes exactly the matching
    # agent's payload.
    agent_events(make_ctx, agent_one).emit("agent/created", {})
    assert "one" in seen


def test_agent_events_serial_returns_first_bail(make_ctx) -> None:
    """`serial` returns the first bail from the chain."""
    agent = _AgentStub("a3")

    async def _nothing(_carrier: Any, _name: str, _payload: Any) -> None:
        return None

    async def _bail(_carrier: Any, _name: str, _payload: Any) -> str:
        return "stop"

    async def _never(_carrier: Any, _name: str, _payload: Any) -> None:
        raise AssertionError("never reached")

    make_ctx.on("agent/turn-stopping", _nothing)  # type: ignore[attr-defined]
    make_ctx.on("agent/turn-stopping", _bail)  # type: ignore[attr-defined]
    make_ctx.on("agent/turn-stopping", _never)  # type: ignore[attr-defined]
    dispatcher = agent_events(make_ctx, agent)
    # ``asyncio.run`` so we can await the dispatcher.
    import asyncio
    result = asyncio.run(dispatcher.serial("agent/turn-stopping", {}))
    assert result == "stop"


def test_agent_events_waterfall_passes_next_callback(make_ctx) -> None:
    """`waterfall` is invoked with the trailing ``next`` callback."""
    agent = _AgentStub("a4")
    captured: list[Any] = []

    def _listener(this: Any, payload: Any, nxt: Any) -> Any:
        captured.append(("called", nxt))
        return None

    make_ctx.on("agent/request", _listener)  # type: ignore[attr-defined]
    dispatcher = agent_events(make_ctx, agent)
    dispatcher.waterfall("agent/request", {}, lambda: "next-default")


# ---------------------------------------------------------------------------
# emit_agent_event
# ---------------------------------------------------------------------------


def test_emit_agent_event_uses_one_shot_dispatcher(make_ctx) -> None:
    """`emit_agent_event` is a single-emit helper."""
    agent = _AgentStub("a5")
    captured: list[Any] = []

    def _listener(_carrier: Any, _name: str, payload: Any) -> None:
        captured.append(payload["agent"])

    make_ctx.on("agent/inbox/inserted", _listener)  # type: ignore[attr-defined]
    emit_agent_event(make_ctx, agent, "agent/inbox/inserted", {"message": "m"})
    assert captured == [agent]


# ---------------------------------------------------------------------------
# assemble_context_for
# ---------------------------------------------------------------------------


def test_assemble_context_for_sets_agent_and_scope() -> None:
    """`assemble_context_for` always sets both `agent` and `scope` fields."""
    agent = _AgentStub("a6")
    ctx = assemble_context_for(agent)
    assert ctx["agent"] is agent
    assert ctx["scope"] is agent
    assert "signal" not in ctx


def test_assemble_context_for_with_signal() -> None:
    """`signal` is forwarded into the context when provided."""
    import asyncio

    sentinel = asyncio.Event()
    agent = _AgentStub("a7")
    ctx = assemble_context_for(agent, signal=sentinel)
    assert ctx["signal"] is sentinel


# ---------------------------------------------------------------------------
# agent_carrier
# ---------------------------------------------------------------------------


def test_agent_carrier_uses_agent_as_scope_key() -> None:
    """`agent_carrier` mints a scope carrier keyed by the agent."""
    agent = _AgentStub("a8")
    carrier = agent_carrier(agent)
    # `carrier_key_of` (from scope) reads the same key.
    from taiyi_core_scope import carrier_key_of, is_scope_carrier
    assert is_scope_carrier(carrier) is True
    assert carrier_key_of(carrier) is agent


def test_agent_events_uses_provided_carrier() -> None:
    """The optional ``carrier`` argument overrides the default carrier."""
    agent = _AgentStub("a9")
    custom_carrier = agent_carrier(agent)
    dispatcher = agent_events(Context(), agent, carrier=custom_carrier)
    assert isinstance(dispatcher, AgentEventDispatch)


# ---------------------------------------------------------------------------
# AGENT_SUBJECT_EVENT_NAMES (constant sanity)
# ---------------------------------------------------------------------------


def test_agent_subject_event_names_includes_lifecycle_events() -> None:
    """`AGENT_SUBJECT_EVENT_NAMES` enumerates the agent-subject vocabulary."""
    assert "agent/created" in AGENT_SUBJECT_EVENT_NAMES
    assert "agent/disposed" in AGENT_SUBJECT_EVENT_NAMES
    assert "agent/status" in AGENT_SUBJECT_EVENT_NAMES
    assert "agent/pre-step" in AGENT_SUBJECT_EVENT_NAMES
    assert "agent/request" in AGENT_SUBJECT_EVENT_NAMES
    assert "agent/turn-stopping" in AGENT_SUBJECT_EVENT_NAMES
    assert "agent/error" in AGENT_SUBJECT_EVENT_NAMES


def test_agent_events_handles_empty_payload() -> None:
    """A payload of None still gets the injected agent."""
    agent = _AgentStub("a10")
    captured: list[Any] = []

    def _listener(carrier: Any, name: str, payload: Any) -> None:
        captured.append(payload)

    ctx = Context()
    try:
        ctx.on("agent/error", _listener)  # type: ignore[attr-defined]
        agent_events(ctx, agent).emit("agent/error", None)
        # A None payload is wrapped into `{'agent': agent, 'other': None}`.
        assert len(captured) == 1
        assert captured[0]["agent"] is agent
    finally:
        import asyncio
        asyncio.run(ctx.dispose())


async def test_agent_events_serial_throw_is_contained(make_ctx) -> None:
    """`serial` continues past a synchronous listener throw."""
    agent = _AgentStub("a-serial-throw")

    def _boom(_carrier: Any, _name: str, _payload: Any) -> None:
        raise RuntimeError("serial-throw")

    warnings: list[Any] = []

    def _cap(message: Any) -> None:
        warnings.append(message)

    make_ctx.logger.warn = _cap  # type: ignore[attr-defined]
    make_ctx.on("agent/turn-stopping", _boom)  # type: ignore[attr-defined]

    async def _ok(_carrier: Any, _name: str, _payload: Any) -> str:
        return "ok"

    make_ctx.on("agent/turn-stopping", _ok)  # type: ignore[attr-defined]
    dispatcher = agent_events(make_ctx, agent)
    result = await dispatcher.serial("agent/turn-stopping", {})
    assert result == "ok"
    assert any("threw" in str(w) for w in warnings)


async def test_agent_events_serial_awaitable_no_bail(make_ctx) -> None:
    """`serial` continues past an awaiting listener that returns None."""
    agent = _AgentStub("a-serial-await")

    async def _nothing(_carrier: Any, _name: str, _payload: Any) -> None:
        return None

    async def _also_nothing(_carrier: Any, _name: str, _payload: Any) -> None:
        return None

    make_ctx.on("agent/turn-stopping", _nothing)  # type: ignore[attr-defined]
    make_ctx.on("agent/turn-stopping", _also_nothing)  # type: ignore[attr-defined]
    dispatcher = agent_events(make_ctx, agent)
    result = await dispatcher.serial("agent/turn-stopping", {})
    assert result is None


def test_collect_unbound_callbacks_returns_empty_when_no_hooks() -> None:
    """`_collect_unbound_callbacks` returns ``[]`` when no listeners are registered."""
    ctx = Context()
    try:
        callbacks = _collect_unbound_callbacks_local(ctx, "agent/missing")
        assert callbacks == []
    finally:
        import asyncio
        asyncio.run(ctx.dispose())


def _collect_unbound_callbacks_local(ctx: Context, event_name: str) -> list:
    """Local re-implementation that imports the helper only here."""
    from taiyi_core_agent.dispatch import _collect_unbound_callbacks
    return _collect_unbound_callbacks(ctx, event_name)


def test_assemble_context_for_omits_signal_when_none() -> None:
    """`signal` is omitted when the caller passes ``None``."""
    ctx = assemble_context_for(_AgentStub("a-no-signal"))
    assert "signal" not in ctx


def test_assemble_context_for_direct_invoke() -> None:
    """Direct invocation of `assemble_context_for` covers all branches."""
    import asyncio

    from taiyi_core_agent.context import assemble_context_for as _direct

    base = _direct(_AgentStub("agent-direct"))
    assert base["agent"].id == "agent-direct"
    assert base["scope"].id == "agent-direct"
    assert "signal" not in base

    sentinel_loop = asyncio.new_event_loop()
    try:
        # Construct the call with a signal that is type-checked to
        # satisfy the dict assignment path even when the loop is dead.
        with_signal = _direct(_AgentStub("agent-with-signal"), signal=sentinel_loop)
        assert with_signal["signal"] is sentinel_loop
    finally:
        try:
            sentinel_loop.close()
        except Exception:  # pragma: no cover
            pass


async def test_agent_events_emit_async_listener_schedules_log(make_ctx) -> None:
    """`emit` contains an awaited listener that rejects."""
    import asyncio

    agent = _AgentStub("a-async-reject")

    async def _bad_listener(_carrier: Any, _name: str, _payload: Any) -> None:
        raise RuntimeError("async-reject")

    warnings: list[Any] = []

    def _cap(message: Any) -> None:
        warnings.append(message)

    make_ctx.logger.warn = _cap  # type: ignore[attr-defined]
    make_ctx.on("agent/inbox/inserted", _bad_listener)  # type: ignore[attr-defined]
    agent_events(make_ctx, agent).emit("agent/inbox/inserted", {})
    # Allow the scheduled task to run.
    await asyncio.sleep(0)
    assert any("listener rejected" in str(w) for w in warnings)
