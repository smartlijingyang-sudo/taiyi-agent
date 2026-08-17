"""`taiyi_core_agent.plugin` — cordis plugin entry.

1:1 port of `@deepseek-ai/dsh-agent`'s default export. Installs the
:class:`AgentRegistry` under ``ctx.agents``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cordis import Context, plugin

from taiyi_core_agent.registry import AgentRegistry

__all__ = ["setup"]


@plugin(name="agent", inject=[])
async def setup(ctx: Context, config: Any = None) -> Callable[[], None]:
    """Install the agent registry as ``ctx.agents`` and return its disposer."""
    # The ``AgentRegistry`` service installs itself under the ``agents``
    # service name when constructed; the returned disposer is the
    # auto-dispose disposer registered through ``cordis.Service``.
    registry = AgentRegistry(ctx)
    # Reflect provide so ``ctx.agents`` resolves to the constructed
    # registry (the registry's own __init__ already calls
    # ``ctx.reflect.provide("agents", self)``; the explicit call below
    # is the public surface entry for downstream plugins that import
    # only ``taiyi_core_agent.plugin.setup``).
    try:
        provide_dispose = ctx.reflect.provide("agents", registry)  # type: ignore[attr-defined]
    except RuntimeError:
        provide_dispose = lambda: None  # noqa: E731 — already-provided fallback

    async def _async_dispose() -> None:
        try:
            await registry.dispose()
        except Exception:  # pragma: no cover — defensive
            pass
        try:
            provide_dispose()
        except Exception:  # pragma: no cover — defensive
            pass

    def _dispose() -> Any:
        try:
            return _async_dispose()
        except Exception:  # pragma: no cover — defensive
            return None

    return _dispose
