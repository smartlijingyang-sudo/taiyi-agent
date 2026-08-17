"""Tests for cordis.disposer — Effect with reverse-order dispose."""

from __future__ import annotations

import pytest

from cordis.disposer import Effect


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


__all__ = ["TestEffect"]
