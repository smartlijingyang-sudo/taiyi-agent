"""`taiyi_core_agent.runtime_types` — public agent types + live-runtime events.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/runtime-types.ts`.

Public surface:

- :class:`AgentOptions`, :class:`CancelOptions`
- :data:`AgentStatus`
- :data:`PreStepDecision`, :data:`RequestErrorAction`
- :data:`SessionStartSource`
- :class:`Agent` (protocol)
- :data:`AGENT_EVENT_NAMES` — live-runtime agent event vocabulary

The upstream `declare module '@deepseek-ai/dsh-system-prompt'` augmentation
(adding ``agent?: Agent`` to ``AssembleContext``) and `declare module
'@deepseek-ai/cordis'` augmentation (declaring ``Events['agent/*']``) have
no Python runtime equivalent. The agent event names are exposed as
:data:`AGENT_EVENT_NAMES` so callers and tests can refer to them as
strings, and :class:`Agent` carries the same ``agent: Agent`` self-reference
that the dispatch helper injects.

Cross-package types that Python lacks a port for yet (``UserMessage``,
``MessageId``, ``LlmCallConfig``, ``LlmFailure``, ``ResolvedRetryPolicy``,
``AssembleContext``, ``AgentCancelCause``) are referenced as duck-typed
mapping strings / generic ``Any`` so the protocols remain importable
without depending on the not-yet-ported LLM / system-prompt packages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, NotRequired, Protocol, TypedDict

if TYPE_CHECKING:
    from cordis import Context
    from taiyi_core_session.session import Session

    from taiyi_core_agent.inbox import Inbox


__all__ = [
    "AgentOptions",
    "CancelOptions",
    "AgentStatus",
    "PreStepDecision",
    "RequestErrorAction",
    "SessionStartSource",
    "Agent",
    "AGENT_EVENT_NAMES",
]


# ---------------------------------------------------------------------------
# Agent creation / cancellation options
# ---------------------------------------------------------------------------


class AgentOptions(TypedDict, total=False):
    """Merge-extensible agent creation options.

    Mirrors upstream `AgentOptions`: persona configuration belongs to
    system-prompt sections, never here. Only request-router fields live on
    this dict.
    """

    provider: NotRequired[str]
    model: NotRequired[str]
    maxTokens: NotRequired[int]


class CancelOptions(TypedDict, total=False):
    """Options accepted by :meth:`Agent.cancel`."""

    keepInbox: NotRequired[bool]


# `AgentStatus` lives in :mod:`taiyi_core_agent.status`; re-exported here so
# callers reading the runtime-types module see the full public surface.
AgentStatus = Literal["idle", "running"]


# ---------------------------------------------------------------------------
# Pre-step / request-recovery decision unions
# ---------------------------------------------------------------------------

# Upstream uses discriminated unions; Python mirrors them with NotRequired
# discriminator-style TypedDicts and a single ``PreStepDecision`` union.
class _PreStepReject(TypedDict):
    kind: Literal["reject"]


class _PreStepEnter(TypedDict):
    kind: Literal["enter"]
    messages: list[Any]


PreStepDecision = _PreStepReject | _PreStepEnter


class _RequestErrorRetry(TypedDict):
    kind: Literal["retry"]


RequestErrorAction = _RequestErrorRetry | None


SessionStartSource = Literal["startup", "resume", "clear", "compact"]


# ---------------------------------------------------------------------------
# Live Agent interface (Protocol — runtime contract)
# ---------------------------------------------------------------------------


class Agent(Protocol):
    """Public live-agent handle.

    Mirrors upstream :class:`Agent`. Python uses a :class:`Protocol` because
    the loop implementation is provided by another package
    (``taiyi-core-agent-loop``); the registry only needs to type-check
    against the public surface here.
    """

    id: str  # SessionId alias; declared as plain str to avoid the import cycle.
    options: AgentOptions
    session: Session
    inbox: Inbox
    status: AgentStatus
    ctx: Context

    def cancel(self, cause: Any, options: CancelOptions | None = ...) -> None: ...  # pragma: no cover
    async def when_idle(self) -> None: ...  # pragma: no cover
    def run_maintenance(  # pragma: no cover
        self, task: Callable[[Any], Any]
    ) -> Any: ...
    def send(self, message: Any, target: str, wakeup: bool) -> None: ...  # pragma: no cover
    def followup(self, message: Any) -> None: ...  # pragma: no cover
    def steer(self, message: Any) -> None: ...  # pragma: no cover
    def inject(self, message: Any) -> None: ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Live-runtime agent event vocabulary
# ---------------------------------------------------------------------------

# The agent-subject event names form a stable string vocabulary. Upstream
# declares them via TypeScript module augmentation on the cordis ``Events``
# interface; the Python port exposes them as a tuple so callers and tests
# can verify membership without depending on a structural typing trick.
AGENT_EVENT_NAMES: tuple[str, ...] = (
    # ---- lifecycle (emit) ----
    "agent/created",
    "agent/disposed",
    "agent/status",
    # ---- inbox (emit) ----
    "agent/inbox/inserted",
    "agent/inbox/claimed",
    "agent/inbox/discarded",
    # ---- session lifecycle (emit) ----
    "agent/session-start",
    # ---- machine extension points ----
    "agent/pre-step",          # waterfall
    "agent/request",           # waterfall
    "agent/request-error",     # waterfall
    "agent/turn-stopping",     # serial
    # ---- error notifications (emit) ----
    "agent/error",
)
