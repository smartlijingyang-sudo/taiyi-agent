"""`taiyi_core_agent.dispatch` — agent-scoped dispatch + prompt assembly.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/dispatch.ts`.

Public surface:

- :func:`agent_carrier` — build the scope carrier for one agent.
- :func:`agent_events` — fused dispatcher that couples an agent subject to
  its scope carrier (kept allocation-free in the loop driver).
- :func:`emit_agent_event` — fire-and-forget notification without
  retaining the dispatcher.
- :func:`assemble_context_for` — build the prompt-assembly context with
  agent and scope bound together.

The upstream :class:`AgentSubjectEvent` / :class:`AgentEventDispatch` type
aliases are exposed as a :data:`AgentSubjectEvent` keyword-only narrowing
plus a runtime :data:`AGENT_SUBJECT_EVENT_NAMES` constant. The
:class:`AgentEventDispatch` Protocol keeps static-checkers happy while the
runtime uses duck-typed dicts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cordis import Context


__all__ = [
    "agent_carrier",
    "agent_events",
    "emit_agent_event",
    "assemble_context_for",
    "AgentEventDispatch",
    "AGENT_SUBJECT_EVENT_NAMES",
]


# Names whose first parameter (after ``this: Scoped<Agent>``) is the
# ``Payload`` carrying ``{agent: Agent}``. Mirrors the runtime filter
# applied by upstream ``AgentSubjectEvent`` — its type-level conditional
# cascade has no Python equivalent; the names listed here are the same
# string set returned by the upstream type alias.
AGENT_SUBJECT_EVENT_NAMES: tuple[str, ...] = (
    "agent/created",
    "agent/disposed",
    "agent/status",
    "agent/inbox/inserted",
    "agent/inbox/claimed",
    "agent/inbox/discarded",
    "agent/session-start",
    "agent/pre-step",
    "agent/request",
    "agent/request-error",
    "agent/turn-stopping",
    "agent/error",
)


class AgentEventDispatch:
    """Fused dispatcher returned by :func:`agent_events`.

    Mirrors upstream ``AgentEventDispatch``. The :meth:`emit` method
    injects the bound agent into every payload (``{...payload, agent}``)
    so listeners reading ``payload.agent`` see the exact subject without
    trusting callers.
    """

    __slots__ = ("_emit", "_serial", "_waterfall")

    def __init__(
        self,
        emit_fn: Callable[[str, Any], None],
        serial_fn: Callable[..., Any],
        waterfall_fn: Callable[..., Any],
    ) -> None:
        self._emit = emit_fn
        self._serial = serial_fn
        self._waterfall = waterfall_fn

    def emit(self, name: str, payload: Any) -> None:
        self._emit(name, payload)

    async def serial(self, name: str, payload: Any) -> Any:
        return await self._serial(name, payload)

    def waterfall(self, name: str, payload: Any, *rest: Any) -> Any:
        return self._waterfall(name, payload, *rest)


def agent_carrier(agent: Any) -> Any:
    """Build the fused scope carrier for one agent subject.

    Mirrors upstream `agentCarrier`: a stateless routing object that
    :func:`agent_events` accepts so callers that dispatch repeatedly for
    the same agent (the loop driver) can build it once in the agent's
    constructor and reuse it, keeping hot-path dispatches
    allocation-free.
    """
    from taiyi_core_scope import scope_target
    return scope_target(agent, agent)


def agent_events(
    ctx: "Context",
    agent: Any,
    carrier: Any | None = None,
) -> AgentEventDispatch:
    """Build a dispatcher that couples the agent subject to its scope carrier.

    Mirrors upstream ``agentEvents``. The fused dispatcher injects the
    bound agent into every payload so the subject and the scope key
    cannot diverge.
    """
    if carrier is None:
        carrier = agent_carrier(agent)

    # Bound local copies for closure capture (avoids global lookups in
    # the hot path, mirroring the loop's reuse pattern).
    bound_ctx = ctx
    bound_agent = agent
    bound_carrier = carrier

    def _fused(payload: Any) -> dict[str, Any]:
        """Inject the agent into the caller-supplied payload.

        The spread comes first so a structurally acceptable payload that
        happens to carry an ``agent`` field can never override the
        injected subject.
        """
        if isinstance(payload, dict):
            merged = dict(payload)
            merged["agent"] = bound_agent
            return merged
        return {"agent": bound_agent, "other": payload}

    def _emit(name: str, payload: Any) -> None:
        # Mirrors upstream ``agentEvents.emit``: Cordis's ``Array.map``
        # invocation starves later listeners on a synchronous throw and
        # discards returned promises. The agent notifications are
        # non-vetoing, so we resolve the same filtered callback set
        # ourselves and contain both failure modes independently.
        args: list[Any] = [bound_carrier, name, _fused(payload)]
        try:
            callbacks = bound_ctx.events.dispatch("emit", list(args))
        except Exception:
            callbacks = []
        for callback in callbacks or []:
            try:
                returned = callback(*args)
            except Exception as exc:  # noqa: BLE001
                try:
                    bound_ctx.logger.warn(
                        f'agent event "{name}" listener threw: {exc}'
                    )
                except Exception:  # pragma: no cover — defensive
                    pass
                continue
            if returned is not None and hasattr(returned, "__await__"):
                # Cordis returns a coroutine for async listeners; we
                # schedule a contained log if the listener rejects.
                try:
                    import asyncio as _asyncio

                    async def _contain(_r: Any = returned, _n: str = name) -> None:
                        try:
                            await _r
                        except Exception as exc:  # noqa: BLE001
                            try:
                                bound_ctx.logger.warn(
                                    f'agent event "{_n}" listener rejected: {exc}'
                                )
                            except Exception:  # pragma: no cover
                                pass

                    _asyncio.ensure_future(_contain())
                except Exception:  # pragma: no cover — defensive
                    pass

    async def _serial(name: str, payload: Any) -> Any:
        # oxlint-disable-next-line typescript/unbound-method -- the events mixin accessor returns a pre-bound function
        serial_fn = getattr(bound_ctx, "serial", None)
        if serial_fn is None:
            return None
        return await serial_fn(bound_carrier, name, _fused(payload))

    def _waterfall(name: str, payload: Any, *rest: Any) -> Any:
        waterfall_fn = getattr(bound_ctx, "waterfall", None)
        if waterfall_fn is None:
            return None
        return waterfall_fn(bound_carrier, name, _fused(payload), *rest)

    return AgentEventDispatch(_emit, _serial, _waterfall)


def emit_agent_event(
    ctx: "Context",
    agent: Any,
    name: str,
    payload: Any,
) -> None:
    """Emit one contained agent notification without retaining a dispatcher.

    Mirrors upstream ``emitAgentEvent``. Useful for fire-and-forget cases
    where the loop driver already has a fused dispatcher and a single
    notification has no hot-path allocation budget.
    """
    agent_events(ctx, agent).emit(name, payload)


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
