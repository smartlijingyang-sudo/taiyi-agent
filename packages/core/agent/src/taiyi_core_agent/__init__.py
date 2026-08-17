"""taiyi-core-agent — Agent service: live registry, factory delegation, and 1:1 Python port of `@deepseek-ai/dsh-agent`.

This package is the Python port of `~/deepseek-harness/packages/core/agent/`.
Public surface:

- :class:`AgentRegistry` — central registry of live agents
- :class:`AgentFactory`, :class:`AgentHandle`, :class:`CreateAgentOptions`,
  :class:`ResumeAgentOptions`, :class:`AgentSetupCommit`, :class:`AgentSetup`
- :class:`Agent`, :class:`AgentOptions`, :class:`CancelOptions`,
  :data:`AgentStatus`
- :class:`Inbox`, :class:`InboxNotifications`
- :data:`PreStepDecision`, :data:`RequestErrorAction`,
  :data:`SessionStartSource`
- :class:`ModelSelection`, :class:`ModelSelectionRef`,
  :func:`install_model_selection`
- :class:`ConsumedWork`, :func:`fold_consumed_work`,
  :func:`accounts_for_claim`
- :data:`InboxTarget`, :class:`InboxSpliceData`
- :func:`agent_carrier`, :func:`agent_events`,
  :func:`emit_agent_event`, :func:`assemble_context_for`
- :data:`AGENT_EVENT_NAMES`, :data:`AGENT_SUBJECT_EVENT_NAMES`,
  :func:`apply` invariant companion
- :func:`setup` cordis plugin entry
- :data:`NO_FACTORY_MESSAGE`, :data:`NO_INITIATOR_MESSAGE`,
  :data:`DISPOSED_INITIATOR_MESSAGE`
"""

from __future__ import annotations

from taiyi_core_agent.carrier import agent_carrier
from taiyi_core_agent.consumed_work import (
    ConsumedWork,
    accounts_for_claim,
    fold_consumed_work,
)
from taiyi_core_agent.context import assemble_context_for
from taiyi_core_agent.dispatch import (
    AgentEventDispatch,
    AGENT_SUBJECT_EVENT_NAMES,
    agent_events,
)
from taiyi_core_agent.event import emit_agent_event
from taiyi_core_agent.factory import (
    AgentFactory,
    AgentHandle,
    AgentSetupCommit,
    AgentSetup,
    CreateAgentMeta,
    CreateAgentOptions,
    DISPOSED_INITIATOR_MESSAGE,
    NO_FACTORY_MESSAGE,
    NO_INITIATOR_MESSAGE,
    ResumeAgentOptions,
)
from taiyi_core_agent.inbox import Inbox, InboxNotifications
from taiyi_core_agent.model_selection import (
    ModelSelection,
    ModelSelectionRef,
    install_model_selection,
)
from taiyi_core_agent.registry import AgentEntry, AgentRegistry, InitiatorRun
from taiyi_core_agent.runtime_types import (
    AGENT_EVENT_NAMES,
    Agent,
    AgentOptions,
    CancelOptions,
    PreStepDecision,
    RequestErrorAction,
    SessionStartSource,
)
from taiyi_core_agent.status import AgentStatus
from taiyi_core_agent.types import InboxSpliceData, InboxTarget

__version__ = "0.1.0"

__all__ = [
    # registry
    "AgentEntry",
    "AgentRegistry",
    "InitiatorRun",
    # factory
    "AgentFactory",
    "AgentHandle",
    "AgentSetupCommit",
    "AgentSetup",
    "CreateAgentMeta",
    "CreateAgentOptions",
    "ResumeAgentOptions",
    "NO_FACTORY_MESSAGE",
    "NO_INITIATOR_MESSAGE",
    "DISPOSED_INITIATOR_MESSAGE",
    # runtime types / status
    "AGENT_EVENT_NAMES",
    "Agent",
    "AgentOptions",
    "AgentStatus",
    "CancelOptions",
    "PreStepDecision",
    "RequestErrorAction",
    "SessionStartSource",
    # inbox
    "Inbox",
    "InboxNotifications",
    # types
    "InboxSpliceData",
    "InboxTarget",
    # consumed-work
    "ConsumedWork",
    "accounts_for_claim",
    "fold_consumed_work",
    # model selection
    "ModelSelection",
    "ModelSelectionRef",
    "install_model_selection",
    # dispatch
    "AgentEventDispatch",
    "AGENT_SUBJECT_EVENT_NAMES",
    "agent_carrier",
    "agent_events",
    "emit_agent_event",
    "assemble_context_for",
    # invariant companion
    "apply",
    # meta
    "__version__",
]


# ---------------------------------------------------------------------------
# Invariant companion — lazy wrapper so the public surface exposes `apply`
# directly. The real implementation lives in
# :mod:`taiyi_core_agent.invariant`.
# ---------------------------------------------------------------------------


def apply(ctx):  # type: ignore[no-untyped-def]
    """Register the agent invariant companion.

    Mirrors upstream ``apply``. Re-exported from
    :mod:`taiyi_core_agent.invariant` so the surface is reachable from
    the package root.
    """
    from taiyi_core_agent.invariant import apply as _apply
    return _apply(ctx)
