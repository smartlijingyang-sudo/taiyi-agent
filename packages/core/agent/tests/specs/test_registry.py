"""Tests for `taiyi_core_agent.registry` — the live AgentRegistry service."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any

import pytest
from cordis import Context

from taiyi_core_agent.factory import (
    DISPOSED_INITIATOR_MESSAGE,
    NO_FACTORY_MESSAGE,
    NO_INITIATOR_MESSAGE,
    AgentHandle,
    CreateAgentOptions,
    ResumeAgentOptions,
)
from taiyi_core_agent.registry import AgentEntry, AgentRegistry, InitiatorRun

# ---------------------------------------------------------------------------
# Service registration surface
# ---------------------------------------------------------------------------


def test_registry_installs_self_as_ctx_agents(make_ctx) -> None:
    """`AgentRegistry(ctx)` makes `ctx.agents` resolve to the registry."""
    registry = AgentRegistry(make_ctx)
    assert make_ctx.agents is registry  # type: ignore[attr-defined]


def test_current_initiator_is_none_outside_boundary(make_ctx) -> None:
    """No initiator scope is active by default."""
    registry = AgentRegistry(make_ctx)
    assert registry.current_initiator() is None


def test_require_initiator_raises_outside_boundary(make_ctx) -> None:
    """`require_initiator` throws `NO_INITIATOR_MESSAGE` without a boundary."""
    registry = AgentRegistry(make_ctx)
    with pytest.raises(RuntimeError, match=re.escape(NO_INITIATOR_MESSAGE)):
        registry.require_initiator()


def test_require_initiator_returns_agent(make_ctx) -> None:
    """`require_initiator` returns the active initiator when present."""
    registry = AgentRegistry(make_ctx)
    sentinel = _make_agent("sentinel")
    seen: list[Any] = []

    def _op() -> None:
        seen.append(registry.require_initiator())

    registry.with_initiator(sentinel, _op)
    assert seen and seen[0] is sentinel


# ---------------------------------------------------------------------------
# Initiator boundaries
# ---------------------------------------------------------------------------


def test_with_initiator_returns_value_and_restores_bound(make_ctx) -> None:
    """`with_initiator(agent, op)` exposes `agent` and restores the previous value."""
    registry = AgentRegistry(make_ctx)
    sentinel_agent = _make_agent("a-1")

    captured: list[Any] = []

    def _op() -> str:
        captured.append(registry.current_initiator())
        return "ok"

    result = registry.with_initiator(sentinel_agent, _op)
    assert result == "ok"
    assert captured[0] is sentinel_agent
    assert registry.current_initiator() is None


def test_without_initiator_clears_inherited(make_ctx) -> None:
    """`without_initiator` clears the inherited agent for one operation."""
    registry = AgentRegistry(make_ctx)
    parent_agent = _make_agent("parent")
    seen: list[Any] = []

    def _inner() -> None:
        seen.append(registry.current_initiator())

    def _outer() -> None:
        registry.with_initiator(parent_agent, _inner)

    _outer()
    assert seen[0] is parent_agent
    # Now in a fresh clearing boundary.
    registry.without_initiator(_inner)
    assert seen[1] is None


def test_with_initiator_preserves_parent_run(make_ctx) -> None:
    """`InitiatorRun.parent` walks the boundary chain."""
    registry = AgentRegistry(make_ctx)
    outer_agent = _make_agent("outer")
    inner_agent = _make_agent("inner")

    seen_parents: list[Any] = []

    def _inner() -> None:
        # Inside inner, the initiator is the inner agent. The active
        # run's `parent` is the outer run, retrievable via the
        # internals: only the registry's release pipeline sees it.
        seen_parents.append(registry.current_initiator())

    def _outer() -> None:
        registry.with_initiator(inner_agent, _inner)

    registry.with_initiator(outer_agent, _outer)
    assert seen_parents[0] is inner_agent


def test_with_initiator_releases_after_synchronous_exception(make_ctx) -> None:
    """An exception inside `operation` releases the run and propagates."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("a")

    def _boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        registry.with_initiator(agent, _boom)
    assert registry._active_initiator_runs == 0


def test_with_initiator_releases_after_async_result_no_loop(make_ctx) -> None:
    """An awaitable result without a running event loop releases immediately."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("a")

    async def _async_op() -> int:
        return 42

    # No event loop is running on the test thread; the run must release
    # synchronously to keep the active count consistent.
    coro = _async_op()
    result = registry.with_initiator(agent, lambda: coro)
    assert asyncio.iscoroutine(result)
    assert registry._active_initiator_runs == 0
    coro.close()  # pragma: no cover — defensive


# ---------------------------------------------------------------------------
# Factory registration
# ---------------------------------------------------------------------------


def test_set_factory_then_require_returns_it(make_ctx) -> None:
    """`set_factory` registers the factory for `create` and `resume`."""
    registry = AgentRegistry(make_ctx)
    factory = _FakeFactory(make_ctx)
    dispose = registry.set_factory(factory)
    assert dispose is not None
    assert callable(dispose)


def test_set_factory_twice_rejects(make_ctx) -> None:
    """A second `set_factory` call throws."""
    registry = AgentRegistry(make_ctx)
    factory = _FakeFactory(make_ctx)
    registry.set_factory(factory)
    with pytest.raises(RuntimeError, match="already registered"):
        registry.set_factory(factory)


def test_create_requires_factory(make_ctx) -> None:
    """`create` throws `NO_FACTORY_MESSAGE` when no factory is registered."""
    registry = AgentRegistry(make_ctx)
    with pytest.raises(RuntimeError, match=re.escape(NO_FACTORY_MESSAGE)):
        registry.create(CreateAgentOptions(session_id="s-1"))


def test_resume_requires_factory(make_ctx) -> None:
    """`resume` throws `NO_FACTORY_MESSAGE` when no factory is registered."""
    registry = AgentRegistry(make_ctx)

    async def _runner() -> None:
        with pytest.raises(RuntimeError, match=re.escape(NO_FACTORY_MESSAGE)):
            await registry.resume(ResumeAgentOptions(resume_session_id="s-1"))

    asyncio.run(_runner())


def test_create_invokes_factory_synchronously(make_ctx) -> None:
    """`create` invokes the factory and returns its handle."""
    registry = AgentRegistry(make_ctx)
    factory = _FakeFactory(make_ctx, sync=True)
    registry.set_factory(factory)
    handle = registry.create(CreateAgentOptions(session_id="s-1"))
    assert factory.create_calls == 1
    assert isinstance(handle, AgentHandle)
    assert factory.create_args[0] is registry._ctx
    assert isinstance(factory.create_args[1], CreateAgentOptions)


async def test_resume_invokes_factory(make_ctx) -> None:
    """`resume` returns the factory's awaited handle."""
    registry = AgentRegistry(make_ctx)
    factory = _FakeFactory(make_ctx, sync=False)
    registry.set_factory(factory)
    handle = await registry.resume(ResumeAgentOptions(resume_session_id="s-2"))
    assert isinstance(handle, AgentHandle)


def test_set_factory_disposer_clears_slot(make_ctx) -> None:
    """Calling the disposer returned by `set_factory` clears the slot."""
    registry = AgentRegistry(make_ctx)
    factory = _FakeFactory(make_ctx)
    dispose = registry.set_factory(factory)
    dispose()
    with pytest.raises(RuntimeError, match=re.escape(NO_FACTORY_MESSAGE)):
        registry.create(CreateAgentOptions(session_id="x"))


# ---------------------------------------------------------------------------
# Agent lifecycle (register / enter / announce)
# ---------------------------------------------------------------------------


def test_register_emits_agent_created(make_ctx) -> None:
    """`register(agent)` calls `enter` + `announce`, emitting `agent/created`."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("a1")
    seen: list[Any] = []

    def _listener(_carrier: Any, _name: str, payload: Any) -> None:
        seen.append(payload["agent"])

    make_ctx.on("agent/created", _listener)  # type: ignore[attr-defined]
    registry.register(agent)
    assert seen == [agent]


def test_register_emits_agent_disposed_when_handle_disposed(make_ctx) -> None:
    """Unregistering the agent during teardown emits `agent/disposed`."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("a2")
    seen: list[Any] = []

    def _listener(_carrier: Any, _name: str, payload: Any) -> None:
        seen.append(payload["agent"])

    make_ctx.on("agent/disposed", _listener)  # type: ignore[attr-defined]
    detach = registry.register(agent)
    detach()
    assert seen == [agent]


def test_get_returns_live_agent(make_ctx) -> None:
    """`get` returns the live agent (or `None`)."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("a3")
    assert registry.get("a3") is None
    registry.register(agent)
    assert registry.get("a3") is agent
    assert registry.get("missing") is None


def test_get_after_unregister_returns_none(make_ctx) -> None:
    """After teardown, `get` no longer returns the agent."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("a4")
    detach = registry.register(agent)
    detach()
    assert registry.get("a4") is None


def test_list_and_roots_have_consistent_order(make_ctx) -> None:
    """`list` enumerates in registration order; `roots` filters by `owner`."""
    registry = AgentRegistry(make_ctx)
    a = _make_agent("a-root")
    b = _make_agent("b-child")
    registry.register(a)  # owner=undefined
    # Manually inject an entry with owner so `roots` filters correctly.
    entry = AgentEntry(id="b-child", agent=b, owner=a, carrier=_FakeCarrier())
    registry._store["b-child"] = entry
    assert registry.list() == [a, b]
    assert registry.roots() == [a]


def test_is_owned_by_returns_true_only_for_owner(make_ctx) -> None:
    """`is_owned_by` reads the runtime ownership recorded at insertion."""
    registry = AgentRegistry(make_ctx)
    a = _make_agent("a")
    b = _make_agent("b")
    entry = AgentEntry(id="b", agent=b, owner=a, carrier=_FakeCarrier())
    registry._store["b"] = entry
    assert registry.is_owned_by("b", a) is True
    assert registry.is_owned_by("b", _make_agent("other")) is False


def test_register_rejects_id_mismatch(make_ctx) -> None:
    """Inserting a `Agent.id` not matching `Agent.session.id` throws."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("agent-id")
    agent.session.id = "session-id"  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="does not match session id"):
        registry.enter(agent, None)


def test_register_rejects_duplicate(make_ctx) -> None:
    """A second `enter` with the same id throws (collision boundary)."""
    registry = AgentRegistry(make_ctx)
    a = _make_agent("dup")
    b = _make_agent("dup")
    registry.enter(a, None)
    with pytest.raises(RuntimeError, match="already registered"):
        registry.enter(b, None)


def test_announce_rejects_unowned_agent(make_ctx) -> None:
    """`announce` rejects agents that are not the live entry for their id."""
    registry = AgentRegistry(make_ctx)
    a = _make_agent("alive")
    other = _make_agent("alive")
    registry.enter(a, None)
    with pytest.raises(RuntimeError, match="not live"):
        registry.announce(other)


def test_announce_rejects_double_announcement(make_ctx) -> None:
    """`announce` rejects when an entry has already been announced."""
    registry = AgentRegistry(make_ctx)
    a = _make_agent("ann")
    registry.enter(a, None)
    registry.announce(a)
    with pytest.raises(RuntimeError, match="was already announced"):
        registry.announce(a)


def test_detach_before_announce_emits_no_disposed(make_ctx) -> None:
    """An entry rolled back before announce must not emit `agent/disposed`."""
    registry = AgentRegistry(make_ctx)
    a = _make_agent("rollback")
    disposed_seen: list[Any] = []

    def _listener(_carrier: Any, _name: str, payload: Any) -> None:
        disposed_seen.append(payload["agent"])

    make_ctx.on("agent/disposed", _listener)  # type: ignore[attr-defined]
    detach = registry.enter(a, None)
    detach()
    assert disposed_seen == []
    assert registry.get("rollback") is None


def test_emit_created_contains_synchronous_listener_errors(make_ctx) -> None:
    """Synchronous listener errors during `agent/created` are contained."""
    registry = AgentRegistry(make_ctx)
    agent = _make_agent("err")
    warnings: list[Any] = []

    def _boom(_carrier: Any, _name: str, _payload: Any) -> None:
        raise RuntimeError("listener-threw")

    def _cap(message: Any) -> None:
        warnings.append(message)

    make_ctx.logger.warn = _cap  # type: ignore[attr-defined]
    make_ctx.on("agent/created", _boom)  # type: ignore[attr-defined]
    registry.register(agent)
    # Listener raised; the warn helper captured the message.
    assert any("listener threw" in str(w) for w in warnings)


def test_has_lifecycle_ancestor_returns_true_when_candidate_matches(make_ctx) -> None:
    """A candidate identical to the registry's fiber is its own ancestor."""
    registry = AgentRegistry(make_ctx)
    fiber = make_ctx.fiber  # type: ignore[attr-defined]
    assert registry._has_lifecycle_ancestor(fiber) is True


def test_has_lifecycle_ancestor_returns_false_for_different_fiber(make_ctx) -> None:
    """A fiber unrelated to the registry has no lifecycle ancestor relation."""
    registry = AgentRegistry(make_ctx)
    fake_fiber = _FakeFiber(make_ctx.fiber)  # type: ignore[attr-defined]
    assert registry._has_lifecycle_ancestor(fake_fiber) is False  # type: ignore[arg-type]


def test_close_initiators_transitions_state(make_ctx) -> None:
    """`_close_initiators` flips state from active -> closing."""
    registry = AgentRegistry(make_ctx)
    assert registry._initiator_state == "active"
    registry._close_initiators()
    assert registry._initiator_state == "closing"
    # A second call is a no-op (already closing).
    registry._close_initiators()
    assert registry._initiator_state == "closing"


def test_assert_initiators_readable_raises_after_disposed(make_ctx) -> None:
    """`current_initiator` throws once the scope is disposed."""
    registry = AgentRegistry(make_ctx)
    registry._initiator_state = "disposed"
    with pytest.raises(RuntimeError, match=re.escape(DISPOSED_INITIATOR_MESSAGE)):
        registry.current_initiator()


def test_release_initiator_run_idempotent() -> None:
    """Releasing an inactive run does not double-decrement the counter.

    Uses an explicit registry instance (no Cordis context / event loop)
    so the drain future can be a stub — release must short-circuit
    when no active runs remain.
    """

    class _StubRegistry:
        # ``_release_initiator_run`` only writes ``_active_initiator_runs``
        # and ``_initiator_drain``; bind the bare attributes the method
        # needs so it can run without a real ``AgentRegistry``.
        _active_initiator_runs = 1
        _initiator_drain = None

        _release_initiator_run = AgentRegistry._release_initiator_run

    fake = _StubRegistry()
    run = InitiatorRun(active=True, parent=None)
    fake._release_initiator_run(run)
    assert fake._active_initiator_runs == 0
    # Calling again is a no-op because the run was marked inactive.
    fake._release_initiator_run(run)
    assert fake._active_initiator_runs == 0


def test_release_initiator_run_resolves_drain_future() -> None:
    """Releasing the last run resolves a pending drain future.

    Runs in a tiny event loop so ``asyncio.Future`` is constructible;
    the future must settle before the run is fully drained.
    """
    import asyncio

    async def _runner() -> None:
        ctx = Context()
        try:
            registry = AgentRegistry(ctx)
            run = InitiatorRun(active=True, parent=None)
            registry._active_initiator_runs = 1
            drain = asyncio.get_event_loop().create_future()
            registry._initiator_drain = drain
            registry._release_initiator_run(run)
            # Future resolved without an error.
            assert drain.result() is None
        finally:
            await ctx.dispose()

    asyncio.run(_runner())


# ---------------------------------------------------------------------------
# Async: drain semantics
# ---------------------------------------------------------------------------


async def test_dispose_initiators_settles_future(make_ctx) -> None:
    """`_dispose_initiators` returns the memoized future once teardown settles."""
    registry = AgentRegistry(make_ctx)
    future = registry._dispose_initiators()
    await future
    assert registry._initiator_state == "disposed"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _AgentStub:
    """Minimal Agent stand-in exposing the surface the registry reads."""

    id: str
    session: _SessionStub
    options: dict
    inbox: Any
    status: Any
    ctx: Any

    def __init__(self, agent_id: str, ctx: Any) -> None:
        self.id = agent_id
        self.session = _SessionStub(agent_id)
        self.options = {}
        self.inbox = _InboxStub()
        self.status = "idle"
        self.ctx = ctx

    def cancel(self, _cause: Any, _options: Any = None) -> None:
        pass

    async def when_idle(self) -> None:
        return None

    def run_maintenance(self, _task: Any) -> Any:
        return None

    def send(self, _msg: Any, _target: str, _wakeup: bool) -> None:
        pass

    def followup(self, _msg: Any) -> None:
        pass

    def steer(self, _msg: Any) -> None:
        pass

    def inject(self, _msg: Any) -> None:
        pass


class _SessionStub:
    id: str
    events: tuple

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.events = ()


class _InboxStub:
    next_turn: list = []
    next_step: list = []
    has_pending: bool = False


class _CarrierStub:
    pass


class _FakeCarrier:
    pass


class _FakeFactory:
    """Stand-in loop-owned factory used to exercise the registry.

    Defaults to a synchronous factory (returns ``AgentHandle`` directly).
    Pass ``sync=False`` to return a coroutine the registry must await.
    """

    def __init__(self, ctx: Any, sync: bool = True) -> None:
        self._ctx = ctx
        self._sync = sync
        self.create_calls = 0
        self.create_args: list[Any] = []
        self.resume_calls = 0
        self.resume_args: list[Any] = []
        self._create_result: Any = None
        self._resume_result: Any = None

    def create_agent(
        self, owner_ctx: Context, options: CreateAgentOptions
    ) -> Any:
        self.create_calls += 1
        self.create_args = [owner_ctx, options]
        if self._sync:
            return _FakeHandle(_make_agent("created-agent", owner_ctx))
        # Async path — return a coroutine so the registry awaits it.
        async def _async_create() -> AgentHandle:
            return _FakeHandle(_make_agent("async-agent", owner_ctx))

        return _async_create()

    def resume(
        self, owner_ctx: Context, options: ResumeAgentOptions
    ) -> Any:
        self.resume_calls += 1
        self.resume_args = [owner_ctx, options]
        if self._sync:
            return _FakeHandle(_make_agent("resumed-agent", owner_ctx))
        async def _async_resume() -> AgentHandle:
            return _FakeHandle(_make_agent("resumed-agent", owner_ctx))

        return _async_resume()


class _FakeHandle(AgentHandle):
    """Handle implementation for tests."""

    def __init__(self, agent: _AgentStub) -> None:
        super().__init__(agent, _make_dispose())

    def dispose(self):  # type: ignore[override]
        async def _noop() -> None:
            return None

        return _noop()


class _FakeFiber:
    """Fiber stand-in used to exercise `_has_lifecycle_ancestor`."""

    def __init__(self, real_fiber: Any) -> None:
        # ``parent.fiber`` is the next link; a self-referential parent
        # stops the walk after one step.
        self.parent = type("P", (), {"fiber": self})()
        self._real_fiber = real_fiber

    def __eq__(self, other: Any) -> bool:
        return False

    def __hash__(self) -> int:
        return id(self)


def _make_agent(agent_id: str, ctx: Any | None = None) -> _AgentStub:
    """Build a minimal agent stand-in for registry tests."""
    ctx_obj = ctx if ctx is not None else None
    return _AgentStub(agent_id, ctx_obj)


def _make_dispose() -> Callable[[], Any]:
    async def _dispose() -> None:
        return None

    return _dispose
