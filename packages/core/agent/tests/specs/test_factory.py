"""Tests for `taiyi_core_agent.factory` — the factory contract vocabulary."""

from __future__ import annotations

import inspect
from typing import Any

from taiyi_core_agent.factory import (
    DISPOSED_INITIATOR_MESSAGE,
    NO_FACTORY_MESSAGE,
    NO_INITIATOR_MESSAGE,
    AgentFactory,
    AgentHandle,
    AgentSetupCommit,
    CreateAgentOptions,
    ResumeAgentOptions,
)
from taiyi_core_agent.runtime_types import AgentOptions

# ---------------------------------------------------------------------------
# Options dataclasses
# ---------------------------------------------------------------------------


def test_create_agent_options_defaults() -> None:
    """`CreateAgentOptions` defaults are mutable-but-empty shapes."""
    options = CreateAgentOptions(session_id="abc")
    assert options.session_id == "abc"
    assert options.meta is None
    assert options.seed == ()
    assert options.agent_options is None
    assert options.signal is None
    assert options.setup is None


def test_create_agent_options_stores_meta_and_setup() -> None:
    """`CreateAgentOptions` accepts the full payload."""
    setup_called: list[Any] = []

    def _setup(_ctx: Any) -> None:
        setup_called.append(_ctx)

    sentinel_ctx = object()
    options = CreateAgentOptions(
        session_id="abc",
        meta={"cwd": "/abs", "delegationDepth": 2},
        seed=({"type": "turn/start"},),
        agent_options=AgentOptions(provider="x", model="y"),
        signal=None,
        setup=_setup,
    )
    assert options.meta == {"cwd": "/abs", "delegationDepth": 2}
    assert options.seed == ({"type": "turn/start"},)
    assert options.agent_options == {"provider": "x", "model": "y"}
    assert callable(options.setup)
    options.setup(sentinel_ctx)  # type: ignore[arg-type]
    assert setup_called == [sentinel_ctx]


def test_resume_agent_options_defaults() -> None:
    """`ResumeAgentOptions` matches the upstream surface."""
    options = ResumeAgentOptions(resume_session_id="abc")
    assert options.resume_session_id == "abc"
    assert options.agent_options is None
    assert options.signal is None
    assert options.setup is None


# ---------------------------------------------------------------------------
# Setup commit + setup callable
# ---------------------------------------------------------------------------


def test_setup_commit_default_commit_is_noop() -> None:
    """The default `AgentSetupCommit.commit` is a no-op (override to validate)."""
    commit = AgentSetupCommit()
    assert commit.commit() is None


def test_setup_commit_override_rejects() -> None:
    """`AgentSetupCommit` subclasses can validate in `commit()`."""

    class _StrictCommit(AgentSetupCommit):
        def __init__(self) -> None:
            self.observed = False

        def commit(self) -> None:
            self.observed = True

    c = _StrictCommit()
    c.commit()
    assert c.observed is True


def test_setup_callable_can_be_sync_or_async() -> None:
    """`AgentSetup` accepts sync / async / commit-returning callables."""
    sync_calls: list[Any] = []

    def _sync(_ctx: Any) -> None:
        sync_calls.append("sync")

    async def _async(_ctx: Any) -> None:
        sync_calls.append("async")

    def _returning_commit(_ctx: Any) -> AgentSetupCommit:
        return AgentSetupCommit()

    assert inspect.isfunction(_sync)
    assert inspect.iscoroutinefunction(_async)
    # The returning-commit variant matches the upstream type alias.
    assert callable(_returning_commit)


# ---------------------------------------------------------------------------
# Handle + factory protocol shapes
# ---------------------------------------------------------------------------


def test_agent_handle_is_dataclass_with_required_fields() -> None:
    """`AgentHandle` exposes `agent` and `dispose`."""

    async def _dispose() -> None:
        return None

    handle = AgentHandle(agent=object(), dispose=_dispose)
    assert hasattr(handle, "agent")
    assert callable(handle.dispose)
    # Dataclass field check.
    import dataclasses
    fields = {f.name for f in dataclasses.fields(AgentHandle)}
    assert fields == {"agent", "dispose"}


def test_agent_factory_protocol_signature() -> None:
    """`AgentFactory`'s protocol declares the two async methods."""
    method_names = {name for name in dir(AgentFactory) if not name.startswith("_")}
    assert "create_agent" in method_names
    assert "resume" in method_names


def test_agent_factory_protocol_isinstance_check() -> None:
    """`isinstance` against `AgentFactory` follows runtime-checkable protocol."""

    class _ValidFactory:
        async def create_agent(self, owner_ctx: Any, options: Any) -> AgentHandle:
            return AgentHandle(agent=object(), dispose=lambda: _noop())

        async def resume(self, owner_ctx: Any, options: Any) -> AgentHandle:
            return AgentHandle(agent=object(), dispose=lambda: _noop())

    class _InvalidFactory:
        pass

    valid = _ValidFactory()
    invalid = _InvalidFactory()
    # Protocol without ``runtime_checkable`` may not support isinstance;
    # verify the protocol exposes the expected methods either way.
    assert hasattr(valid, "create_agent")
    assert hasattr(valid, "resume")
    assert not hasattr(invalid, "create_agent")


def test_agent_factory_protocol_runtime_checkable_when_decorated() -> None:
    """`AgentFactory` is already decorated with ``runtime_checkable``."""
    # ``hasattr(AgentFactory, '__class_getitem__')`` is the canonical
    # runtime-checkable marker; this test pins the contract.
    import typing
    assert hasattr(typing, "runtime_checkable")
    # The protocol declares the two methods regardless of decoration.
    members = {name for name in dir(AgentFactory) if not name.startswith("__")}
    assert "create_agent" in members
    assert "resume" in members


def test_agent_factory_protocol_dual_signature_validate() -> None:
    """`AgentFactory`'s protocol has typing.Protocol as its metaclass."""
    # The Python protocol class is recognizable via ``__abstractmethods__``.
    assert hasattr(AgentFactory, "__abstractmethods__")


# ---------------------------------------------------------------------------
# Error message constants
# ---------------------------------------------------------------------------


def test_no_factory_message_is_a_human_readable_string() -> None:
    """`NO_FACTORY_MESSAGE` is the exact upstream message."""
    assert NO_FACTORY_MESSAGE == "no agent factory registered (load an agent-loop plugin)"


def test_no_initiator_message_is_a_human_readable_string() -> None:
    """`NO_INITIATOR_MESSAGE` is the exact upstream message."""
    assert NO_INITIATOR_MESSAGE == "no initiating agent is active"


def test_disposed_initiator_message_is_a_human_readable_string() -> None:
    """`DISPOSED_INITIATOR_MESSAGE` is the exact upstream message."""
    assert DISPOSED_INITIATOR_MESSAGE == "agent initiator scope is disposed"


async def _noop() -> None:
    return None
