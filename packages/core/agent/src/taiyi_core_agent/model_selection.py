"""`taiyi_core_agent.model_selection` — agent-scoped model selection.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/model-selection.ts`.

Public surface:

- :class:`ModelSelection`
- :class:`ModelSelectionRef`
- :func:`install_model_selection`
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cordis import Context

__all__ = [
    "ModelSelection",
    "ModelSelectionRef",
    "install_model_selection",
]


@dataclass(frozen=True)
class ModelSelection:
    """Complete provider, model, and optional reasoning effort selected for one live Agent."""

    provider: str
    model: str
    reasoningEffort: str | None = None  # noqa: N815 — upstream camelCase contract


@dataclass
class ModelSelectionRef:
    """Mutable model selection plus the value captured for the current step."""

    current: ModelSelection | None = None
    assembled: ModelSelection | None = None


def install_model_selection(
    agent_ctx: Context,
    selection: ModelSelectionRef,
) -> Callable[[], None]:
    """Couple one mutable selection to prompt assembly and request routing.

    Mirrors upstream `installModelSelection`. Prompt assembly snapshots the
    selected model before delegating, then applies its provider/model pair
    and effort to request config so a concurrent switch takes effect on a
    later step instead of splitting the two surfaces. An absent selected
    effort clears any inherited effort, restoring the selected model's
    provider/default behavior.

    Returns a disposer that unregisters both scoped waterfall listeners.
    """
    dispose_assembly = _register_assembly_listener(agent_ctx, selection)
    dispose_request = _register_request_listener(agent_ctx, selection)

    def _dispose() -> None:
        dispose_assembly()
        dispose_request()

    return _dispose


# ---------------------------------------------------------------------------
# Listener registration helpers
# ---------------------------------------------------------------------------


def _extract_nxt(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Callable[[], Any]:
    """Read the ``next`` callback from a cordis waterfall invocation.

    cordis binds the listener to the active context as the first
    positional argument; the ``next`` callback is delivered either as a
    trailing positional callable or as the ``nxt`` keyword. This helper
    detects both shapes and returns a no-op when none is present so
    callers can guard against test contexts that don't drive a full
    waterfall.
    """
    nxt: Callable[[], Any] | None = kwargs.get("nxt")
    if nxt is not None:
        return nxt
    if args and callable(args[-1]):  # pragma: no cover — defensive positional fallback
        return args[-1]
    return lambda: None  # pragma: no cover — defensive no-nxt fallback


def _register_assembly_listener(
    agent_ctx: Context,
    selection: ModelSelectionRef,
) -> Callable[[], bool]:
    """Register the ``system-prompt/assemble`` waterfall listener.

    Snapshots ``selection.current`` BEFORE awaiting ``next()`` so a
    concurrent switch scheduled by ``next()`` does not affect the assembly
    produced by this step.
    """

    async def _assemble_listener(*args: Any, **kwargs: Any) -> Any:
        nxt = _extract_nxt(args, kwargs)
        selected = selection.current
        assembled = await nxt()
        selection.assembled = selected
        if selected is None:
            return assembled
        try:
            variables = dict(assembled.get("variables", {}))
        except Exception:
            variables = {}
        variables["provider"] = selected.provider
        variables["model"] = selected.model
        if isinstance(assembled, dict):
            merged = dict(assembled)
            merged["variables"] = variables
            return merged
        try:
            assembled.variables = variables  # type: ignore[attr-defined]
            return assembled
        except Exception:  # pragma: no cover — defensive
            return assembled

    return agent_ctx.on(  # type: ignore[attr-defined]
        "system-prompt/assemble",
        _assemble_listener,
    )


def _register_request_listener(
    agent_ctx: Context,
    selection: ModelSelectionRef,
) -> Callable[[], bool]:
    """Register the ``agent/request`` waterfall listener.

    Applies the snapshot captured by :func:`_register_assembly_listener`
    to the resolved request configuration. An absent selection clears any
    inherited reasoning effort, restoring provider defaults.
    """

    async def _request_listener(*args: Any, **kwargs: Any) -> Any:
        nxt = _extract_nxt(args, kwargs)
        resolved = await nxt()
        selected = selection.assembled
        if selected is None:
            return resolved
        try:
            base = dict(resolved)
        except Exception:
            return resolved
        # Strip the inherited reasoning effort: upstream uses
        # ``const { reasoningEffort: _inheritedEffort, ...withoutInheritedEffort } = resolved``.
        base.pop("reasoningEffort", None)
        base["provider"] = selected.provider
        base["model"] = selected.model
        if selected.reasoningEffort is not None:
            base["reasoningEffort"] = selected.reasoningEffort
        return base

    return agent_ctx.on(  # type: ignore[attr-defined]
        "agent/request",
        _request_listener,
    )
