"""Shared pytest fixtures for taiyi-timer test suite.

Provides a `make_ctx` factory that mints a fresh `cordis.Context` and
attempts best-effort cleanup in the fixture finalizer. Tests that build
their own `TimerService` should still `await ctx.dispose()` explicitly to
cancel pending timers.
"""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Callable, Iterator

import pytest


@pytest.fixture
def make_ctx() -> Iterator[Callable[[], object]]:
    """Yield a factory that mints a fresh `Context` (tests manage teardown)."""
    created: list[object] = []

    def _factory():  # type: ignore[no-untyped-def]
        from cordis import Context

        ctx = Context()
        created.append(ctx)
        return ctx

    yield _factory

    # Best-effort cleanup for tests that did not await dispose themselves.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for ctx in created:
            state = getattr(ctx, "state_disposed", False)
            if state:
                continue
            try:
                dispose = getattr(ctx, "dispose", None)
                if dispose is None:
                    continue
                result = dispose()
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
            except Exception:  # pragma: no cover — best-effort cleanup only
                pass
