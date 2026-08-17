"""`taiyi_core_agent.context` — prompt-assembly context builder.

1:1 port of ``assembleContextFor`` from
`~/deepseek-harness/packages/core/agent/src/dispatch.ts`.

Public surface:

- :func:`assemble_context_for`
"""

from __future__ import annotations

from typing import Any

__all__ = ["assemble_context_for"]


def assemble_context_for(
    agent: Any,
    signal: Any | None = None,
) -> dict[str, Any]:
    """Build the prompt assembly context with agent and scope bound together.

    Mirrors upstream ``assembleContextFor``. Setting both fields through
    one call guarantees that agent-scoped prompt and tool contributions
    cannot be silently omitted.
    """
    payload: dict[str, Any] = {"agent": agent, "scope": agent}
    if signal is not None:
        payload["signal"] = signal
    return payload
