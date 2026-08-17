"""Tests for `taiyi_core_scope.plugin` — the cordis plugin entry."""

from __future__ import annotations

import asyncio

from cordis import Context, Plugin

from taiyi_core_scope.plugin import setup


def test_setup_returns_plugin_instance() -> None:
    """`setup` is the cordis plugin entry; it must be a `Plugin` instance."""
    assert isinstance(setup, Plugin)
    assert setup.name == "scope"
    assert setup.inject == []


async def test_setup_installs_scope_surface_on_ctx() -> None:
    """`setup(ctx, config)` exposes the scope surface under `ctx.scope_lib`."""
    import pytest  # noqa: PLC0415

    ctx = Context()
    dispose = await setup.setup(ctx, {})
    surface = ctx.scope_lib  # type: ignore[attr-defined]
    assert isinstance(surface, dict)
    assert "create_scope" in surface
    assert "bind_scope_parent" in surface
    assert "scope_target" in surface
    # Cleanup
    dispose()
    # After dispose, `ctx.scope_lib` should be cleared.
    with pytest.raises(AttributeError):
        _ = ctx.scope_lib  # type: ignore[attr-defined]  # noqa: B018


async def test_setup_dispose_is_idempotent() -> None:
    """Calling the disposer twice does not raise."""
    ctx = Context()
    dispose = await setup.setup(ctx, {})
    dispose()
    dispose()  # second call should be a safe no-op


def test_setup_callable_directly() -> None:
    """`setup(ctx, config)` can be called as a plain function (not just as a Plugin)."""
    ctx = Context()

    async def _runner() -> None:
        dispose = await setup.setup(ctx, {})
        dispose()

    asyncio.run(_runner())
