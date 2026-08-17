"""`taiyi_core_agent.registry` — live agent registry + initiator AsyncLocalStorage.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/index.ts`
(the ``AgentRegistry`` Service class).

Public surface:

- :class:`AgentRegistry` — central registry of agent types (built-in +
  user-defined), with initiator ``withInitiator`` /
  :meth:`AgentRegistry.without_initiator` AsyncLocalStorage transitions.
"""

from __future__ import annotations

import asyncio
import inspect
import weakref
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from cordis import Context, Service

from taiyi_core_agent.factory import (
    AgentFactory,
    AgentHandle,
    CreateAgentOptions,
    DISPOSED_INITIATOR_MESSAGE,
    NO_FACTORY_MESSAGE,
    NO_INITIATOR_MESSAGE,
    ResumeAgentOptions,
)
from taiyi_core_agent.runtime_types import Agent as AgentProtocol
from taiyi_core_scope import scope_target

if TYPE_CHECKING:
    from cordis import Fiber


__all__ = [
    "AgentRegistry",
    "AgentEntry",
    "InitiatorRun",
]


# ---------------------------------------------------------------------------
# Stateful records
# ---------------------------------------------------------------------------


@dataclass
class AgentEntry:
    """All mutable lifecycle state for one exact registry entry.

    Mirrors upstream ``AgentEntry``. The entry identity is the
    authoritative collision boundary (``enter()`` rejects replacement
    while a single-shot detach capability is live).
    """

    id: str
    agent: AgentProtocol
    owner: AgentProtocol | None
    carrier: Any
    announced: bool = False
    announcing: bool = False
    detach_requested: bool = False
    # Auxiliary marker mirroring upstream `WeakMap<Agent, ...>`-style
    # bookkeeping — kept as a per-entry weak dictionary so a registry
    # does not extend agent lifetimes beyond what callers retain.
    last_status: "weakref.WeakKeyDictionary[AgentProtocol, str]" = field(
        default_factory=weakref.WeakKeyDictionary
    )


@dataclass
class InitiatorRun:
    """One tracked initiator or clearing boundary.

    Mirrors upstream ``InitiatorRun``. The run's ``parent`` chain is
    walked by
    :meth:`AgentRegistry._release_reentrant_initiator_runs` so the
    teardown initiated by one chain excludes that chain from its own
    drain.
    """

    active: bool = True
    parent: "InitiatorRun | None" = None


def _is_awaitable(value: Any) -> bool:
    """Mirror Node's ``util.isPromise`` for the few cases upstream needs."""
    if value is None or value is False:
        return False
    return hasattr(value, "__await__") and callable(getattr(value, "__await__", None))


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class AgentRegistry(Service):
    """Live registry of agent types + initiator AsyncLocalStorage.

    Mirrors upstream ``AgentRegistry``:

    - :meth:`create` / :meth:`resume` invoke the loop-supplied factory.
    - :meth:`register` / :meth:`enter` / :meth:`announce` build entries.
    - :meth:`current_initiator` / :meth:`require_initiator` read the
      inherited Agent.
    - :meth:`with_initiator` / :meth:`without_initiator` scope one
      Agent as the inherited initiator of one synchronous or
      asynchronous operation.
    """

    def __init__(self, ctx: Context, **config: Any) -> None:  # noqa: D107 — Service init
        super().__init__(ctx, **config)
        # The Python ``Service`` base does not auto-register under a
        # framework-level name; mirror upstream ``super(ctx, 'agents')``
        # by binding ``self`` as ``ctx.agents`` so runtime readers see
        # ``ctx.agents === this``.
        self._ctx = ctx
        try:
            ctx.reflect.provide("agents", self)  # type: ignore[attr-defined]
        except RuntimeError:
            # Already provided — a second install is a no-op.
            pass

        # Store and factory slot — see upstream `private store` /
        # `private factory`.
        self._store: dict[str, AgentEntry] = {}
        self._factory: dict[str, Any] | None = None

        # Initiator AsyncLocalStorage (Python: ContextVar with two
        # layers, mirroring upstream's two AsyncLocalStorage instances).
        self._initiators: ContextVar[AgentProtocol | None] = ContextVar(
            "taiyi_core_agent.initiators", default=None
        )
        self._initiator_runs: ContextVar[InitiatorRun | None] = ContextVar(
            "taiyi_core_agent.initiator_runs", default=None
        )
        self._initiator_state: Literal["active", "closing", "disposed"] = "active"
        self._active_initiator_runs = 0
        self._initiator_drain: asyncio.Future[None] | None = None
        self._initiator_disposal: asyncio.Future[None] | None = None

        # Optional Typert registration — skip when the typert service
        # is not available in the consuming context.
        try:
            if hasattr(ctx, "typert"):
                type_ctx = ctx.typert  # type: ignore[attr-defined]
                try:
                    type_ctx.lookups.register("agent", {  # type: ignore[attr-defined]
                        "parameter": "agent",
                        "wire": "agentId",
                        "hostTypeSymbol": "@deepseek-ai/dsh-agent#Agent",
                        "wireTypeSymbol": "@deepseek-ai/dsh-session/types#SessionId",
                        "resolve": lambda session_id: self.get(session_id),
                    })
                except Exception:  # pragma: no cover — best-effort
                    pass
                try:
                    type_ctx.contexts.registerHost("agent", {  # type: ignore[attr-defined]
                        "wire": "agentId",
                        "wireTypeSymbol": "@deepseek-ai/dsh-session/types#SessionId",
                        "resolve": lambda session_id: (
                            self.get(session_id).ctx
                            if self.get(session_id) is not None
                            else None
                        ),
                    })
                except Exception:  # pragma: no cover — best-effort
                    pass
        except Exception:  # pragma: no cover — defensive
            pass

        # ``ctx.agent`` DX accessor — defaults to ``None`` on every
        # context. Each Agent.ctx shadows it with an own property so
        # the accessor body never needs to resolve a scope itself.
        try:
            ctx.reflect.accessor(  # type: ignore[attr-defined]
                "agent",
                {"get": lambda _ctx, _rcv, _err: None},
            )
        except RuntimeError:
            # Accessor already declared by another install — safe to skip.
            pass
        except Exception:  # pragma: no cover — best-effort
            pass

        # Lifecycle wiring: close initiator scope when our fiber unloads.
        try:
            self._service_dispose = ctx.fiber.effect(  # type: ignore[attr-defined]
                _initiator_lifecycle_factory(self),
                label="agents.initiatorLifecycle()",
            )
        except Exception:  # pragma: no cover — fiberless context
            self._service_dispose = None

        # Install the ``internal/status`` listener that closes the
        # initiator scope when our service's fiber unloads. Mirrors the
        # upstream TS ``ctx.on('internal/status', ...)`` block.
        try:
            ctx.on(  # type: ignore[attr-defined]
                "internal/status",
                _on_internal_status_factory(self),
            )
        except Exception:  # pragma: no cover — listener registration may fail
            pass

    # ------------------------------------------------------------------
    # Initiator reads
    # ------------------------------------------------------------------

    def current_initiator(self) -> AgentProtocol | None:
        """Read the Agent that initiated the inherited async driver chain.

        Mirrors upstream ``currentInitiator``. Use the optional form for
        logging / tracing / metrics that also support agentless calls;
        :meth:`require_initiator` for the throwing variant.
        """
        self._assert_initiators_readable()
        return self._initiators.get()

    def require_initiator(self) -> AgentProtocol:
        """Read the initiator and fail when no boundary is active.

        Mirrors upstream ``requireInitiator``.
        """
        agent = self.current_initiator()
        if agent is None:
            raise RuntimeError(NO_INITIATOR_MESSAGE)
        return agent

    # ------------------------------------------------------------------
    # Initiator boundaries
    # ------------------------------------------------------------------

    def with_initiator(
        self,
        agent: AgentProtocol,
        operation: Callable[[], Any],
    ) -> Any:
        """Run ``operation`` with ``agent`` as its inherited initiator."""
        return self._run_with_initiator(agent, operation)

    def without_initiator(self, operation: Callable[[], Any]) -> Any:
        """Run ``operation`` without an inherited initiator boundary."""
        return self._run_with_initiator(None, operation)

    # ------------------------------------------------------------------
    # Factory registration / use
    # ------------------------------------------------------------------

    def set_factory(self, factory: AgentFactory) -> Callable[[], None]:
        """Register the agent-creation factory.

        Mirrors upstream ``setFactory``. Returns the exact cordis effect
        disposer (single-shot): composite (generator) effects may yield
        it directly — exact identity nests the teardown in order.
        """
        # Avoid stacking two Cordis shadow layers when a caller passes a
        # Service already read through a context. Calls are re-traced
        # through their actual owner context below.
        original_symbol = "cordis.original"
        target_obj: Any = factory
        try:
            shadow_target = getattr(target_obj, original_symbol, None)
            if shadow_target is not None:
                target_obj = shadow_target
        except Exception:  # pragma: no cover — defensive
            pass

        if self._factory is not None:
            raise RuntimeError("an agent factory is already registered")
        self._factory = {"target": target_obj}

        def _dispose() -> None:
            self._factory = None

        try:
            return self._ctx.fiber.effect(  # type: ignore[attr-defined]
                lambda: _dispose,
                label="agents.setFactory()",
            )
        except Exception:  # pragma: no cover — fiberless context
            return _dispose

    def create(self, options: CreateAgentOptions) -> Any:
        """Create and publish a new agent through the registered factory.

        Mirrors upstream ``create``. The resolved :class:`AgentHandle`
        lets the owner tear down exactly this agent.
        """
        factory_slot = self._require_factory()
        target = factory_slot["target"]
        try:
            result = target.create_agent(self._ctx, options)
        except Exception:
            raise
        if inspect.isawaitable(result):
            return self._create_async(target, options)
        return result

    async def resume(self, options: ResumeAgentOptions) -> AgentHandle:
        """Load a persisted session and resume an agent on it.

        Mirrors upstream ``resume``. Rejects if no factory is registered
        or if persistence / setup fails.
        """
        factory_slot = self._require_factory()
        target = factory_slot["target"]
        result = target.resume(self._ctx, options)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _create_async(
        self, factory_target: AgentFactory, options: CreateAgentOptions
    ) -> AgentHandle:
        """Async counterpart to :meth:`create`."""
        result = factory_target.create_agent(self._ctx, options)
        if inspect.isawaitable(result):
            result = await result
        return result

    # ------------------------------------------------------------------
    # Agent lifecycle (register / enter / announce)
    # ------------------------------------------------------------------

    def register(self, agent: AgentProtocol) -> Callable[[], None]:
        """Register a live agent.

        Mirrors upstream ``register``. Returns the exact cordis effect
        disposer (single-shot; a repeat call returns ``None`` without
        awaiting an in-flight teardown).
        """
        try:
            return self._ctx.fiber.effect(  # type: ignore[attr-defined]
                _register_effect_factory(self, agent),
                label="agents.register()",
            )
        except Exception:  # pragma: no cover — fiberless context
            return _register_sync(self, agent)

    def enter(
        self,
        agent: AgentProtocol,
        owner: AgentProtocol | None,
    ) -> Callable[[], None]:
        """Insert an already-constructed agent without announcing.

        Mirrors upstream ``enter``. Returns an idempotent detach closure
        that removes this exact entry and emits ``agent/disposed`` when
        the agent has already been announced.
        """
        agent_id = agent.id
        if agent_id != agent.session.id:
            raise RuntimeError(
                f'agent id "{agent_id}" does not match session id "{agent.session.id}"'
            )
        carrier = scope_target(agent, agent)
        if agent_id in self._store:
            raise RuntimeError(f'agent "{agent_id}" is already registered')
        entry = AgentEntry(
            id=agent_id,
            agent=agent,
            owner=owner,
            carrier=carrier,
        )
        self._store[agent_id] = entry
        entered = True

        def _detach() -> None:
            nonlocal entered
            if not entered:
                return
            entered = False
            if entry.announcing:
                entry.detach_requested = True
                return
            self._detach_entered(entry)

        return _detach

    def announce(self, agent: AgentProtocol) -> None:
        """Announce an agent previously inserted via :meth:`enter`.

        Mirrors upstream ``announce``. Throws if the agent isn't the
        live registry entry for its id, or if the creation announcement
        already began.
        """
        entry = self._store.get(agent.id)
        if entry is None or entry.agent is not agent:
            raise RuntimeError(f'agent "{agent.id}" is not live in this registry')
        if entry.announced or entry.announcing:
            raise RuntimeError(f'agent "{entry.id}" was already announced')
        entry.announcing = True
        entry.announced = True
        try:
            self._emit_created(entry)
        finally:
            entry.announcing = False
            if entry.detach_requested:
                self._detach_entered(entry)

    def _emit_created(self, entry: AgentEntry) -> None:
        """Emit the paired ``agent/created`` lifecycle edge.

        Mirrors upstream's manual dispatch loop: read the registered
        hooks, invoke each with the original args (``carrier, name,
        payload``), and contain both synchronous throws and returned-
        promise rejections. Skips cordis's ``_bind_callbacks`` wrapper
        so a listener can keep its expected argument count.
        """
        args: tuple[Any, ...] = (
            entry.carrier,
            "agent/created",
            {"agent": entry.agent},
        )
        callbacks = _collect_unbound_callbacks(self._ctx, "agent/created")  # type: ignore[attr-defined]
        for callback in callbacks:
            try:
                returned = callback(*args)
            except Exception as exc:  # noqa: BLE001
                _log_warn(self, entry.id, "agent/created", "threw", exc)
                continue
            if inspect.isawaitable(returned):
                _schedule_rejection_log(self, entry.id, "agent/created", returned)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get(self, agent_id: str) -> AgentProtocol | None:
        """Look up a live agent by id."""
        entry = self._store.get(agent_id)
        return entry.agent if entry is not None else None

    def is_owned_by(self, agent_id: str, owner: AgentProtocol) -> bool:
        """Test whether a live agent was created through ``owner``'s scope."""
        entry = self._store.get(agent_id)
        return entry is not None and entry.owner is owner

    def list(self) -> list[AgentProtocol]:
        """All live agents, in registration order."""
        return [entry.agent for entry in self._store.values()]

    def roots(self) -> list[AgentProtocol]:
        """All live top-level agents (no owner), in registration order."""
        return [
            entry.agent
            for entry in self._store.values()
            if entry.owner is None
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_factory(self) -> dict[str, Any]:
        if self._factory is None:
            raise RuntimeError(NO_FACTORY_MESSAGE)
        return self._factory

    def _detach_entered(self, entry: AgentEntry) -> None:
        """Remove one exact entered agent and emit its paired disposal when announced."""
        entry.detach_requested = False
        if self._store.get(entry.id) is not entry:
            return
        self._store.pop(entry.id, None)
        # An insertion rolled back before announce never produced a
        # ``created`` event, so emitting ``disposed`` would invent an
        # impossible lifecycle edge.
        if not entry.announced:
            return
        self._emit_disposed(entry)

    def _emit_disposed(self, entry: AgentEntry) -> None:
        """Emit the paired ``agent/disposed`` lifecycle edge."""
        args: tuple[Any, ...] = (
            entry.carrier,
            "agent/disposed",
            {"agent": entry.agent},
        )
        callbacks = _collect_unbound_callbacks(self._ctx, "agent/disposed")  # type: ignore[attr-defined]
        for callback in callbacks:
            try:
                returned = callback(*args)
            except Exception as exc:  # noqa: BLE001
                _log_warn(self, entry.id, "agent/disposed", "threw", exc)
                continue
            if inspect.isawaitable(returned):
                _schedule_rejection_log(self, entry.id, "agent/disposed", returned)

    def _has_lifecycle_ancestor(self, candidate: "Fiber") -> bool:
        """Whether ``candidate`` is an ancestor of our service's fiber."""
        try:
            fiber: Any = self._ctx.fiber
        except Exception:
            return False
        while True:
            if fiber is candidate:
                return True
            parent = getattr(fiber.parent, "fiber", None)
            if parent is fiber:
                return False
            fiber = parent

    def _close_initiators(self) -> None:
        """Reject new initiator boundaries while inherited continuations drain."""
        if self._initiator_state == "active":
            self._initiator_state = "closing"

    def _dispose_initiators(self) -> "asyncio.Future[None]":
        """Drive the initiator-scope teardown on the running event loop.

        Mirrors upstream ``disposeInitiators``: memoizes the disposal
        future so repeated calls share the same ``Promise``. The
        teardown awaits any in-flight initiator boundaries, then
        invalidates retained references and disables the ContextVars.
        """
        if self._initiator_disposal is not None:
            return self._initiator_disposal
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop — settle a placeholder future so callers
            # can observe the synchronous-completion contract.
            self._initiator_disposal = asyncio.Future()
            self._initiator_disposal.set_result(None)
            return self._initiator_disposal

        self._initiator_disposal = loop.create_future()
        captured_future = self._initiator_disposal

        async def _teardown() -> None:
            try:
                self._close_initiators()
                self._release_reentrant_initiator_runs()
                while self._active_initiator_runs != 0:
                    if self._initiator_drain is None:
                        self._initiator_drain = loop.create_future()
                    await self._initiator_drain
                    self._initiator_drain = None
                self._initiator_state = "disposed"
            finally:
                captured_future.set_result(None)

        try:
            loop.create_task(_teardown())
        except RuntimeError:
            # Loop closed between acquisition and scheduling — settle
            # synchronously so the disposer remains awaitable.
            captured_future.set_result(None)
        return self._initiator_disposal

    def _run_with_initiator(
        self,
        agent: AgentProtocol | None,
        operation: Callable[[], Any],
    ) -> Any:
        if self._initiator_state != "active":
            raise RuntimeError(DISPOSED_INITIATOR_MESSAGE)
        run = InitiatorRun(parent=self._initiator_runs.get())
        self._active_initiator_runs += 1
        result: Any
        try:
            init_token = self._initiator_runs.set(run)
            agent_token = self._initiators.set(agent)
            try:
                result = operation()
            finally:
                self._initiators.reset(agent_token)
                self._initiator_runs.reset(init_token)
        except BaseException:
            self._release_initiator_run(run)
            raise

        # Mirrors upstream's ``isPromise(result)`` semantics: an
        # awaitable result creates a boundary that lives until the
        # awaited value settles; a synchronous result is released
        # immediately.
        if _is_awaitable(result):
            self._watch_awaitable(result, run)
        else:
            self._release_initiator_run(run)
        return result

    def _watch_awaitable(self, awaitable: Any, run: InitiatorRun) -> None:
        """Schedule an awaitable continuation to release its initiator run.

        Best-effort: if no event loop is running the run is released
        immediately so the boundary invariant is preserved even in
        synchronous test contexts. Mirrors upstream's brand-protection
        branch (``@@species`` failure).
        """
        def _on_settle(_r: Any) -> None:
            self._release_initiator_run(run)

        loop = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            self._release_initiator_run(run)
            return
        try:
            running = loop.is_running()
        except Exception:  # pragma: no cover — defensive
            running = False
        if not running:
            self._release_initiator_run(run)
            return
        try:
            loop.create_task(_await_and_release(awaitable, _on_settle))
        except RuntimeError:
            self._release_initiator_run(run)

    def _assert_initiators_readable(self) -> None:
        if self._initiator_state == "disposed":
            raise RuntimeError(DISPOSED_INITIATOR_MESSAGE)

    def _release_reentrant_initiator_runs(self) -> None:
        """Exclude the boundary chain that initiated this teardown from its own drain."""
        run = self._initiator_runs.get()
        while run is not None:
            self._release_initiator_run(run)
            run = run.parent

    def _release_initiator_run(self, run: InitiatorRun) -> None:
        if not run.active:
            return
        run.active = False
        self._active_initiator_runs -= 1
        if self._active_initiator_runs != 0:
            return
        if self._initiator_drain is not None:
            try:
                self._initiator_drain.set_result(None)
            except Exception:  # pragma: no cover — already settled
                pass
        self._initiator_drain = None


# ---------------------------------------------------------------------------
# Module helpers — kept at module scope so coverage can track them cleanly
# ---------------------------------------------------------------------------


def _initiator_lifecycle_factory(registry: AgentRegistry) -> Callable[[], Any]:
    """Build the composite (generator) effect for initiator lifecycle.

    Mirrors the upstream ``ctx.effect(function* ...)`` block: a generator
    that yields two disposers in teardown order — first wait for the
    initiator drain, then close initiators.
    """

    def _composite() -> Any:
        # First yielded disposer awaits the teardown future.
        yield lambda: registry._dispose_initiators()
        # Second yielded disposer synchronously closes initiators.
        yield registry._close_initiators

    return _composite


def _on_internal_status_factory(registry: AgentRegistry) -> Callable[[Any], None]:
    """Build the ``internal/status`` listener that closes initiator scope on unload."""

    def _listener(fiber: Any) -> None:
        try:
            from cordis.fiber import FiberState
        except Exception:  # pragma: no cover — cordis not available
            return
        if (
            getattr(fiber, "state", None) == FiberState.UNLOADING
            and registry._has_lifecycle_ancestor(fiber)
        ):
            registry._close_initiators()

    return _listener


def _register_effect_factory(
    registry: AgentRegistry,
    agent: AgentProtocol,
) -> Callable[[], Any]:
    """Build the generator effect used by :meth:`AgentRegistry.register`."""

    def _effect() -> Any:
        # Yield the enter disposer first so the framework nests the
        # unregistration at this exact yield position; only then
        # announce the agent (enter+announce ordering matters for
        # listeners that observe the lifecycle pair).
        yield registry.enter(agent, getattr(registry._ctx, "agent", None))
        registry.announce(agent)

    return _effect


def _register_sync(
    registry: AgentRegistry, agent: AgentProtocol
) -> Callable[[], None]:
    """Synchronous fallback when the cordis effect is unavailable."""
    entered = registry.enter(agent, getattr(registry._ctx, "agent", None))
    registry.announce(agent)
    return entered


def _log_warn(
    registry: AgentRegistry,
    agent_id: str,
    event_name: str,
    mode: str,
    exc: BaseException,
) -> None:
    """Contain a listener's synchronous throw with a logger.warning call."""
    try:
        registry._ctx.logger.warn(  # type: ignore[attr-defined]
            f'agent "{agent_id}": {event_name} listener {mode}: {exc}'
        )
    except Exception:  # pragma: no cover — defensive
        pass


def _schedule_rejection_log(
    registry: AgentRegistry,
    agent_id: str,
    event_name: str,
    returned: Any,
) -> None:
    """Schedule a contained log for an awaited listener that rejected.

    Mirrors upstream's ``void Promise.resolve(returned).catch(...)``
    pattern. The Python port logs through ``asyncio.ensure_future``
    best-effort.
    """
    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or not loop.is_running():
        return
    try:
        loop.create_task(_log_rejection(registry, agent_id, event_name, returned))
    except RuntimeError:  # pragma: no cover — defensive
        pass


async def _log_rejection(
    registry: AgentRegistry,
    agent_id: str,
    event_name: str,
    returned: Any,
) -> None:
    try:
        await returned
    except Exception as exc:  # noqa: BLE001
        _log_warn(registry, agent_id, event_name, "rejected", exc)


async def _await_and_release(
    awaitable: Any, on_settle: Callable[[Any], None]
) -> None:
    """Await ``awaitable`` and call ``on_settle`` regardless of outcome."""
    try:
        await awaitable
    except Exception:  # noqa: BLE001
        pass
    on_settle(None)


def _collect_unbound_callbacks(ctx: Any, event_name: str) -> list[Any]:
    """Return the registered ``event_name`` callbacks without cordis's ``_bind_callbacks`` wrapper.

    Upstream TS's ``events.dispatch('emit', args)`` returns callbacks
    whose first invocation already binds ``this``; the registry's
    announcement loop calls them with the full original args (``carrier,
    name, payload``). The Python port can't reach that shape through
    :meth:`EventsService.dispatch` because ``_bind_callbacks`` adds a
    trailing ``thisArg`` slot, so the registry reads the hooks table
    directly.
    """
    try:
        hooks_service = ctx.events  # type: ignore[attr-defined]
        hooks_table = hooks_service._hooks  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover — defensive
        return []
    hooks = hooks_table.get(event_name) if isinstance(hooks_table, dict) else None
    if not hooks:
        return []
    return [hook.callback for hook in hooks]
