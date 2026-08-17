"""`taiyi_core_agent.factory` — agent-creation factory contracts.

1:1 Python port of the factory portion of
`~/deepseek-harness/packages/core/agent/src/index.ts`.

The actual implementation lives in :mod:`taiyi_core_agent.registry`
(:class:`AgentRegistry`); this module owns the type vocabulary that
the registry, the loop, and consumers program against.

Public surface:

- :class:`CreateAgentOptions`, :class:`ResumeAgentOptions`
- :class:`AgentHandle`
- :class:`AgentFactory`
- :class:`AgentSetupCommit`, :class:`AgentSetup`
- :data:`NO_FACTORY_MESSAGE`, :data:`NO_INITIATOR_MESSAGE`,
  :data:`DISPOSED_INITIATOR_MESSAGE`
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from typing_extensions import NotRequired

if TYPE_CHECKING:
    from cordis import Context

    from taiyi_core_agent.runtime_types import Agent, AgentOptions


__all__ = [
    "CreateAgentMeta",
    "CreateAgentOptions",
    "ResumeAgentOptions",
    "AgentSetupCommit",
    "AgentSetup",
    "AgentHandle",
    "AgentFactory",
    "NO_FACTORY_MESSAGE",
    "NO_INITIATOR_MESSAGE",
    "DISPOSED_INITIATOR_MESSAGE",
]


# Thrown when create/resume is called before an agent factory is registered.
NO_FACTORY_MESSAGE = "no agent factory registered (load an agent-loop plugin)"
NO_INITIATOR_MESSAGE = "no initiating agent is active"
DISPOSED_INITIATOR_MESSAGE = "agent initiator scope is disposed"


# ---------------------------------------------------------------------------
# Creation / setup options
# ---------------------------------------------------------------------------


CreateAgentMeta = dict[str, Any]
"""Light alias for the per-factory `meta` payload.

Mirrors the upstream
``meta?: { cwd?, parentSession?, seedLength?, origin?, delegationDepth?, agentPreset? }``
shape without a heavy TypedDict — these are only forwarded to the
factory, where validation happens once the loop mints the session.
"""


@dataclass
class CreateAgentOptions:
    """Options for programmatically creating an agent.

    Mirrors upstream ``CreateAgentOptions``. The caller supplies the
    single live ``session_id`` (a branded :class:`taiyi_core_session.types.SessionId`,
    typed as a plain :class:`str` here to avoid the import cycle), plus
    optional session metadata and an optional :class:`AgentSetup`.
    """

    session_id: str
    meta: CreateAgentMeta | None = None
    seed: tuple[Any, ...] = ()
    agent_options: "AgentOptions | None" = None
    signal: Any = None
    setup: "AgentSetup | None" = None


@dataclass
class ResumeAgentOptions:
    """Options for resuming an agent on a persisted session.

    Mirrors upstream ``ResumeAgentOptions``.
    """

    resume_session_id: str
    agent_options: "AgentOptions | None" = None
    signal: Any = None
    setup: "AgentSetup | None" = None


# ---------------------------------------------------------------------------
# Setup composition contracts
# ---------------------------------------------------------------------------


class AgentSetupCommit:
    """Synchronous finalizer returned by unpublished Agent setup.

    Mirrors upstream ``AgentSetupCommit``: validation/commit happens at
    the exact publication commit point, after every setup await
    settles. The factory invokes ``commit()`` after setup awaits and
    immediately before registry publication; a throw rolls the
    unpublished Agent back.
    """

    def commit(self) -> None:
        """Validate and commit the prepared setup. May raise."""


AgentSetup = Callable[
    ["Context"],
    "AgentSetupCommit | Awaitable[AgentSetupCommit | None] | None",
]
"""Composite setup signature matching upstream ``AgentSetup``."""


# ---------------------------------------------------------------------------
# Owned handle + factory protocol
# ---------------------------------------------------------------------------


@dataclass
class AgentHandle:
    """An owned agent plus its disposer.

    Mirrors upstream :class:`AgentHandle`. The disposer is a CAPABILITY:
    among consumers, only the holder can tear this agent down. The
    registered factory provider is also a structural owner because the
    scoped agent depends on that provider's service API; provider unload
    stops and drains every live handle it made.
    """

    agent: "Agent"
    dispose: Callable[[], Awaitable[None]]

    async def dispose_async(self) -> None:
        """Asynchronous helper for the disposer side of :class:`AgentHandle`."""
        await self.dispose()


class AgentFactory(Protocol):
    """The agent-creation factory the loop implementation provides.

    Mirrors upstream :class:`AgentFactory`. Kept on the
    ``taiyi-core-agent`` interface so consumers (e.g. the ACP bridge)
    program against ``ctx.agents`` without depending on the concrete
    ``taiyi-core-agent-loop`` package.
    """

    async def create_agent(
        self,
        owner_ctx: "Context",
        options: CreateAgentOptions,
    ) -> AgentHandle: ...

    async def resume(
        self,
        owner_ctx: "Context",
        options: ResumeAgentOptions,
    ) -> AgentHandle: ...


__all__.append("CreateAgentMeta")
