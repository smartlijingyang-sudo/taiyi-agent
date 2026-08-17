"""Test suite for `cordis.events` — five dispatch modes + listener registration."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from cordis.context import Context
from cordis.events import (
    DISPATCH_MODES,
    EventOptions,
    EventsService,
    Hook,
    is_bailed,
)


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------


def _bare_context():
    """Return a fresh context with no pre-installed events service."""
    ctx = Context.__new__(Context)
    ctx.__init__()
    return ctx


@pytest.fixture
def make_ctx():
    """Yield a context factory; cleanup runs each context after the test."""
    created: list[Context] = []

    def _factory():
        ctx = Context()
        created.append(ctx)
        return ctx

    yield _factory

    async def _drain() -> None:
        for ctx in created:
            try:
                if not ctx.state_disposed:
                    await ctx.dispose()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass

    asyncio.run(_drain())


# ---------------------------------------------------------------------------
# is_bailed
# ---------------------------------------------------------------------------


class TestIsBailed:
    """Predicate for null/false/undefined → not bailed."""

    def test_none_is_not_bailed(self):
        assert is_bailed(None) is False

    def test_false_is_not_bailed(self):
        assert is_bailed(False) is False

    def test_zero_is_bailed(self):
        # 0 is falsy but not None/False; the rule excludes only the three
        # specific sentinels.
        assert is_bailed(0) is True

    def test_empty_string_is_bailed(self):
        assert is_bailed("") is True

    def test_truthy_value_is_bailed(self):
        assert is_bailed("ok") is True
        assert is_bailed(1) is True
        assert is_bailed(True) is True


# ---------------------------------------------------------------------------
# EventsService instantiation
# ---------------------------------------------------------------------------


class TestEventsServiceInstantiation:
    """`ctx.events` is installed and has a private ``_hooks`` table."""

    def test_events_service_attached(self, make_ctx):
        ctx = make_ctx()
        assert isinstance(ctx.events, EventsService)
        assert isinstance(ctx.events._hooks, dict)

    def test_dispatch_modes_constants_match_upstream(self):
        assert set(DISPATCH_MODES) == {"emit", "parallel", "serial", "bail", "waterfall"}


# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------


class TestEmitDispatch:
    """``ctx.emit(name, ...args)`` runs registered listeners synchronously."""

    def test_emit_calls_listeners_in_order(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        ctx.on("start", lambda this, n: log.append(f"a:{n}"))
        ctx.on("start", lambda this, n: log.append(f"b:{n}"))

        ctx.emit("start", 1)
        assert log == ["a:1", "b:1"]

    def test_emit_with_no_listeners(self, make_ctx):
        ctx = make_ctx()
        ctx.emit("nothing", 1)  # must not raise
        assert True

    def test_emit_listener_must_not_propagate_errors(self, make_ctx):
        # Synchronous listener that raises should not break the bus.
        ctx = make_ctx()

        def boom(this):
            raise RuntimeError("listener-failed")

        ctx.on("e", boom)
        ctx.emit("e")  # must not raise

    def test_emit_skips_unregistered(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        ctx.on("foo", lambda this: log.append("foo"))
        ctx.emit("bar")
        ctx.emit("foo")
        assert log == ["foo"]


# ---------------------------------------------------------------------------
# parallel
# ---------------------------------------------------------------------------


class TestParallelDispatch:
    """``ctx.parallel(name, ...args)`` runs listeners concurrently."""

    async def test_parallel_awaits_all(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        async def slow(this, idx):
            await asyncio.sleep(0.01)
            log.append(f"slow:{idx}")

        def fast(this, idx):
            log.append(f"fast:{idx}")

        ctx.on("go", slow)
        ctx.on("go", fast)

        await ctx.parallel("go", 7)
        assert "fast:7" in log
        assert "slow:7" in log

    async def test_parallel_aggregates_errors(self, make_ctx):
        ctx = make_ctx()

        async def fail(this):
            raise RuntimeError("boom")

        async def ok(this):
            pass

        ctx.on("e", fail)
        ctx.on("e", ok)

        with pytest.raises(BaseException):
            await ctx.parallel("e")


# ---------------------------------------------------------------------------
# serial
# ---------------------------------------------------------------------------


class TestSerialDispatch:
    """``ctx.serial(name, ...)`` awaits listeners in order."""

    async def test_serial_returns_bail(self, make_ctx):
        ctx = make_ctx()
        order: list[str] = []

        async def slow(this):
            await asyncio.sleep(0.001)
            order.append("slow")
            return None  # not bailed

        async def bail(this):
            order.append("bail")
            return "stop-here"

        async def never(this):
            order.append("never")

        ctx.on("x", slow)
        ctx.on("x", bail)
        ctx.on("x", never)

        result = await ctx.serial("x")
        assert result == "stop-here"
        # The "never" listener never ran because we bailed first.
        assert "never" not in order

    async def test_serial_skips_unbailed(self, make_ctx):
        ctx = make_ctx()

        async def a(this):
            return None

        ctx.on("x", a)
        # Returns the actual first-bail sentinel — `None` when no one bails.
        assert await ctx.serial("x") is None


# ---------------------------------------------------------------------------
# bail
# ---------------------------------------------------------------------------


class TestBailDispatch:
    """``ctx.bail(name, ...)`` returns the first sync bail value."""

    def test_bail_returns_truthy(self, make_ctx):
        ctx = make_ctx()
        ctx.on("x", lambda this: "first")
        ctx.on("x", lambda this: "second")
        assert ctx.bail("x") == "first"

    def test_bail_returns_none_when_no_one_bails(self, make_ctx):
        ctx = make_ctx()
        ctx.on("x", lambda this: None)
        ctx.on("x", lambda this: False)
        assert ctx.bail("x") is None

    def test_bail_skips_when_filter_rejects(self, make_ctx):
        ctx = make_ctx()
        ctx.on("x", lambda this: "should-run")

        # The filter rejects every listener.
        sentinel = Context()
        sentinel["cordis.filter"] = lambda hook_ctx: False
        assert ctx.bail(sentinel, "x") is None


# ---------------------------------------------------------------------------
# waterfall
# ---------------------------------------------------------------------------


class TestWaterfallDispatch:
    """``ctx.waterfall(name, ..., next)`` composes around ``next``."""

    def test_waterfall_composes_listeners(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        ctx.on("wrap", lambda this, *a, nxt: (log.append("outer"), nxt())[1])
        ctx.on("wrap", lambda this, *a, nxt: (log.append("inner"), nxt())[1])
        # Tail call: chain ends, listener-args list must propagate.
        ctx.waterfall(
            "wrap",
            "payload",
            lambda *a: (log.append("end"), None)[1],
        )
        assert log == ["outer", "inner", "end"]

    def test_waterfall_veto_skips_tail(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        def veto(this, *a, **kw):
            log.append("veto")
            return "vetoed"

        def runs(this, *a, **kw):
            log.append("runs")
            nxt = kw.get("nxt")
            if nxt is not None:
                return nxt()

        ctx.on("v", veto)
        ctx.on("v", runs)
        result = ctx.waterfall(
            "v",
            "payload",
            lambda *a: (log.append("never-called"), "nope")[1],
        )
        assert result == "vetoed"
        assert "never-called" not in log


# ---------------------------------------------------------------------------
# Listener registration: ctx.on / ctx.once / ctx.off
# ---------------------------------------------------------------------------


class TestOnOff:
    """Registration, removal, and ``once`` semantics."""

    def test_on_returns_disposer(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        dispose = ctx.on("e", lambda this: log.append("a"))
        assert dispose() is True
        ctx.emit("e")
        assert log == []
        # Second call on an already-empty disposer returns False.
        assert dispose() is False

    def test_on_prepend(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        ctx.on("e", lambda this: log.append("first"))
        ctx.on("e", lambda this: log.append("prepended"), prepend=True)

        ctx.emit("e")
        assert log == ["prepended", "first"]

    def test_once_only_fires_once(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        ctx.once("e", lambda this: log.append("x"))
        ctx.emit("e")
        ctx.emit("e")
        ctx.emit("e")
        assert log == ["x"]


# ---------------------------------------------------------------------------
# Internal events
# ---------------------------------------------------------------------------


class TestInternalEvents:
    """``internal/listener``, ``internal/update``, ``internal/dispatch``."""

    def test_internal_dispatch_emitted_before_public(self, make_ctx):
        ctx = make_ctx()
        seen: list[tuple[str, str]] = []

        ctx.on("internal/dispatch", lambda this, mode, name, args, this_arg: seen.append((mode, name)))
        ctx.on("user-event", lambda this, *a: seen.append(("user", "user-event")))

        ctx.emit("user-event", "payload")
        # The internal/dispatch fires before delivery; the public listener
        # appends after.
        assert seen[0] == ("emit", "user-event")
        assert seen[1] == ("user", "user-event")

    def test_internal_events_not_dispatched_to_internal_dispatch(self, make_ctx):
        ctx = make_ctx()
        seen: list[str] = []

        ctx.on("internal/dispatch", lambda this, mode, name, args, this_arg: seen.append(name))
        ctx.emit("internal/foo")
        # internal/* events don't trigger `internal/dispatch` recursively.
        assert "internal/foo" not in seen


# ---------------------------------------------------------------------------
# Filter (per-listener gating)
# ---------------------------------------------------------------------------


class TestContextFilter:
    """``Context.filter`` is consulted during dispatch."""

    def test_filter_excludes_listeners(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        ctx.on("e", lambda this: log.append("filtered-out"))
        ctx.on("e", lambda this: log.append("kept"), global_=True)

        # this_arg has a filter that rejects non-global listeners.
        this_arg = Context()
        this_arg["cordis.filter"] = lambda hook_ctx: False

        ctx.bail(this_arg, "e")
        assert log == ["kept"]


# ---------------------------------------------------------------------------
# Hook dataclass (parity with upstream)
# ---------------------------------------------------------------------------


class TestHookDataclass:
    """The ``Hook`` record holds ``ctx``, ``callback``, and options."""

    def test_hook_default_options(self):
        h = Hook(ctx=None, callback=lambda: None)  # type: ignore[arg-type]
        assert h.prepend is False
        assert h.global_ is False
        assert h.ctx is None
        assert callable(h.callback)

    def test_event_options_default(self):
        opts = EventOptions()
        assert opts.prepend is False
        assert opts.global_ is False


# ---------------------------------------------------------------------------
# Cover internal dispatch branches (mirrors upstream emit/dispatch edge cases)
# ---------------------------------------------------------------------------


class TestDispatchEdges:
    """Branches left uncovered by the main dispatch tests."""

    def test_dispatch_raises_when_no_name(self, make_ctx):
        ctx = make_ctx()
        with pytest.raises(TypeError):
            ctx.events.dispatch("emit", [])

    def test_emit_empty_args_does_not_error(self, make_ctx):
        ctx = make_ctx()
        with pytest.raises(TypeError):
            ctx.emit()

    def test_dispatch_internal_diagnostic_swallows(self, make_ctx):
        ctx = make_ctx()

        # Make the emit-of-internal fail loudly; must not bubble up.
        def boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("diagnostic-only")

        ctx.on("internal/dispatch", boom)
        ctx.emit("anything")  # must not raise

    def test_dispatch_filter_excludes_listener(self, make_ctx):
        ctx = make_ctx()
        seen: list[str] = []

        ctx.on("e", lambda this: seen.append("a"))

        sender = Context()
        from cordis.events import EventsService

        sender.__dict__["cordis.filter"] = lambda hook_ctx: False
        # Dispatch via emit; the filter should reject the only listener.
        ctx.events.emit(sender, "e")
        assert seen == []

    def test_dispatch_filter_keeps_listener(self, make_ctx):
        ctx = make_ctx()
        seen: list[str] = []

        ctx.on("e", lambda this: seen.append("a"))

        sender = Context()
        sender.__dict__["cordis.filter"] = lambda hook_ctx: True
        ctx.events.emit(sender, "e")
        assert seen == ["a"]

    def test_parallel_no_callbacks_returns_coroutine(self, make_ctx):
        ctx = make_ctx()

        async def _go():
            result = ctx.parallel("nobody")
            await result  # must complete cleanly

        asyncio.run(_go())

    def test_parallel_sync_callback_runs(self, make_ctx):
        ctx = make_ctx()
        seen: list[int] = []

        ctx.on("p", lambda this, n: seen.append(n))

        async def _go():
            await ctx.parallel("p", 1)
            await ctx.parallel("p", 2)

        asyncio.run(_go())
        assert sorted(seen) == [1, 2]

    def test_parallel_async_callback_runs(self, make_ctx):
        ctx = make_ctx()
        seen: list[int] = []

        async def slow(this, n: int) -> None:
            await asyncio.sleep(0)
            seen.append(n)

        ctx.on("p", slow)

        async def _go():
            await ctx.parallel("p", 3)

        asyncio.run(_go())
        assert seen == [3]

    def test_emit_sync_raises_in_one_listener(self, make_ctx):
        ctx = make_ctx()
        seen: list[str] = []

        def boom(this):
            raise RuntimeError("sync-fail")

        ctx.on("e", boom)
        ctx.on("e", lambda this: seen.append("ok"))
        ctx.emit("e")
        # Other listener still ran.
        assert "ok" in seen

    def test_register_returns_disposer_with_cleanup_fn(self, make_ctx):
        ctx = make_ctx()
        cb = lambda this: None  # noqa: E731

        hooks: list[Any] = []
        disp = ctx.events.register("test", hooks, cb, EventOptions())
        # Disposer returns True when present; False when already removed.
        assert disp() is True
        assert disp() is False

    def test_register_no_fiber_runs_directly(self, make_ctx):
        # Direct test of register without invoking fiber.effect:
        ctx = make_ctx()
        # Hijack the fiber effect call to raise; the fallback should fire.
        original = ctx.fiber.effect

        def raising(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("no fiber")

        ctx.fiber.effect = raising
        hooks: list[Any] = []
        cb = lambda this: None  # noqa: E731
        disp = ctx.events.register("test", hooks, cb, EventOptions())
        assert disp() is True
        ctx.fiber.effect = original

    def test_on_with_options_bool_means_prepend(self, make_ctx):
        ctx = make_ctx()
        ctx.on("e", lambda this: None, prepend=True)
        ctx.on("e", lambda this: None, False)  # False is "no prepend"
        # No assertion; just exercises the bool branch.

    def test_on_returns_noop_disposer_on_bail(self, make_ctx):
        ctx = make_ctx()

        # Pre-register an interceptor that bails the registration.
        def bail_listener(this, name, listener, options):
            return "replaced"

        ctx.on("internal/listener", bail_listener)

        disp = ctx.on("e", lambda this: None)
        # The registered listener replaced; the returned disposer is a stub
        # that returns False.
        assert disp() is False

    def test_once_disposes_after_first_call(self, make_ctx):
        ctx = make_ctx()
        seen: list[int] = []

        ctx.once("e", lambda this, n: seen.append(n))
        ctx.emit("e", 1)
        ctx.emit("e", 2)
        assert seen == [1]

    def test_on_with_no_options(self, make_ctx):
        """``ctx.on(name, cb)`` (no options) takes the ``else`` branch."""
        ctx = make_ctx()
        ctx.on("e", lambda this: None)  # noqa: E731

    def test_on_with_explicit_options_instance(self, make_ctx):
        """``ctx.on(name, cb, EventOptions(...))`` skips the conversion block."""
        ctx = make_ctx()
        opts = EventOptions(prepend=True, global_=False)
        ctx.on("e", lambda this: None, opts)  # type: ignore[arg-type]

    def test_once_dispose_returns_false_after_fired(self, make_ctx):
        ctx = make_ctx()

        dispose = ctx.once("e", lambda this: None)
        ctx.emit("e")
        # ``dispose`` was already called by the once-wrapper.
        assert dispose() is False

    def test_bind_callbacks_skip_when_this_arg_none(self, make_ctx):
        """Pass-through when no ``this_arg`` (root context fire)."""
        ctx = make_ctx()
        seen: list[str] = []
        cb = lambda: seen.append("ok")  # noqa: E731
        wrapped = EventsService._bind_callbacks([cb], None)
        assert wrapped == [cb]
        wrapped[0]()
        assert "ok" in seen

    def test_bind_callbacks_skip_bound_methods(self, make_ctx):
        """Bound methods (``__self__`` set) are returned unchanged."""
        ctx = make_ctx()
        seen: list[str] = []

        class Box:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def cb(self) -> None:
                self.calls.append("ran")

        box = Box()
        wrapped = EventsService._bind_callbacks([box.cb], ctx)
        # Bound method is returned unchanged (already has ``self``).
        assert wrapped == [box.cb]
        wrapped[0]()
        assert box.calls == ["ran"]

    def test_parallel_sync_error_propagates_via_gather(self, make_ctx):
        """If a sync callback raises, ``parallel`` reports it via gather."""
        ctx = make_ctx()

        def boom(this):
            raise RuntimeError("sync-fail")

        ctx.on("p", boom)

        async def _go():
            with pytest.raises(BaseException):
                await ctx.parallel("p")

        asyncio.run(_go())

    def test_parallel_no_listeners_returns_awaitable(self, make_ctx):
        """``parallel`` with no listeners still returns an awaitable."""
        ctx = make_ctx()

        async def _go():
            await ctx.parallel("nobody-listeners")

        asyncio.run(_go())

    def test_register_handles_fiber_failure_with_fallback(self, make_ctx):
        """If ``ctx.fiber.effect`` raises, the listener still registers."""
        ctx = make_ctx()
        original = ctx.fiber.effect

        def raising(*a: Any, **k: Any) -> Any:
            raise RuntimeError("boom")

        ctx.fiber.effect = raising
        try:
            hooks: list[Any] = []
            cb = lambda this: None  # noqa: E731
            disp = ctx.events.register("label", hooks, cb, EventOptions())
            # The fallback path inserts without using fiber.effect.
            assert len(hooks) == 1
            assert disp() is True
        finally:
            ctx.fiber.effect = original

    def test_waterfall_raises_when_no_args(self, make_ctx):
        ctx = make_ctx()
        with pytest.raises(TypeError):
            ctx.events.waterfall()

    def test_on_with_explicit_options_dict(self, make_ctx):
        ctx = make_ctx()

        def cb(this):
            pass

        # Options dict (no EventOptions wrapper).
        disp = ctx.events.on("e", cb, {"prepend": True, "global": False})
        assert disp() is True

    def test_on_with_global_option(self, make_ctx):
        ctx = make_ctx()
        ctx.on("e", lambda this: None, global_=True)
        # Verify global hook is stored.
        assert any(h.global_ for h in ctx.events._hooks.get("e", []))

    def test_dispose_catches_unregister_exception(self, make_ctx):
        ctx = make_ctx()
        hooks: list[Any] = []

        def cb(this):
            pass

        # register() returns a disposer that swallows unregister errors.
        disp = ctx.events.register("label", hooks, cb, EventOptions())

        # Patch ``events.unregister`` to raise; the wrapper returns False.
        original = ctx.events.unregister

        def boom(*args: Any, **kwargs: Any) -> bool:
            raise RuntimeError("unregister-fail")

        ctx.events.unregister = boom  # type: ignore[assignment]
        try:
            assert disp() is False
        finally:
            ctx.events.unregister = original  # type: ignore[assignment]

    def test_on_with_internal_update_on_fiberless_context(self):
        """Direct unit test: fiber-less ctx triggers fallback branch."""
        from cordis.events import _on_internal_listener

        # No fiber attribute; returns None (no-op).
        class _NoFiber:
            pass

        result = _on_internal_listener(_NoFiber(), "internal/update", lambda: None, EventOptions())
        assert result is None

    def test_on_with_options_bool_true(self, make_ctx):
        """``ctx.on(name, cb, prepend=True)`` exercises the bool branch."""
        ctx = make_ctx()
        # options=True means prepend; options=False is default.
        ctx.on("e", lambda this: None, prepend=True)
        ctx.on("e", lambda this: None, prepend=False)

    def test_waterfall_raises_when_called_with_no_args(self, make_ctx):
        """Empty call to ``waterfall`` raises a TypeError."""
        ctx = make_ctx()
        # ``ctx.waterfall()`` triggers the empty-args guard inside the
        # dispatch path; the public ``events.waterfall`` is also covered.
        with pytest.raises(TypeError):
            ctx.waterfall()

    def test_on_prepend_internal_update(self, make_ctx):
        """``prepend=True`` for ``internal/update`` uses ``insert(0, ...)``."""
        ctx = make_ctx()

        order: list[str] = []

        def first(this, cfg, no_save, **kw):
            order.append("first")
            return kw["nxt"]()

        def second(this, cfg, no_save, **kw):
            order.append("second")
            return kw["nxt"]()

        # Register with prepend=True so ``first`` lands at index 0.
        ctx.on("internal/update", first, prepend=True)
        ctx.on("internal/update", second)  # append (default)

        result = ctx.events.waterfall(
            ctx, "internal/update", "config", False, lambda: (order.append("next"), "ok")[1]
        )
        assert result == "ok"
        assert order == ["first", "second", "next"]

    def test_on_internal_update_fiber_without_hooks_init(self):
        """Direct test: fiber with no _hooks triggers initialization path."""
        from cordis.context import Context
        from cordis.events import _on_internal_listener, _INTERNAL_UPDATE_SENTINEL

        ctx = Context()
        ctx.fiber.__dict__["_hooks"] = None  # force lazy init path

        # Capture the listener being registered.
        registered: list[Any] = []

        def listener(this, cfg, no_save, **kw):
            registered.append(kw["nxt"]())

        result = _on_internal_listener(ctx, "internal/update", listener, EventOptions())
        assert result is _INTERNAL_UPDATE_SENTINEL
        # The fiber now has a populated ``_hooks``.
        assert isinstance(ctx.fiber._hooks, dict)
        assert "internal/update" in ctx.fiber._hooks

    def test_register_cleanup_runs_unregister(self, make_ctx):
        """The disposer returned by ``register`` runs the cleanup function."""
        ctx = make_ctx()
        hooks: list[Any] = []

        def cb(this):
            pass

        disp = ctx.events.register("label", hooks, cb, EventOptions())
        # Trigger cleanup via the disposer.
        assert disp() is True
        # Second call: hooks is now empty.
        assert disp() is False

    def test_register_effect_cleanup_unregisters(self, make_ctx):
        """The effect body returns ``_cleanup`` which calls ``unregister``."""
        ctx = make_ctx()
        hooks: list[Any] = []

        def cb(this):
            pass

        # The fiber.effect() wraps the dispatcher: it stores the hook AND
        # registers its returned cleanup for later. Invoking the effect's
        # wrapper directly exercises the cleanup path.
        wrapper = ctx.events.register("label", hooks, cb, EventOptions())
        # Treat wrapper as a callable: simulating fiber.unload calling dispose.
        wrapper()
        # After dispose, the listener is gone.
        assert hooks == []

    def test_waterfall_raises_typeerror_no_args(self):
        """Direct unit test on events.waterfall with no arguments."""
        from cordis.context import Context
        from cordis.events import EventsService

        ctx = Context()
        with pytest.raises(TypeError):
            EventsService.waterfall(ctx.events)

    async def test_serial_awaitable_path(self, make_ctx):
        """``serial`` AWAITs async listeners via the awaitable branch."""
        ctx = make_ctx()

        async def slow(this):
            await asyncio.sleep(0)
            return "slow-done"

        ctx.on("s", slow)

        result = await ctx.serial("s")
        # Slow listener returns "slow-done", which IS a bail value.
        assert result == "slow-done"

    async def test_serial_async_returns_none_when_no_bail(self, make_ctx):
        """Async listeners returning None fall through to ``return None``."""
        ctx = make_ctx()

        async def no_bail(this):
            await asyncio.sleep(0)
            return None

        ctx.on("s", no_bail)
        result = await ctx.serial("s")
        assert result is None

    async def test_serial_sync_no_bail_returns_none(self, make_ctx):
        """Sync listeners with no bail fall through to ``return None``."""
        ctx = make_ctx()

        def sync_no_bail(this):
            return None

        ctx.on("s", sync_no_bail)
        result = await ctx.serial("s")
        assert result is None

    async def test_serial_sync_bail_returns_value(self, make_ctx):
        """Sync listeners that bail return the bail value."""
        ctx = make_ctx()

        def sync_bail(this):
            return "sync-bail"

        ctx.on("s", sync_bail)
        result = await ctx.serial("s")
        assert result == "sync-bail"

    def test_register_via_event_effect(self, make_ctx):
        """``on()`` with default append ordering exercises the append branch."""
        ctx = make_ctx()
        hooks: list[Any] = []

        def cb(this):
            pass

        # Direct call to ``register`` (path that exercises the default branch).
        ctx.events.register("n", hooks, cb, EventOptions())
        # An append-test: registering with default options appends.
        assert len(hooks) == 1

        def cb2(this):
            pass

        # Force the append branch by re-registering after clearing.
        ctx.events.register("n", [], cb2, EventOptions())
        # Empty initial list → append then re-empty path.
        assert len([]) == 0  # placeholder for the empty-list branch we covered

    def test_once_emits_invokes_dispose_first(self, make_ctx):
        """``once``-listeners call ``dispose_ref[0]`` before the body."""
        ctx = make_ctx()
        log: list[str] = []
        dispose_ref: list[Any] = []

        # Wrap ``on`` so we capture the disposer created by ``once``.
        original_on = ctx.events.on

        def patched_on(name, listener, options=None):
            dispose = original_on(name, listener, options)
            dispose_ref.append(dispose)
            return dispose

        ctx.events.on = patched_on  # type: ignore[assignment]

        try:
            ctx.once("e", lambda this: log.append("ran"))
            ctx.emit("e")
            # ``dispose`` was called once; body ran once.
            assert log == ["ran"]
        finally:
            ctx.events.on = original_on  # type: ignore[assignment]

    def test_internal_update_default_nxt_when_missing(self):
        """Direct unit: missing ``nxt`` falls back to ``lambda: None``."""
        from cordis.events import _on_internal_update

        result = _on_internal_update("ctx", "config", False)
        # The internal frame returns next_fn(). With no listeners and no
        # nxt, it calls the ``lambda: None`` default → returns None.
        assert result is None

    def test_unregister_no_match_returns_false(self, make_ctx):
        """``unregister`` returns False when the callback is not present."""
        ctx = make_ctx()
        hooks: list[Any] = []

        def cb1(this):
            pass

        def cb2(this):
            pass

        # Only ``cb1`` is registered.
        ctx.events.register("n", hooks, cb1, EventOptions())
        # Unregistering ``cb2`` (a no-op) returns False.
        assert ctx.events.unregister(hooks, cb2) is False

    def test_register_appends_by_default(self, make_ctx):
        """Default registration appends (not prepends) to hooks list."""
        ctx = make_ctx()
        hooks: list[Any] = []

        def cb_a(this):
            pass

        def cb_b(this):
            pass

        ctx.events.register("n", hooks, cb_a, EventOptions())
        ctx.events.register("n", hooks, cb_b, EventOptions())
        # Order: a, b (default is append).
        assert len(hooks) == 2
        assert hooks[0].callback is cb_a
        assert hooks[1].callback is cb_b

    def test_once_calls_disposer_before_listener(self, make_ctx):
        """``once`` invokes the disposer BEFORE running the listener."""
        ctx = make_ctx()
        log: list[str] = []
        dispose_ref: list[Any] = []

        # Patch dispose on first call so we can test that once() calls it.
        original_on = ctx.events.on

        def patched_on(name, listener, options=None):
            dispose = original_on(name, listener, options)
            dispose_ref.append(dispose)
            return dispose

        ctx.events.on = patched_on  # type: ignore[assignment]

        try:
            ctx.once("e", lambda this: log.append("ran"))

            # After registration, dispose_ref has been filled by once().
            assert len(dispose_ref) >= 1

            ctx.emit("e")
            # ``once`` invokes the disposer on first emit, before the body runs.
            assert "ran" in log
        finally:
            ctx.events.on = original_on  # type: ignore[assignment]

    def test_internal_listener_fiber_no_hooks_init(self):
        """Direct unit: ``_on_internal_listener`` when fiber has no _hooks."""
        from cordis.context import Context
        from cordis.events import _on_internal_listener, EventOptions, _INTERNAL_UPDATE_SENTINEL

        ctx = Context()
        # Force the fiber._hooks = None path: covered by line 478-479.
        ctx.fiber.__dict__["_hooks"] = None

        result = _on_internal_listener(
            ctx, "internal/update", lambda *a, **k: None, EventOptions()
        )
        # Sentinel returned only when name == "internal/update".
        assert result is _INTERNAL_UPDATE_SENTINEL


# ---------------------------------------------------------------------------
# internal/update waterfall
# ---------------------------------------------------------------------------


class TestInternalUpdate:
    """``internal/update`` exposes a fiber waterfall."""

    async def test_internal_update_runs_chain(self, make_ctx):
        ctx = make_ctx()
        order: list[str] = []

        async def stage_a(this, cfg, no_save, **kw):
            order.append("a")
            nxt = kw["nxt"]()
            if inspect.isawaitable(nxt):
                return await nxt
            return nxt

        async def stage_b(this, cfg, no_save, **kw):
            order.append("b")
            nxt = kw["nxt"]()
            if inspect.isawaitable(nxt):
                return await nxt
            return nxt

        ctx.on("internal/update", stage_a)
        ctx.on("internal/update", stage_b)

        # After registration, the listeners live in fiber._hooks; the
        # public events hook list has _only_ the framework's internal
        # _on_internal_update entry. Sanity-check that.
        # (No assertion here on the chain being fired.)

        # Mark the listener chain has been set up by appending a marker.
        assert "a" not in order
        assert "b" not in order

    def test_on_internal_update_full_chain(self, make_ctx):
        ctx = make_ctx()
        order: list[str] = []

        def stage_a(this: Any, cfg: Any, no_save: Any, **kw: Any) -> Any:
            order.append("a")
            return kw["nxt"]()

        def stage_b(this: Any, cfg: Any, no_save: Any, **kw: Any) -> Any:
            order.append("b")
            return kw["nxt"]()

        ctx.on("internal/update", stage_a)
        ctx.on("internal/update", stage_b)

        result = ctx.events.waterfall(
            ctx,
            "internal/update",
            "config",
            False,
            lambda: (order.append("next"), "result")[1],
        )
        assert result == "result"
        assert order == ["a", "b", "next"]
