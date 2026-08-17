"""Shared pytest fixtures for the `taiyi-core-agent` test suite."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from cordis import Context


@pytest.fixture
def make_ctx() -> Iterator[Context]:
    """Mint a fresh Cordis ``Context``; dispose at fixture teardown."""
    ctx = Context()
    yield ctx
    if ctx.state_disposed:
        return
    try:
        asyncio.run(ctx.dispose())
    except Exception:  # pragma: no cover — defensive
        pass


@pytest.fixture
def make_async_ctx():
    """Async factory yielding a fresh Cordis ``Context``; dispose on teardown."""
    contexts: list[Context] = []

    async def _factory() -> Context:
        ctx = Context()
        contexts.append(ctx)
        return ctx

    yield _factory

    async def _drain_all() -> None:
        for ctx in contexts:
            if ctx.state_disposed:
                continue
            try:
                await ctx.dispose()
            except Exception:  # pragma: no cover — defensive
                pass

    asyncio.run(_drain_all())
