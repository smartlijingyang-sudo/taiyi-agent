"""Shared pytest fixtures for `taiyi-loader` test suite.

Mirrors the pattern in `taiyi-cordis/tests/conftest.py`. Each fixture mints a
fresh `Context` and ensures it is disposed at teardown.
"""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Callable, Iterator
from typing import Any

import pytest


@pytest.fixture
def make_ctx() -> Iterator[Callable[[], Any]]:
    """Return a factory that mints a fresh `cordis.Context`.

    Cleanup runs each spawned context through ``ctx.dispose()`` (synchronously,
    via ``asyncio.run``) so test isolation matches `taiyi-cordis` conventions.
    """
    created: list[Any] = []

    def _factory() -> Any:
        from cordis.context import Context as _Context

        ctx = _Context()
        created.append(ctx)
        return ctx

    yield _factory

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for ctx in created:
            if getattr(ctx, "state_disposed", False):
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


@pytest.fixture
def loader_ctx(make_ctx: Callable[[], Any]) -> Any:
    """Mint a fresh `Context` and register a `taiyi-loader` `Loader` on it.

    Tests that exercise the loader API reuse this fixture; nothing about
    the fixture is mandatory — tests that need a bare context should use
    ``make_ctx`` directly.
    """
    from loader import Loader

    ctx = make_ctx()
    loader = Loader(ctx)
    return ctx, loader
