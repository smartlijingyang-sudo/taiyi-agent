"""`taiyi_core_agent.carrier` — agent scope carrier builder.

1:1 port of `agentCarrier` from
`~/deepseek-harness/packages/core/agent/src/dispatch.ts`.

Public surface:

- :func:`agent_carrier`

This module is split out from :mod:`taiyi_core_agent.dispatch` so the
carrier builder is importable independently of the dispatch surface
(mirrors the upstream location of ``agentCarrier`` next to the
fused dispatcher).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


__all__ = ["agent_carrier"]


def agent_carrier(agent: Any) -> Any:
    """Build the fused scope carrier for one agent subject.

    Mirrors upstream ``agentCarrier``. The carrier is a stateless routing
    object that :func:`taiyi_core_agent.dispatch.agent_events` accepts
    so callers (the loop driver) may build it once in the agent's
    constructor and reuse it for every dispatch, keeping the hot path
    allocation-free.
    """
    # Local import: ``taiyi_core_scope`` is provided by
    # ``taiyi-core-scope`` and importable independently.
    from taiyi_core_scope import scope_target
    return scope_target(agent, agent)
