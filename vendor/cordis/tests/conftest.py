"""Shared pytest fixtures for taiyi-cordis test suite.

`make_ctx` is implemented as the framework grows; the import is resolved
lazily so that conftest parsing succeeds even before Task 1.2 lands.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest


@pytest.fixture
def make_ctx() -> Iterator[Callable[[], object]]:
    """Return a factory that mints a fresh `Context` (caller manages teardown).

    Filled in once Task 1.2 implements `cordis.context.Context`.
    """
    created: list[object] = []

    def _factory():  # type: ignore[no-untyped-def]
        from cordis.context import Context as _Context

        ctx = _Context()
        created.append(ctx)
        return ctx

    yield _factory

    # Best-effort cleanup for tests that did not await dispose themselves.
    import asyncio

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
