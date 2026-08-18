"""Tests for `taiyi-core-agent` re-export surface (apply wrapper)."""

from __future__ import annotations

from typing import Any

import taiyi_core_agent.invariant as _invariant_module
from taiyi_core_agent import apply as apply_lazy


def test_apply_lazy_dispatches_to_invariant_apply(make_ctx) -> None:
    """`taiyi_core_agent.apply` forwards to `taiyi_core_agent.invariant.apply`."""
    captured: list[Any] = []

    def _spy(ctx: Any) -> Any:
        captured.append(ctx)
        return lambda: None

    original = _invariant_module.apply
    _invariant_module.apply = _spy  # type: ignore[assignment]
    try:
        result = apply_lazy(make_ctx)
        assert captured == [make_ctx]
        assert callable(result)
    finally:
        _invariant_module.apply = original  # type: ignore[assignment]


def test_apply_lazy_returns_invariant_disposable(make_ctx) -> None:
    """The lazy wrapper returns whatever `invariant.apply` returns."""
    sentinel = lambda: None  # noqa: E731
    original = _invariant_module.apply
    _invariant_module.apply = lambda _ctx: sentinel  # type: ignore[assignment]
    try:
        result = apply_lazy(make_ctx)
        assert result is sentinel
    finally:
        _invariant_module.apply = original  # type: ignore[assignment]


def test_apply_lazy_invokes_inner_module() -> None:
    """The lazy wrapper triggers a real install on the inner module."""
    _invariant_module.apply  # noqa: B018 — ensure symbol is bound
    # The lazy wrapper imports `_apply` from the invariant module.
    import importlib

    invariant_module = importlib.import_module("taiyi_core_agent.invariant")
    sentinel = lambda: None  # noqa: E731
    original = invariant_module.apply
    invariant_module.apply = lambda _ctx: sentinel  # type: ignore[assignment]
    try:
        ctx_factory = type("C", (), {})()
        result = apply_lazy(ctx_factory)  # type: ignore[arg-type]
        assert result is sentinel
    finally:
        invariant_module.apply = original  # type: ignore[assignment]
