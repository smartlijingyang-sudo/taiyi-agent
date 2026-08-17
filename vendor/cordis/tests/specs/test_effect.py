"""Tests for cordis.disposer — Effect with reverse-order dispose."""

from __future__ import annotations

import inspect

import pytest

from cordis.disposer import Disposer, Effect, _as_func, dispose_all, run_disposer


class TestEffect:
    """Effect tests — single value, iterable, reverse order, dedup."""

    async def test_effect_single_value(self):
        """Single callable is treated as one disposer."""
        disposed = []

        def cleanup():
            disposed.append("single")

        effect = Effect.of(cleanup)
        assert len(effect.dispose_fns) == 1

        # Execute the disposer
        await effect.__disposer__()
        assert disposed == ["single"]

    async def test_effect_iterable(self):
        """List of callables creates multiple disposers."""
        disposed = []

        def cleanup1():
            disposed.append("1")

        def cleanup2():
            disposed.append("2")

        def cleanup3():
            disposed.append("3")

        effect = Effect.of([cleanup1, cleanup2, cleanup3])
        assert len(effect.dispose_fns) == 3

        await effect.__disposer__()
        # Reverse order: 3, 2, 1
        assert disposed == ["3", "2", "1"]

    async def test_effect_reverse_order(self):
        """Disposers run in reverse registration order (LIFO)."""
        order = []

        def first():
            order.append("first")

        def second():
            order.append("second")

        def third():
            order.append("third")

        effect = Effect.of([first, second, third])
        await effect.__disposer__()

        assert order == ["third", "second", "first"]

    async def test_effect_dedup(self):
        """Same function registered multiple times only runs once."""
        disposed = []

        def cleanup():
            disposed.append("dedup")

        # Register the same function 3 times
        effect = Effect.of([cleanup, cleanup, cleanup])
        await effect.__disposer__()

        # Should only run once due to dedup by function identity
        assert disposed == ["dedup"]

    async def test_effect_none(self):
        """None creates an empty effect."""
        effect = Effect.of(None)
        assert len(effect.dispose_fns) == 0

        # Should not raise
        await effect.__disposer__()

    async def test_effect_async_callable(self):
        """Async callables are supported."""
        disposed = []

        async def async_cleanup():
            disposed.append("async")

        effect = Effect.of(async_cleanup)
        await effect.__disposer__()

        assert disposed == ["async"]

    async def test_effect_mixed_sync_async(self):
        """Mix of sync and async disposers."""
        disposed = []

        def sync_cleanup():
            disposed.append("sync")

        async def async_cleanup():
            disposed.append("async")

        effect = Effect.of([sync_cleanup, async_cleanup])
        await effect.__disposer__()

        # Reverse order: async first, then sync
        assert disposed == ["async", "sync"]

    async def test_effect_empty_list(self):
        """Empty list creates an empty effect."""
        effect = Effect.of([])
        assert len(effect.dispose_fns) == 0

        await effect.__disposer__()


class TestRunDisposer:
    """``run_disposer`` supports sync / async / iterable results."""

    async def test_run_sync_callable(self):
        """Sync callable runs without await."""

        def cleanup():
            cleanup.called = True

        await run_disposer(Disposer(func=cleanup))
        assert cleanup.called is True

    async def test_run_async_callable(self):
        """Async callable is awaited."""

        async def cleanup():
            cleanup.called = True

        await run_disposer(Disposer(func=cleanup))
        assert cleanup.called is True

    async def test_run_async_iterable(self):
        """Async iterable of disposers is drained."""
        calls = []

        async def agen():
            yield lambda: calls.append("1")
            yield lambda: calls.append("2")

        # The disposer function returns an async generator.
        def disposer_fn():
            return agen()

        await run_disposer(Disposer(func=disposer_fn))

    async def test_run_sync_iterable_of_disposers(self):
        """Sync iterable is drained (the values are not invoked as disposers)."""
        # The implementation drains the iterable but doesn't call each value
        # (mirrors upstream ``runDisposer`` behavior).
        # We just verify that iteration completes without error.

        def disposer_fn():
            return iter([1, 2, 3])

        # No assertion needed beyond completion.
        await run_disposer(Disposer(func=disposer_fn))

    async def test_run_string_passes_through(self):
        """String result is iterable but treated as a passthrough (no iteration)."""

        def disposer_fn():
            return "not-iterated"

        # run_disposer should NOT iterate the string.
        await run_disposer(Disposer(func=disposer_fn))


class TestDisposeAll:
    """``dispose_all`` runs each caller's disposer."""

    async def test_dispose_all_sync_list(self):
        calls = []

        def make(value):
            def fn():
                calls.append(value)
            return fn

        await dispose_all([make(1), make(2), make(3)])
        assert calls == [1, 2, 3]

    async def test_dispose_all_with_async(self):
        """Async callables in the iter are awaited."""
        calls = []

        def sync():
            calls.append("sync")

        async def async_fn():
            calls.append("async")

        await dispose_all([sync, async_fn])
        assert calls == ["sync", "async"]


class TestAsFunc:
    """``_as_func`` adapts a raw value to a disposer."""

    def test_as_func_with_callable(self):
        """Callable value is returned as-is."""

        def my_fn():
            return "result"

        assert _as_func(my_fn) is my_fn

    def test_as_func_with_non_callable(self):
        """Non-callable value is wrapped in a no-op lambda."""
        sentinel = object()
        fn = _as_func(sentinel)
        # Calling the wrapped fn should not raise; returns the original value.
        result = fn()
        assert result is sentinel


class TestEffectOfPassthrough:
    """``Effect.of`` returns the value as-is when it's already an Effect."""

    def test_effect_of_returns_same_effect(self):
        """Effect.of(effect) returns the same effect (identity)."""
        original = Effect.of(lambda: None)
        result = Effect.of(original)
        assert result is original


class TestDisposeAllAsyncIter:
    """``dispose_all`` supports async iterable."""

    async def test_dispose_all_async_iterable(self):
        """Async iterable of disposers is awaited."""
        calls = []

        def make(value):
            def fn():
                calls.append(value)
            return fn

        async def agen():
            yield make(1)
            yield make(2)

        await dispose_all(agen())
        assert calls == [1, 2]


__all__ = ["TestEffect"]
