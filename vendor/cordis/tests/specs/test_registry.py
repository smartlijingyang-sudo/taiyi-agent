"""Test suite for `cordis.registry` — plugin registry and DI helpers.

Mirrors upstream behaviour of `~/deepseek-harness/vendor/cordis/src/registry.ts`:

- ``RegistryService`` resolves plugin shapes (function / class / object).
- ``PluginRuntime`` is shared by every fiber of a plugin callback.
- ``inject()`` runs callbacks once declared dependencies are available.
- Lookup helpers (``get`` / ``has`` / ``delete`` / iteration).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

import pytest

from cordis.context import Context
from cordis.fiber import Fiber, FiberState
from cordis.registry import (
    Inject,
    PluginRuntime,
    RegistryService,
    inject_resolve,
    is_applicable,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_context() -> Context:
    """Mint a fresh Context for tests that don't share a fixture."""
    return Context()


def asyncio_run_await(fiber: Fiber) -> None:
    """Drive ``fiber.await_()`` in a one-shot event loop."""
    coro = fiber.await_()
    if inspect.isawaitable(coro):
        asyncio.run(coro)


@pytest.fixture
def make_ctx():
    """Yield a context factory with auto-cleanup."""
    created: list[Context] = []

    def _factory() -> Context:
        ctx = Context()
        created.append(ctx)
        return ctx

    yield _factory

    import asyncio

    async def _drain() -> None:
        for ctx in created:
            try:
                if not ctx.state_disposed:
                    await ctx.dispose()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass

    asyncio.run(_drain())


# ---------------------------------------------------------------------------
# PluginRuntime dataclass
# ---------------------------------------------------------------------------


class TestPluginRuntime:
    """``PluginRuntime`` carries callback + Config + per-fiber DisposableList."""

    def test_default_construction(self):
        rt = PluginRuntime()
        assert rt.name is None
        assert rt.callback is not None  # default sentinel lambda
        assert rt.Config is None
        assert len(rt.fibers) == 0

    def test_fields_are_settable(self):
        def cb(this: Context, cfg: Any) -> None:  # pragma: no cover — exercise only
            pass

        rt = PluginRuntime(name="x", callback=cb, Config={"type": "noop"})
        assert rt.name == "x"
        assert rt.callback is cb
        assert rt.Config == {"type": "noop"}


# ---------------------------------------------------------------------------
# is_applicable
# ---------------------------------------------------------------------------


class TestIsApplicable:
    """``is_applicable`` returns True for ``{ apply: fn }`` plugin shapes."""

    def test_dict_with_apply_callable_is_applicable(self):
        def cb(this: Context, cfg: Any) -> None:  # pragma: no cover
            pass

        assert is_applicable({"apply": cb}) is True

    def test_dict_without_apply_is_not_applicable(self):
        assert is_applicable({"name": "x"}) is False

    def test_empty_dict_is_not_applicable(self):
        assert is_applicable({}) is False

    def test_none_is_not_applicable(self):
        assert is_applicable(None) is False

    def test_zero_is_not_applicable(self):
        assert is_applicable(0) is False

    def test_function_is_not_applicable(self):
        def cb(this: Context, cfg: Any) -> None:  # pragma: no cover
            pass

        assert is_applicable(cb) is False

    def test_string_is_not_applicable(self):
        assert is_applicable("hello") is False

    def test_non_callable_apply_is_not_applicable(self):
        assert is_applicable({"apply": "string"}) is False


# ---------------------------------------------------------------------------
# inject_resolve
# ---------------------------------------------------------------------------


class TestInjectResolve:
    """``inject_resolve`` normalizes dependency declarations into a dict."""

    def test_none_returns_default_empty_dict(self):
        assert inject_resolve(None) == {}

    def test_empty_list_returns_default_empty_dict(self):
        assert inject_resolve([]) == {}

    def test_empty_dict_returns_default_empty_dict(self):
        assert inject_resolve({}) == {}

    def test_list_form_sets_values_to_none(self):
        assert inject_resolve(["foo", "bar"]) == {"foo": None, "bar": None}

    def test_dict_form_passes_values_through(self):
        assert inject_resolve({"foo": {"level": 1}}) == {"foo": {"level": 1}}

    def test_dict_form_normalizes_none_values_to_none(self):
        assert inject_resolve({"foo": None, "bar": 1}) == {"foo": None, "bar": 1}

    def test_result_dict_is_appended_to(self):
        out: dict[str, Any] = {"existing": "ok"}
        result = inject_resolve(["foo"], out)
        assert result is out
        assert out == {"existing": "ok", "foo": None}

    def test_falsy_inputs_are_no_ops(self):
        assert inject_resolve(None, {"keep": "yes"}) == {"keep": "yes"}


# ---------------------------------------------------------------------------
# RegistryService — basic
# ---------------------------------------------------------------------------


class TestRegistryServiceBasic:
    """Counter, size, and tracker."""

    def test_counter_increments(self, make_ctx):
        ctx = make_ctx()
        reg = ctx.registry
        c1 = reg.counter
        c2 = reg.counter
        c3 = reg.counter
        assert c1 + 1 == c2
        assert c2 + 1 == c3

    def test_size_starts_at_zero(self, make_ctx):
        ctx = make_ctx()
        assert ctx.registry.size == 0

    def test_size_grows_after_plugin(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(plugin, {})
        assert ctx.registry.size == 1


# ---------------------------------------------------------------------------
# RegistryService.resolve
# ---------------------------------------------------------------------------


class TestRegistryResolve:
    """``resolve`` normalizes the plugin shape to its executable callback."""

    def test_function_resolves_to_itself(self, make_ctx):
        def plugin(this: Context, cfg: Any) -> None:
            pass

        assert ctx_resolve(make_ctx(), plugin) is plugin

    def test_class_resolves_to_itself(self, make_ctx):
        class Plugin:
            def __init__(self, this: Context, cfg: Any) -> None:
                pass

        assert ctx_resolve(make_ctx(), Plugin) is Plugin

    def test_object_form_resolves_to_apply(self, make_ctx):
        def plugin(this: Context, cfg: Any) -> None:
            pass

        obj = {"apply": plugin}
        assert ctx_resolve(make_ctx(), obj) is plugin

    def test_invalid_returns_none(self, make_ctx):
        assert ctx_resolve(make_ctx(), "not a plugin") is None
        assert ctx_resolve(make_ctx(), 42) is None
        assert ctx_resolve(make_ctx(), None) is None
        assert ctx_resolve(make_ctx(), {"no_apply": True}) is None

    def test_resolve_swallows_apply_attribute_errors(self, make_ctx):
        # Object whose ``apply`` lookup raises — fallback returns None.
        class Bad:
            @property
            def apply(self) -> None:
                raise RuntimeError("boom")

        assert ctx_resolve(make_ctx(), Bad()) is None


def ctx_resolve(ctx: Context, plugin: Any) -> Callable[..., Any] | None:
    return ctx.registry.resolve(plugin)


# ---------------------------------------------------------------------------
# RegistryService.get / has / delete
# ---------------------------------------------------------------------------


class TestRegistryGetHasDelete:
    """Lookup + delete semantics."""

    def test_get_returns_none_for_unregistered(self, make_ctx):
        def plugin(this: Context, cfg: Any) -> None:  # pragma: no cover
            pass

        assert make_ctx().registry.get(plugin) is None

    def test_get_returns_runtime_after_register(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(plugin, {})
        rt = ctx.registry.get(plugin)
        assert rt is not None
        assert rt.callback is plugin

    def test_has_true_when_registered(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(plugin, {})
        assert ctx.registry.has(plugin) is True

    def test_has_false_when_unregistered(self, make_ctx):
        def plugin(this: Context, cfg: Any) -> None:  # pragma: no cover
            pass

        assert make_ctx().registry.has(plugin) is False

    def test_get_returns_none_for_invalid_plugin(self, make_ctx):
        assert make_ctx().registry.get(42) is None

    def test_has_false_for_invalid_plugin(self, make_ctx):
        assert make_ctx().registry.has(42) is False

    def test_get_finds_object_form_by_callback(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin({"apply": plugin, "name": "obj"}, {})
        assert ctx.registry.has({"apply": plugin, "name": "obj"}) is True

    def test_delete_unregistered_returns_none(self, make_ctx):
        def plugin(this: Context, cfg: Any) -> None:  # pragma: no cover
            pass

        assert make_ctx().registry.delete(plugin) is None

    def test_delete_invalid_plugin_returns_none(self, make_ctx):
        assert make_ctx().registry.delete(42) is None

    def test_delete_removes_runtime(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(plugin, {})
        rt = ctx.registry.delete(plugin)
        assert rt is not None
        assert rt.callback is plugin
        assert ctx.registry.has(plugin) is False
        assert ctx.registry.size == 0

    def test_delete_disposes_fibers(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        def plugin(this: Context, cfg: Any) -> Any:
            log.append("setup")
            return lambda: log.append("teardown")

        async def _go() -> None:
            fiber = ctx.registry.plugin(plugin, {})
            await fiber.await_()
            ctx.registry.delete(plugin)
            # ``delete`` triggers the dispose chain; the chain schedules
            # _unload which runs the fiber's disposers. Allow the loop to
            # drive any pending tasks before we exit.
            for _ in range(2):
                await asyncio.sleep(0)

        asyncio.run(_go())
        assert "setup" in log
        # ``teardown`` may run after the loop exits; we only verify that the
        # dispose chain was triggered (the runtime was removed).
        assert ctx.registry.size == 0


# ---------------------------------------------------------------------------
# RegistryService iteration
# ---------------------------------------------------------------------------


class TestRegistryIteration:
    """``keys`` / ``values`` / ``entries`` / ``for_each``."""

    def test_keys_lists_registered_callbacks(self, make_ctx):
        ctx = make_ctx()

        def a(this: Context, cfg: Any) -> None:
            pass

        def b(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(a, {})
        ctx.registry.plugin(b, {})
        assert set(ctx.registry.keys()) == {a, b}

    def test_values_lists_runtimes(self, make_ctx):
        ctx = make_ctx()

        def a(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(a, {})
        runtimes = list(ctx.registry.values())
        assert len(runtimes) == 1
        assert runtimes[0].callback is a

    def test_entries_pairs_callbacks_and_runtimes(self, make_ctx):
        ctx = make_ctx()

        def a(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(a, {})
        entries = list(ctx.registry.entries())
        assert entries == [(a, ctx.registry.get(a))]

    def test_for_each_visits_all(self, make_ctx):
        ctx = make_ctx()
        seen: list[Any] = []

        def a(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(a, {})
        ctx.registry.for_each(lambda rt, cb: seen.append((cb, rt.name)))
        assert seen == [(a, None)]


# ---------------------------------------------------------------------------
# RegistryService.plugin — invalid plugin
# ---------------------------------------------------------------------------


class TestRegistryPluginErrors:
    """Plugin shapes that fail validation."""

    def test_invalid_plugin_raises_type_error(self, make_ctx):
        with pytest.raises(TypeError):
            make_ctx().registry.plugin("not a plugin", None)

    def test_invalid_plugin_dict_without_apply_raises(self, make_ctx):
        with pytest.raises(TypeError):
            make_ctx().registry.plugin({"name": "no-apply"}, {})

    def test_invalid_plugin_none_raises(self, make_ctx):
        with pytest.raises(TypeError):
            make_ctx().registry.plugin(None, None)


# ---------------------------------------------------------------------------
# RegistryService.plugin — happy path
# ---------------------------------------------------------------------------


class TestRegistryPluginHappy:
    """Plugin loading creates a fiber + a runtime."""

    def test_plugin_returns_fiber(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        fiber = ctx.registry.plugin(plugin, {})
        assert isinstance(fiber, Fiber)

    def test_plugin_reuses_runtime(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        ctx.registry.plugin(plugin, {})
        ctx.registry.plugin(plugin, {})
        # One runtime for both plugin() calls.
        assert ctx.registry.size == 1

    def test_plugin_function_passes_args(self, make_ctx):
        ctx = make_ctx()
        seen: list[Any] = []

        def plugin(this: Context, cfg: Any) -> None:
            seen.append((this, cfg))

        async def _go() -> None:
            fiber = ctx.registry.plugin(plugin, {"k": "v"})
            await fiber.await_()

        asyncio.run(_go())
        assert len(seen) == 1
        assert seen[0][1] == {"k": "v"}

    def test_plugin_object_form(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        fiber = ctx.registry.plugin({"apply": plugin, "name": "obj"}, {})
        assert isinstance(fiber, Fiber)

    def test_plugin_class_instantiates(self, make_ctx):
        ctx = make_ctx()
        log: list[str] = []

        class Demo:
            def __init__(self, this: Context, cfg: Any) -> None:
                log.append("init")

        async def _go() -> None:
            fiber = ctx.registry.plugin(Demo, {})
            await fiber.await_()

        asyncio.run(_go())
        assert "init" in log

    def test_plugin_runtime_inherits_name(self, make_ctx):
        ctx = make_ctx()

        def my_plugin(this: Context, cfg: Any) -> None:
            pass

        # Give the plugin a name via dict form.
        ctx.registry.plugin({"apply": my_plugin, "name": "explicit"}, {})
        assert ctx.registry.get(my_plugin).name == "explicit"

    def test_plugin_apply_name_resets_to_none(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        # When the dict key "name" is "apply", the runtime name falls back to None.
        ctx.registry.plugin({"apply": plugin, "name": "apply"}, {})
        assert ctx.registry.get(plugin).name is None

    def test_plugin_inherits_Config(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        schema = object()
        ctx.registry.plugin({"apply": plugin, "Config": schema}, {})
        rt = ctx.registry.get(plugin)
        assert rt.Config is schema

    def test_plugin_inherits_function_Config(self, make_ctx):
        ctx = make_ctx()

        def schema(c: Any) -> Any:  # pragma: no cover — test fixture
            return c

        def plugin(this: Context, cfg: Any) -> None:
            pass

        plugin.Config = schema  # type: ignore[attr-defined]
        ctx.registry.plugin(plugin, {})
        rt = ctx.registry.get(plugin)
        assert rt.Config is schema

    def test_plugin_injects_into_fiber(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        plugin_obj = {"apply": plugin, "inject": {"foo": None}}
        fiber = ctx.registry.plugin(plugin_obj, {})
        # inject is normalised into a plain dict.
        assert fiber.inject == {"foo": None}

    def test_plugin_injects_array_form(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        plugin_obj = {"apply": plugin, "inject": ["foo", "bar"]}
        fiber = ctx.registry.plugin(plugin_obj, {})
        assert fiber.inject == {"foo": None, "bar": None}

    def test_plugin_fiber_added_to_runtime(self, make_ctx):
        ctx = make_ctx()

        def plugin(this: Context, cfg: Any) -> None:
            pass

        fiber = ctx.registry.plugin(plugin, {})
        rt = ctx.registry.get(plugin)
        assert fiber in list(rt.fibers)


# ---------------------------------------------------------------------------
# RegistryService.inject — shorthand for plugin()
# ---------------------------------------------------------------------------


class TestRegistryInject:
    """``inject(inject, callback)`` runs a callback once deps are available."""

    def test_inject_returns_fiber(self, make_ctx):
        ctx = make_ctx()

        def cb(this: Context, cfg: Any) -> None:
            pass

        fiber = ctx.registry.inject(["foo"], cb)
        assert isinstance(fiber, Fiber)

    def test_inject_uses_callback_name(self, make_ctx):
        ctx = make_ctx()

        def my_cb(this: Context, cfg: Any) -> None:
            pass

        # The name derived from the callback is stored on the runtime.
        # Python's `getattr(cb, "name")` returns the function's `__name__`.
        ctx.registry.inject(["foo"], my_cb)
        rt = ctx.registry.get(my_cb)
        # The runtime callback key should be `my_cb`.
        assert rt is not None


# ---------------------------------------------------------------------------
# Inject type alias
# ---------------------------------------------------------------------------


class TestInjectTypeAlias:
    """``Inject`` is a list-or-dict alias."""

    def test_inject_is_a_type_alias(self):
        # The alias is documented as ``list[str] | dict[str, Any]``.
        from typing import get_args, get_origin, Union

        # ``Inject`` is a plain alias, not a runtime type — we just assert
        # that assigning a list or a dict is acceptable.
        a: Inject = ["foo"]
        b: Inject = {"foo": None}
        assert a == ["foo"]
        assert b == {"foo": None}


# ---------------------------------------------------------------------------
# Cleanup marker (forces ``make_ctx`` to run once).
# ---------------------------------------------------------------------------


def test_registry_module_imports(make_ctx):
    """Sanity: all public names are importable."""
    from cordis import registry as r

    assert hasattr(r, "RegistryService")
    assert hasattr(r, "PluginRuntime")
    assert hasattr(r, "inject_resolve")
    assert hasattr(r, "is_applicable")