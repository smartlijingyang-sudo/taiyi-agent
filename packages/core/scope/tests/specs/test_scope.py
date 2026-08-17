"""1:1 tests for `taiyi_core_scope.scope` (mirrors `~/deepseek-harness/packages/core/scope/src/index.ts`)."""

from __future__ import annotations

from typing import Any

import pytest
from cordis import Context

from taiyi_core_scope.scope import (
    _SCOPE_KEY_ATTR,
    CreateScopeOptions,
    Scope,
    bind_scope_parent,
    carrier_key_of,
    create_scope,
    is_scope_carrier,
    scope_chain_of,
    scope_of,
    scope_parent_of,
    scope_target,
)

# ---------------------------------------------------------------------------
# ScopeKey, bind_scope_parent, scope_parent_of, scope_chain_of
# ---------------------------------------------------------------------------


def test_scope_key_is_opaque_object(make_ctx: Context) -> None:
    """A ScopeKey is any opaque object whose identity is the comparison."""
    a, b = object(), object()
    assert a != b
    # identity-compared (a is a)
    assert scope_parent_of(a) is None


def test_bind_scope_parent_then_read(make_ctx: Context) -> None:
    parent, child = object(), object()
    bind_scope_parent(child, parent)
    assert scope_parent_of(child) is parent


def test_bind_scope_parent_rejects_double_bind(make_ctx: Context) -> None:
    parent1, parent2, child = object(), object(), object()
    bind_scope_parent(child, parent1)
    with pytest.raises(RuntimeError, match="already bound"):
        bind_scope_parent(child, parent2)


def test_bind_scope_parent_rejects_cycle(make_ctx: Context) -> None:
    a, b = object(), object()
    # a → b → a would cycle
    bind_scope_parent(b, a)
    with pytest.raises(RuntimeError, match="cycle"):
        bind_scope_parent(a, b)


def test_bind_scope_parent_returns_rebind_handle(make_ctx: Context) -> None:
    a, b, c = object(), object(), object()
    bind_scope_parent(b, a)
    binding = bind_scope_parent(c, a)
    binding.rebind(b)
    assert scope_parent_of(c) is b


def test_rebind_rejects_cycle(make_ctx: Context) -> None:
    a, b = object(), object()
    bind_scope_parent(b, a)
    binding = bind_scope_parent(a, object())
    with pytest.raises(RuntimeError, match="cycle"):
        binding.rebind(b)


def test_scope_chain_of_returns_nearest_first(make_ctx: Context) -> None:
    a, b, c = object(), object(), object()
    bind_scope_parent(b, a)
    bind_scope_parent(c, b)
    chain = scope_chain_of(c)
    assert chain == [c, b, a]


def test_scope_chain_of_undefined_is_empty(make_ctx: Context) -> None:
    assert scope_chain_of(None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# create_scope, Scope, scope_of
# ---------------------------------------------------------------------------


def test_create_scope_returns_scope_with_ctx(make_ctx: Context) -> None:
    key = object()
    scope = create_scope(make_ctx, key)
    assert isinstance(scope, Scope)
    assert scope.ctx is not make_ctx
    assert scope_of(scope.ctx) is key


def test_scope_of_unscoped_context_is_none(make_ctx: Context) -> None:
    assert scope_of(make_ctx) is None


def test_create_scope_with_parent_binds_before_use(make_ctx: Context) -> None:
    parent_key, key = object(), object()
    scope = create_scope(make_ctx, key, CreateScopeOptions(parent=parent_key))
    assert scope_of(scope.ctx) is key
    assert scope_parent_of(key) is parent_key


def test_scope_dispose_quiesces_fiber(make_ctx: Context) -> None:
    key = object()
    scope = create_scope(make_ctx, key)
    # Dispose twice; second call should be a no-op (cached promise).
    import asyncio

    asyncio.run(scope.dispose())
    asyncio.run(scope.dispose())  # should not raise


# ---------------------------------------------------------------------------
# scope_target, is_scope_carrier, carrier_key_of
# ---------------------------------------------------------------------------


def test_scope_target_carrier_passes_filter_for_matching_key(make_ctx: Context) -> None:
    key = object()
    base = object()
    carrier = scope_target(base, key)
    # Tag carrier's ctx with `key`
    tagged_ctx = make_ctx.extend({_SCOPE_KEY_ATTR: key})
    filter_fn = getattr(carrier, "cordis.filter")
    assert filter_fn(tagged_ctx) is True


def test_scope_target_carrier_rejects_non_matching_key(make_ctx: Context) -> None:
    carrier_key, other_key = object(), object()
    base = object()
    carrier = scope_target(base, carrier_key)
    tagged_ctx = make_ctx.extend({_SCOPE_KEY_ATTR: other_key})
    filter_fn = getattr(carrier, "cordis.filter")
    assert filter_fn(tagged_ctx) is False


def test_scope_target_carrier_accepts_ancestor_tag(make_ctx: Context) -> None:
    parent_key, child_key = object(), object()
    base = object()
    carrier = scope_target(base, child_key)
    bind_scope_parent(child_key, parent_key)
    tagged_ctx = make_ctx.extend({_SCOPE_KEY_ATTR: parent_key})
    filter_fn = getattr(carrier, "cordis.filter")
    assert filter_fn(tagged_ctx) is True


def test_scope_target_carrier_rejects_descendant_tag(make_ctx: Context) -> None:
    parent_key, child_key = object(), object()
    base = object()
    carrier = scope_target(base, parent_key)
    bind_scope_parent(child_key, parent_key)
    tagged_ctx = make_ctx.extend({_SCOPE_KEY_ATTR: child_key})
    filter_fn = getattr(carrier, "cordis.filter")
    assert filter_fn(tagged_ctx) is False


def test_scope_target_carrier_admits_untagged_context(make_ctx: Context) -> None:
    key = object()
    base = object()
    carrier = scope_target(base, key)
    # `make_ctx` itself has no scope tag
    filter_fn = getattr(carrier, "cordis.filter")
    assert filter_fn(make_ctx) is True


def test_is_scope_carrier_true_for_carrier(make_ctx: Context) -> None:
    base = object()
    carrier = scope_target(base, object())
    assert is_scope_carrier(carrier) is True


def test_is_scope_carrier_false_for_plain_object(make_ctx: Context) -> None:
    assert is_scope_carrier(object()) is False
    assert is_scope_carrier(None) is False
    assert is_scope_carrier(42) is False
    assert is_scope_carrier("string") is False


def test_carrier_key_of_returns_key(make_ctx: Context) -> None:
    key = object()
    carrier = scope_target(object(), key)
    assert carrier_key_of(carrier) is key


def test_carrier_key_of_unkeyed_returns_none(make_ctx: Context) -> None:
    carrier = scope_target(object(), None)
    assert carrier_key_of(carrier) is None


def test_carrier_key_of_non_carrier_returns_none(make_ctx: Context) -> None:
    assert carrier_key_of(object()) is None
    assert carrier_key_of(None) is None


def test_scope_target_preserves_base_filter(make_ctx: Context) -> None:
    """`base.cordis.filter` must still run; if it returns False, carrier rejects too."""
    calls: list[Context] = []

    def _base_filter(ctx: Context) -> bool:
        calls.append(ctx)
        return False

    class _Base:
        pass

    base = _Base()
    object.__setattr__(base, "cordis.filter", _base_filter)
    carrier = scope_target(base, object())
    filter_fn = getattr(carrier, "cordis.filter")
    assert filter_fn(make_ctx) is False
    assert calls == [make_ctx]


def test_scope_target_base_filter_returning_true_lets_chain_decide(make_ctx: Context) -> None:
    """When the base filter admits, the chain check decides the outcome."""

    def _base_filter(ctx: Context) -> bool:  # noqa: ARG001
        return True

    class _Base:
        pass

    base = _Base()
    object.__setattr__(base, "cordis.filter", _base_filter)
    carrier = scope_target(base, object())
    filter_fn = getattr(carrier, "cordis.filter")
    # No tag on `make_ctx` → carrier admits
    assert filter_fn(make_ctx) is True


def test_scope_target_delegates_arbitrary_attributes(make_ctx: Context) -> None:
    """`__getattr__` proxies every attribute except `cordis.filter` to `base`."""

    class _Base:
        custom_marker = "abc"

    carrier: Any = scope_target(_Base(), object())
    assert carrier.custom_marker == "abc"


def test_scope_target_base_filter_exception_is_swallowed(make_ctx: Context) -> None:
    """A base filter that raises must not crash dispatch (return False)."""

    def _bad_filter(ctx: Context) -> bool:  # noqa: ARG001
        raise RuntimeError("nope")

    class _Base:
        pass

    base = _Base()
    object.__setattr__(base, "cordis.filter", _bad_filter)
    carrier = scope_target(base, object())
    filter_fn = getattr(carrier, "cordis.filter")
    # The defensive try/except catches the exception and returns False.
    assert filter_fn(make_ctx) is False


def test_scope_dispose_propagates_fiber_errors(make_ctx: Context) -> None:
    """If the raw `fiber.dispose()` raises, `dispose()` re-raises the same error."""
    import asyncio

    class _BadFiber:
        def dispose(self) -> None:
            raise RuntimeError("fiber-bomb")

        inertia = None

    bad_fiber = _BadFiber()
    scope_obj = Scope(make_ctx, bad_fiber.dispose, bad_fiber)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="fiber-bomb"):
        asyncio.run(scope_obj.dispose())


async def test_quiesce_fiber_swallows_inertia_failure() -> None:
    """A pending inertia that raises must be swallowed by `_quiesce_fiber`."""
    from taiyi_core_scope.scope import _quiesce_fiber

    class _AwaitableFailing:
        def __await__(self) -> Any:
            raise RuntimeError("inertia-bomb")

    class _FiberWithBadInertia:
        def dispose(self) -> None:
            return None

        @property
        def inertia(self) -> _AwaitableFailing:
            return _AwaitableFailing()

    # The function should swallow the inertia error and return.
    await _quiesce_fiber(_FiberWithBadInertia())  # type: ignore[arg-type]


async def test_quiesce_fiber_awaits_async_dispose() -> None:
    """`_quiesce_fiber` awaits `fiber.dispose()` when it returns an awaitable."""
    from taiyi_core_scope.scope import _quiesce_fiber

    class _FiberWithAwaitableDispose:
        inertia = None

        async def dispose(self) -> None:
            return None

    await _quiesce_fiber(_FiberWithAwaitableDispose())  # type: ignore[arg-type]


async def test_quiesce_fiber_handles_sync_dispose() -> None:
    """`_quiesce_fiber` runs `fiber.dispose()` when it returns synchronously."""
    from taiyi_core_scope.scope import _quiesce_fiber

    class _FiberWithSyncDispose:
        inertia = None

        def dispose(self) -> None:
            return None

    await _quiesce_fiber(_FiberWithSyncDispose())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Re-export the private sentinel used by `scope_of(ctx)` so tests can tag
# contexts without going through `create_scope` (which requires a fiber).
__all__ = []  # noqa: F822
