"""`taiyi_core_agent.event` — contained agent notification helper.

1:1 port of ``emitAgentEvent`` from
`~/deepseek-harness/packages/core/agent/src/dispatch.ts`.

Public surface:

- :func:`emit_agent_event`

This module is split out from :mod:`taiyi_core_agent.dispatch` so the
one-shot notification helper is importable independently of the dispatcher
construction surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cordis import Context


__all__ = ["emit_agent_event"]


def emit_agent_event(
    ctx: Context,
    agent: Any,
    name: str,
    payload: Any,
) -> None:
    """Emit one contained agent notification without retaining a dispatcher.

    Mirrors upstream ``emitAgentEvent``. Useful for fire-and-forget
    notifications where the loop driver already has a fused dispatcher
    and a single notification has no hot-path allocation budget.
    """
    from taiyi_core_agent.dispatch import agent_events
    agent_events(ctx, agent).emit(name, payload)
