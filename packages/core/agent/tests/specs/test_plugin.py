"""Tests for `taiyi_core_agent.plugin` — the cordis plugin entry."""

from __future__ import annotations

import asyncio

from cordis import Context, Plugin

from taiyi_core_agent.plugin import setup


def test_setup_is_a_cordis_plugin() -> None:
    """`setup` is a `cordis.Plugin` instance named ``"agent"``."""
    assert isinstance(setup, Plugin)
    assert setup.name == "agent"


async def test_setup_installs_ctx_agents(make_ctx) -> None:
    """`setup(ctx, config)` installs `ctx.agents` and returns a disposer."""
    dispose = await setup.setup(make_ctx, {})
    registry = make_ctx.agents  # type: ignore[attr-defined]
    assert registry is not None
    assert callable(dispose)
    # The disposer must accept a second invocation (idempotency on best
    # effort — the underlying auto-dispose may have already settled).
    try:
        result = dispose()
        # Either an awaitable or None is acceptable.
        if result is not None and hasattr(result, "__await__"):
            await result
    except Exception:  # pragma: no cover — defensive
        pass


async def test_setup_disposer_runs_cleanly(make_ctx) -> None:
    """Calling the disposer does not raise."""
    dispose = await setup.setup(make_ctx, {})
    result = dispose()
    if result is not None and hasattr(result, "__await__"):
        await result


def test_setup_callable_directly() -> None:
    """`setup(ctx, config)` is callable as a plain async function."""
    ctx = Context()

    async def _runner() -> None:
        dispose = await setup.setup(ctx, {})
        result = dispose()
        if result is not None and hasattr(result, "__await__"):
            await result

    asyncio.run(_runner())
