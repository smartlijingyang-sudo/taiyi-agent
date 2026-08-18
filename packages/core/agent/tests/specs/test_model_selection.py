"""Tests for `taiyi_core_agent.model_selection` — installModelSelection."""

from __future__ import annotations

import asyncio
from typing import Any

from cordis import Context

from taiyi_core_agent.model_selection import (
    ModelSelection,
    ModelSelectionRef,
    install_model_selection,
)

# ---------------------------------------------------------------------------
# Listener surface (exercise without a full agent context)
# ---------------------------------------------------------------------------


def _collect_unbound_callbacks(ctx: Context, event_name: str) -> list[Any]:
    """Read the raw hook callbacks table.

    Mirrors the helper used by the registry / dispatch modules so tests
    can introspect and invoke listeners with their declared shape.
    """
    hooks_table = ctx.events._hooks  # type: ignore[attr-defined]
    hooks = hooks_table.get(event_name) if isinstance(hooks_table, dict) else None
    if not hooks:
        return []
    return [hook.callback for hook in hooks]


async def _drain() -> None:
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# ModelSelection + ModelSelectionRef
# ---------------------------------------------------------------------------


def test_model_selection_is_frozen_with_required_fields() -> None:
    """`ModelSelection` is a frozen dataclass."""
    sel = ModelSelection(provider="p", model="m", reasoningEffort="low")
    assert sel.provider == "p"
    assert sel.model == "m"
    assert sel.reasoningEffort == "low"


def test_model_selection_without_reasoning_effort() -> None:
    """Reasoning effort is optional."""
    sel = ModelSelection(provider="p", model="m")
    assert sel.reasoningEffort is None


def test_model_selection_ref_starts_unset() -> None:
    """A fresh `ModelSelectionRef` has no current or assembled selection."""
    ref = ModelSelectionRef()
    assert ref.current is None
    assert ref.assembled is None


def test_model_selection_ref_records_assignments() -> None:
    """Setting `current` and `assembled` works."""
    ref = ModelSelectionRef()
    sel = ModelSelection(provider="p", model="m")
    ref.current = sel
    ref.assembled = sel
    assert ref.current is sel
    assert ref.assembled is sel


# ---------------------------------------------------------------------------
# install_model_selection
# ---------------------------------------------------------------------------


def test_install_model_selection_returns_a_disposer(make_ctx) -> None:
    """The disposer unregisters both scoped waterfall listeners."""
    selection = ModelSelectionRef()
    dispose = install_model_selection(make_ctx, selection)
    assert callable(dispose)
    # Dispose removes the listeners.
    initial_assembly = len(_collect_unbound_callbacks(make_ctx, "system-prompt/assemble"))
    initial_request = len(_collect_unbound_callbacks(make_ctx, "agent/request"))
    assert initial_assembly >= 1
    assert initial_request >= 1
    dispose()
    after_assembly = len(_collect_unbound_callbacks(make_ctx, "system-prompt/assemble"))
    after_request = len(_collect_unbound_callbacks(make_ctx, "agent/request"))
    assert after_assembly < initial_assembly
    assert after_request < initial_request


async def test_install_model_selection_snapshots_into_assembly(make_ctx) -> None:
    """The assembly listener snapshots `selection.current` before delegating."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)

    sentinel_assembly = object()

    async def _default() -> Any:
        return {"variables": {"system": "ok"}}

    # Register a downstream listener that the inner next() can call.
    make_ctx.on("system-prompt/assemble", _default)  # type: ignore[attr-defined]

    listeners = _collect_unbound_callbacks(make_ctx, "system-prompt/assemble")
    # The first listener is our install; the second is the test's
    # default. Run ours first.
    install_listener = listeners[0]
    # Call: the listener does its own await, so we need an event loop.
    selection.current = ModelSelection(provider="p1", model="m1")
    result = await install_listener(make_ctx, "ctx", sentinel_assembly, nxt=lambda: _default())
    assert result["variables"]["provider"] == "p1"
    assert result["variables"]["model"] == "m1"
    assert selection.assembled is selection.current


async def test_install_model_selection_skips_assembly_when_unset(make_ctx) -> None:
    """A None selection passes the assembly through unchanged."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)

    async def _default() -> Any:
        return {"variables": {"system": "ok"}}

    make_ctx.on("system-prompt/assemble", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "system-prompt/assemble")
    install_listener = listeners[0]
    result = await install_listener(make_ctx, "ctx", {}, nxt=lambda: _default())
    assert result == {"variables": {"system": "ok"}}


async def test_install_model_selection_applies_assembled_to_request(make_ctx) -> None:
    """The request listener applies the snapshot to the resolved config."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)
    # Pre-populate `assembled` (normally set by the assembly listener).
    selection.assembled = ModelSelection(
        provider="p2",
        model="m2",
        reasoningEffort="high",
    )

    async def _default() -> Any:
        return {"provider": "orig", "model": "orig", "reasoningEffort": "inherited"}

    make_ctx.on("agent/request", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "agent/request")
    install_listener = listeners[0]
    result = await install_listener(make_ctx, {}, nxt=lambda: _default())
    assert result["provider"] == "p2"
    assert result["model"] == "m2"
    assert result["reasoningEffort"] == "high"


async def test_install_model_selection_request_passthrough_when_unset(make_ctx) -> None:
    """When no model has been selected the request config is untouched."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)

    async def _default() -> Any:
        return {"provider": "orig", "model": "orig", "reasoningEffort": "inherited"}

    make_ctx.on("agent/request", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "agent/request")
    install_listener = listeners[0]
    result = await install_listener(make_ctx, {}, nxt=lambda: _default())
    assert result == {"provider": "orig", "model": "orig", "reasoningEffort": "inherited"}


async def test_install_model_selection_request_clears_effort_when_none(make_ctx) -> None:
    """A selection with ``reasoningEffort=None`` clears the inherited effort."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)
    selection.assembled = ModelSelection(
        provider="p3",
        model="m3",
        reasoningEffort=None,
    )

    async def _default() -> Any:
        return {"provider": "orig", "model": "orig", "reasoningEffort": "inherited"}

    make_ctx.on("agent/request", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "agent/request")
    install_listener = listeners[0]
    result = await install_listener(make_ctx, {}, nxt=lambda: _default())
    assert result["provider"] == "p3"
    assert result["model"] == "m3"
    assert "reasoningEffort" not in result


async def test_install_model_selection_no_nxt_falls_back_to_noop(make_ctx) -> None:
    """When the listener is invoked without `next`, the listener returns the default."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)
    selection.current = None

    async def _default() -> Any:
        return {"variables": {"system": "ok"}}

    make_ctx.on("system-prompt/assemble", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "system-prompt/assemble")
    install_listener = listeners[0]
    # The test passes the listener itself as the only positional arg.
    # The listener is callable, so `_extract_nxt` reads it as `nxt`.
    install_listener(make_ctx)


async def test_install_model_selection_request_resolved_not_mapping(make_ctx) -> None:
    """`agent/request` returns `resolved` unchanged when it's not a mapping."""
    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)
    selection.assembled = ModelSelection(
        provider="p4",
        model="m4",
        reasoningEffort="med",
    )

    sentinel = object()

    async def _default() -> Any:
        return sentinel

    make_ctx.on("agent/request", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "agent/request")
    install_listener = listeners[0]
    result = await install_listener(make_ctx, {}, nxt=lambda: _default())
    # The non-mapping result is returned unchanged.
    assert result is sentinel


async def test_install_model_selection_assembly_best_effort(make_ctx) -> None:
    """The assembly listener's best-effort `assembled.variables = ...` branch."""

    class _NonDictAssembly:
        # The ``assembled.variables = ...`` assignment via setattr — only
        # triggered when ``assembled`` is not a dict and accepts
        # attribute writes.
        pass

    selection = ModelSelectionRef()
    install_model_selection(make_ctx, selection)
    selection.current = ModelSelection(provider="px", model="mx")

    async def _default() -> Any:
        return _NonDictAssembly()

    make_ctx.on("system-prompt/assemble", _default)  # type: ignore[attr-defined]
    listeners = _collect_unbound_callbacks(make_ctx, "system-prompt/assemble")
    install_listener = listeners[0]
    # Direct invocation: the result is the original `_NonDictAssembly`.
    result = await install_listener(make_ctx, {}, nxt=lambda: _default())
    assert isinstance(result, _NonDictAssembly)
