"""`taiyi_core_session.types` — session log static type vocabulary.

1:1 Python port of `~/deepseek-harness/packages/core/session/src/types.ts`
(surface types live in `surface.py`; turn-end types live in `turn.py`).

This module covers the structural types: session identity, format version,
todo / epoch-header / request-context records, create-options, and the
44-key :data:`SessionEventMap` plus :data:`KNOWN_SESSION_EVENT_TYPES`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, NewType, TypedDict

# ---------------------------------------------------------------------------
# JSON-safe value domain (mirrors upstream `json.ts`)
# ---------------------------------------------------------------------------

# Recursive JSON-safe type. Mirrors upstream `JsonValue`.
JsonValue = (
    None
    | bool
    | int
    | float
    | str
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


def is_json_value(value: object) -> bool:
    """Return True iff ``value`` is a losslessly-JSON-serializable Python object."""
    import json as _json

    try:
        _json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

# Upstream `Branded<'SessionId'>` — runtime string, statically tagged.
SessionId = NewType("SessionId", str)


def make_session_id(raw: str) -> SessionId:
    """Brand a raw string as a :data:`SessionId` (compile-time cast, no runtime cost)."""
    return SessionId(raw)


# ---------------------------------------------------------------------------
# Session header (durable storage metadata)
# ---------------------------------------------------------------------------


class SessionHeader(TypedDict, total=False):
    """Immutable validated storage metadata, kept outside the conversation event log."""

    version: int
    id: SessionId
    createdAt: int
    cwd: str
    parentSession: SessionId
    seedLength: int
    origin: Literal["subagent"]
    delegationDepth: int
    agentPreset: str


class CreateSessionMeta(TypedDict, total=False):
    """Storage metadata for ``SessionStore.create`` (excludes stamped fields)."""

    cwd: str
    parentSession: SessionId
    createdAt: int
    seedLength: int
    origin: Literal["subagent"]
    delegationDepth: int
    agentPreset: str


class CreateSessionOptions(TypedDict, total=False):
    """Options for creating a Session via the store."""

    seed: Sequence[SessionEvent]
    meta: CreateSessionMeta


class RestoredSessionOptions(TypedDict):
    """Fresh storage values transferred to ``SessionStore.prepare``."""

    seed: list[SessionEvent]
    meta: SessionHeader
    seedSource: Literal["persistence"]


# `prepare`'s parameter union: either CreateSessionOptions (no seedSource) or RestoredSessionOptions.
PrepareSessionOptions = CreateSessionOptions | RestoredSessionOptions


# ---------------------------------------------------------------------------
# Todo / epoch header / request context
# ---------------------------------------------------------------------------


class TodoItem(TypedDict):
    """One entry in an agent's todo list — unit of ``todo/write`` event's whole-list snapshot."""

    content: str
    status: Literal["pending", "in_progress", "completed"]


class EpochHeader(TypedDict, total=False):
    """Logged request state outside derived history."""

    config: Mapping[str, Any]
    adapterDefaults: Mapping[str, bool]
    system: str
    tools: list[Mapping[str, Any]]


class RequestContext(TypedDict, total=False):
    """Registration-bound metadata for one resolved model route."""

    provider: str
    model: str
    contextWindow: int


RequestHeaderReason = Literal["initial", "resume", "change"]


# ---------------------------------------------------------------------------
# Session event map (44 event types)
# ---------------------------------------------------------------------------


class _TurnStartData(TypedDict):
    turn: int


class _TurnEndData(TypedDict):
    turn: int
    reason: Mapping[str, Any]


class _StepStartData(TypedDict):
    turn: int
    step: int


class _StepEndData(TypedDict):
    turn: int
    step: int


class _UserMessageData(TypedDict):
    id: str
    role: Literal["user"]
    source: Mapping[str, Any]
    content: list[Mapping[str, Any]]


class _AssistantChunkData(TypedDict):
    turn: int
    step: int
    chunk: Mapping[str, Any]


class _AssistantMessageData(TypedDict, total=False):
    turn: int
    step: int
    message: Mapping[str, Any]
    usage: Mapping[str, Any]


class _ToolCallData(TypedDict):
    turn: int
    step: int
    callId: str
    name: str
    arguments: str


class _ToolResultData(TypedDict, total=False):
    turn: int
    step: int
    message: Mapping[str, Any]
    error: Mapping[str, str]
    meta: JsonValue


class _TodoWriteData(TypedDict):
    todos: list[TodoItem]


class _RequestHeaderData(TypedDict):
    header: EpochHeader
    reason: RequestHeaderReason


class _RequestContextData(RequestContext):
    pass


class _EmptyData(TypedDict, total=False):
    pass


# Map: event-type name → typed payload dict (used as a registry, not at runtime).
SessionEventMap: dict[str, Any] = {
    "turn/start": _TurnStartData,
    "turn/end": _TurnEndData,
    "step/start": _StepStartData,
    "step/end": _StepEndData,
    "user/message": _UserMessageData,
    "assistant/chunk": _AssistantChunkData,
    "assistant/message": _AssistantMessageData,
    "tool/call": _ToolCallData,
    "tool/result": _ToolResultData,
    "todo/write": _TodoWriteData,
    "request/header": _RequestHeaderData,
    "request/context": _RequestContextData,
    "session/end-seed": _EmptyData,
    # Other core events — payload shape enforced by upstream relational
    # invariant companion; carried as opaque dicts in Phase 0.
    "agent-preset/selected": dict[str, Any],
    "agent/inbox/spliced": dict[str, Any],
    "approval/asked": dict[str, Any],
    "approval/decided": dict[str, Any],
    "approval/policy": dict[str, Any],
    "command/done": dict[str, Any],
    "command/run": dict[str, Any],
    "compaction/end": dict[str, Any],
    "compaction/prune": dict[str, Any],
    "compaction/start": dict[str, Any],
    "compaction/summary": dict[str, Any],
    "feedback/record": dict[str, Any],
    "goal/change": dict[str, Any],
    "hook/invoked": dict[str, Any],
    "hook/result": dict[str, Any],
    "llm/retry": dict[str, Any],
    "llm/retry-started": dict[str, Any],
    "permission/preset": dict[str, Any],
    "plan/mode": dict[str, Any],
    "sandbox/mode": dict[str, Any],
    "schedule/change": dict[str, Any],
    "session/title": dict[str, Any],
    "session/title-llm-request": dict[str, Any],
    "subagent/descriptor": dict[str, Any],
    "tool-workflow/agent-end": dict[str, Any],
    "tool-workflow/agent-start": dict[str, Any],
    "tool-workflow/run-end": dict[str, Any],
    "tool-workflow/run-start": dict[str, Any],
    "tool/call": dict[str, Any],  # noqa: F601 — also typed above as _ToolCallData
    "tool/code-dispatch": dict[str, Any],
    "tool/code-dispatch-start": dict[str, Any],
    "web/deepseek-search-llm-request": dict[str, Any],
}

# Union of all event-type names.
SessionEventType = Literal[
    "turn/start",
    "turn/end",
    "step/start",
    "step/end",
    "user/message",
    "assistant/chunk",
    "assistant/message",
    "tool/call",
    "tool/result",
    "todo/write",
    "request/header",
    "request/context",
    "session/end-seed",
    "agent-preset/selected",
    "agent/inbox/spliced",
    "approval/asked",
    "approval/decided",
    "approval/policy",
    "command/done",
    "command/run",
    "compaction/end",
    "compaction/prune",
    "compaction/start",
    "compaction/summary",
    "feedback/record",
    "goal/change",
    "hook/invoked",
    "hook/result",
    "llm/retry",
    "llm/retry-started",
    "permission/preset",
    "plan/mode",
    "sandbox/mode",
    "schedule/change",
    "session/title",
    "session/title-llm-request",
    "subagent/descriptor",
    "tool-workflow/agent-end",
    "tool-workflow/agent-start",
    "tool-workflow/run-end",
    "tool-workflow/run-start",
    "tool/code-dispatch",
    "tool/code-dispatch-start",
    "web/deepseek-search-llm-request",
]


# Frozenset of all known event types — drives persistence validation.
KNOWN_SESSION_EVENT_TYPES: frozenset[str] = frozenset(
    [
        "agent-preset/selected",
        "agent/inbox/spliced",
        "approval/asked",
        "approval/decided",
        "approval/policy",
        "assistant/chunk",
        "assistant/message",
        "command/done",
        "command/run",
        "compaction/end",
        "compaction/prune",
        "compaction/start",
        "compaction/summary",
        "feedback/record",
        "goal/change",
        "hook/invoked",
        "hook/result",
        "llm/retry",
        "llm/retry-started",
        "permission/preset",
        "plan/mode",
        "request/context",
        "request/header",
        "sandbox/mode",
        "schedule/change",
        "session/end-seed",
        "session/title",
        "session/title-llm-request",
        "step/end",
        "step/start",
        "subagent/descriptor",
        "todo/write",
        "tool-workflow/agent-end",
        "tool-workflow/agent-start",
        "tool-workflow/run-end",
        "tool-workflow/run-start",
        "tool/call",
        "tool/code-dispatch",
        "tool/code-dispatch-start",
        "tool/result",
        "turn/end",
        "turn/start",
        "user/message",
        "web/deepseek-search-llm-request",
    ]
)


# Runtime shape of one session event (a dict carrying the envelope + payload).
SessionEvent = Mapping[str, Any]


__all__ = [
    # JSON domain
    "JsonValue",
    "is_json_value",
    # Identity
    "SessionId",
    "make_session_id",
    # Header / options
    "SessionHeader",
    "CreateSessionMeta",
    "CreateSessionOptions",
    "RestoredSessionOptions",
    "PrepareSessionOptions",
    # Todo / epoch header / request context
    "TodoItem",
    "EpochHeader",
    "RequestContext",
    "RequestHeaderReason",
    # Event map
    "SessionEventMap",
    "SessionEventType",
    "KNOWN_SESSION_EVENT_TYPES",
    "SessionEvent",
]
