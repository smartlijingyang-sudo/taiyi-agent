"""Shared pytest fixtures for `taiyi-runtime-diagnostics-invariants` test suite."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from cordis import Context


@pytest.fixture
def make_ctx() -> Iterator[Context]:
    """Mint a fresh Cordis `Context`; auto-disposed at fixture teardown."""
    ctx = Context()
    yield ctx
    try:
        if not ctx.state_disposed:
            asyncio.run(ctx.dispose())
    except Exception:  # pragma: no cover — defensive
        pass
