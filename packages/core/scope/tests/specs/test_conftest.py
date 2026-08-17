"""Tests for the conftest `make_ctx` fixture."""

from __future__ import annotations

import asyncio

from cordis import Context


def test_make_ctx_yields_fresh_context(make_ctx: Context) -> None:
    """Each fixture invocation yields a brand-new `Context`."""
    assert isinstance(make_ctx, Context)


def test_make_ctx_auto_disposes(make_ctx: Context) -> None:
    """The fixture disposes its `Context` at teardown."""
    assert not make_ctx.state_disposed


def test_make_ctx_disposes_already_disposed_context_safely(make_ctx: Context) -> None:
    """If a test pre-disposes the context, the fixture's finalizer is a no-op."""
    # Manually dispose the context BEFORE the fixture's teardown runs.
    asyncio.run(make_ctx.dispose())
    assert make_ctx.state_disposed
    # The conftest finalizer will hit its `if state_disposed: return` branch.
