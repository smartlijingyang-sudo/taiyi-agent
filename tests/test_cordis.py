"""cordis 框架核心测试：5 种事件派发 + 服务注入 + effect dispose + plugin 挂载。"""
from __future__ import annotations

import asyncio

import pytest

from cordis import Context, Disposer, Registry, Service, plugin


# ---------------------------------------------------------------------------
# Service 注入
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provide_and_inject():
    ctx = Context()

    @plugin
    async def setup(ctx, config):
        ctx.provide("foo", {"hello": "world"})

    await ctx.plugin(setup, {})
    assert ctx.inject("foo") == {"hello": "world"}


@pytest.mark.asyncio
async def test_inject_walks_parent_chain():
    parent = Context()
    parent.provide("foo", "from_parent")
    child = parent.scope("child")
    assert child.inject("foo") == "from_parent"


@pytest.mark.asyncio
async def test_inject_missing_raises():
    ctx = Context()
    with pytest.raises(KeyError):
        ctx.inject("missing")


@pytest.mark.asyncio
async def test_inject_default_when_missing():
    ctx = Context()
    assert ctx.inject("missing", default=None) is None


@pytest.mark.asyncio
async def test_provide_duplicate_raises():
    ctx = Context()
    ctx.provide("foo", 1)
    with pytest.raises(KeyError):
        ctx.provide("foo", 2)


@pytest.mark.asyncio
async def test_requires_returns_tuple():
    ctx = Context()
    ctx.provide("a", 1)
    ctx.provide("b", 2)
    assert ctx.requires("a", "b") == (1, 2)


# ---------------------------------------------------------------------------
# Event dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_serial_runs_all_listeners():
    ctx = Context()
    log: list[str] = []

    async def setup(ctx, config):
        ctx.on("hello", lambda x: log.append(f"a:{x}"))
        ctx.on("hello", lambda x: log.append(f"b:{x}"))

    await ctx.plugin(setup, {})
    await ctx.emit("hello", "x")
    assert log == ["a:x", "b:x"]


@pytest.mark.asyncio
async def test_emit_serial_with_async_listener():
    ctx = Context()
    log: list[str] = []

    async def setup(ctx, config):
        async def listen(x: str) -> None:
            await asyncio.sleep(0.01)
            log.append(f"async:{x}")

        ctx.on("hello", listen)

    await ctx.plugin(setup, {})
    await ctx.emit("hello", "x")
    assert log == ["async:x"]


@pytest.mark.asyncio
async def test_parallel_emit_concurrent():
    ctx = Context()
    log: list[int] = []

    async def setup(ctx, config):
        async def listen(tag: int) -> None:
            await asyncio.sleep(0.01)
            log.append(tag)

        ctx.on("p", listen)
        ctx.on("p", listen)
        ctx.on("p", listen)

    await ctx.plugin(setup, {})
    await ctx.parallel_emit("p", 1)
    # 三个监听器都跑过
    assert sorted(log) == [1, 1, 1]


@pytest.mark.asyncio
async def test_waterfall_chains_in_order():
    ctx = Context()
    log: list[str] = []

    async def setup(ctx, config):
        ctx.waterfall("wf", lambda v, nxt: nxt(v + 1))
        ctx.waterfall("wf", lambda v, nxt: nxt(v * 10))
        ctx.waterfall("wf", lambda v, nxt: log.append(f"final:{v}") or v)

    await ctx.plugin(setup, {})
    out = await ctx.emit("wf", 1)
    # 1 -> +1 -> *10 -> final
    assert out == 10
    assert log == ["final:10"]


@pytest.mark.asyncio
async def test_waterfall_without_next_vetoes():
    """waterfall 监听器不调用 next() 即 veto，下游不再跑。"""
    ctx = Context()
    log: list[str] = []

    async def setup(ctx, config):
        ctx.waterfall("wf", lambda v, nxt: log.append(f"vetoed:{v}"))
        ctx.waterfall("wf", lambda v, nxt: nxt(v + 1))

    await ctx.plugin(setup, {})
    out = await ctx.emit("wf", 1)
    assert out == 1
    assert log == ["vetoed:1"]


# ---------------------------------------------------------------------------
# Effect / Dispose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_effect_disposer_runs_on_dispose():
    ctx = Context()
    counter = {"n": 0}

    def on_cleanup() -> None:
        counter["n"] += 1

    ctx.effect(setup=lambda: None, disposer=on_cleanup, name="t")
    await ctx.dispose()
    assert counter["n"] == 1
    # idempotent
    await ctx.dispose()
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_disposer_idempotent():
    d = Disposer(lambda: None, name="x")
    assert not d.done
    await d.dispose()
    assert d.done
    await d.dispose()
    assert d.done


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plugin_runs_setup():
    ctx = Context()

    @plugin
    async def setup(ctx, config):
        ctx.provide("plugin_ran", True)

    await ctx.plugin(setup, {})
    assert ctx.inject("plugin_ran") is True


@pytest.mark.asyncio
async def test_plugin_must_be_async():
    with pytest.raises(TypeError):

        @plugin
        def sync_setup(ctx, config):  # type: ignore[arg-type]
            pass


@pytest.mark.asyncio
async def test_plugin_disposer_removes_added_services():
    ctx = Context()

    @plugin
    async def setup(ctx, config):
        ctx.provide("temp", "data")

    d = await ctx.plugin(setup, {})
    assert ctx.has("temp")
    await d.dispose()
    assert not ctx.has("temp")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_register_and_get():
    r: Registry[str] = Registry()
    r.register("a", "alpha")
    r.register("b", "beta")
    assert r.get("a") == "alpha"
    assert r.names() == ["a", "b"]


def test_registry_unregister():
    r: Registry[str] = Registry()
    r.register("a", "alpha")
    r.unregister("a")
    assert not r.has("a")


def test_registry_duplicate_raises():
    r: Registry[str] = Registry()
    r.register("a", "x")
    with pytest.raises(ValueError):
        r.register("a", "y")


# ---------------------------------------------------------------------------
# Fiber (scope)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_inherits_state():
    parent = Context()
    parent.state["shared"] = "value"
    child = parent.scope("child")
    assert child.state["shared"] == "value"
    child.state["added_in_child"] = 42
    assert parent.state["added_in_child"] == 42  # shared


@pytest.mark.asyncio
async def test_scope_inherits_config():
    parent = Context(config={"x": 1, "y": 2})
    child = parent.scope("child", config={"y": 99, "z": 3})
    assert child.config == {"x": 1, "y": 99, "z": 3}


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_dispose_called_on_ctx_dispose():
    ctx = Context()

    class Svc(Service):
        def __init__(self, ctx: Context) -> None:
            super().__init__(ctx)
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    svc = Svc(ctx)
    ctx.provide("svc", svc)
    await ctx.dispose()
    assert svc.disposed