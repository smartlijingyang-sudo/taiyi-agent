"""Shared pytest fixtures for taiyi-include tests."""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Callable, Iterator

import pytest


@pytest.fixture
def make_ctx() -> Iterator[Callable[[], object]]:
    """Factory for a fresh ``Context`` (caller manages teardown)."""
    created: list[object] = []

    def _factory():  # type: ignore[no-untyped-def]
        from cordis.context import Context as _Context

        ctx = _Context()
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
            except Exception:
                pass
