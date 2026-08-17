"""Tests for `taiyi_core_session.plugin` — cordis plugin entry."""

from __future__ import annotations

import pytest
from cordis import Plugin

from taiyi_core_session.plugin import setup


def test_setup_is_a_plugin_instance() -> None:
    """The exported entry is a `cordis.Plugin`."""
    assert isinstance(setup, Plugin)
    assert setup.name == "session"


@pytest.mark.asyncio
async def test_setup_installs_sessions_on_ctx(make_ctx) -> None:
    """After setup, `ctx.sessions` is a `SessionStore`."""
    dispose = await setup.setup(make_ctx, {})
    store = make_ctx.sessions  # type: ignore[attr-defined]
    from taiyi_core_session.session import SessionStore

    assert isinstance(store, SessionStore)
    dispose()


@pytest.mark.asyncio
async def test_setup_dispose_clears_sessions(make_ctx) -> None:
    """After dispose, `ctx.sessions` is no longer accessible."""
    dispose = await setup.setup(make_ctx, {})
    dispose()
    with pytest.raises(AttributeError):
        _ = make_ctx.sessions  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_setup_runnable_directly_as_function(make_ctx) -> None:
    """`setup.setup(ctx, config)` can be called as a plain async function."""
    dispose = await setup.setup(make_ctx, {})
    assert dispose is not None
    dispose()
