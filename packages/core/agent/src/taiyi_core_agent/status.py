"""`taiyi_core_agent.status` — agent lifecycle states.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/runtime-types.ts`
(``AgentStatus`` type alias).

Public surface:

- :data:`AgentStatus`
"""

from __future__ import annotations

from typing import Literal

__all__ = ["AgentStatus"]


# Mirrors upstream:
#
#   /** An agent's lifecycle state ... `idle` means no driver is active; `running` ... */
#   export type AgentStatus = 'idle' | 'running'
#
AgentStatus = Literal["idle", "running"]
