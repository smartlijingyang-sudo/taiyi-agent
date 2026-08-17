"""Shared pytest fixtures for taiyi-hmr test suite.

The HMR service integrates with the cordis context; we build a minimal
context per test and dispose it on teardown so watcher tasks do not
leak across tests.
"""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Callable, Iterator

import pytest
from cordis.context import Context


@pytest.fixture
def make_ctx() -> Iterator[Callable[[], Context]]:
    """Return a factory that mints a fresh ``Context``; teardown disposes each."""
    created: list[Context] = []

    def _factory() -> Context:
        ctx = Context()
        created.append(ctx)
        return ctx

    yield _factory

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
