"""`taiyi_core_session.session` — Session class + helpers.

1:1 Python port of `~/deepseek-harness/packages/core/session/src/index.ts` —
the Session class surface, all append-path validation helpers, the surface
manager + fold, and the request-header fold.

Public surface (also re-exported from :mod:`taiyi_core_session`):

- :class:`Session` — append-only event log
- :func:`fold_surface`, :class:`SurfaceManager`
- :func:`derive_event_message`, :func:`is_surface_event`, etc.
- :func:`canonical_header`, :func:`header_equals`, :func:`fold_request_header`
- :func:`snapshot_json_value`, :func:`is_json_value`
- :func:`adopt_session_event`, :func:`snapshot_session_event`
"""

from __future__ import annotations

import json
import os
import weakref
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping, Sequence
from copy import deepcopy
from typing import Any, Literal

from cordis import Context

from taiyi_core_session.surface import (
    ReplaceOpDict,
    SurfaceEventType,
    SurfaceIntent,
    SurfaceOp,
    is_surface_eligible_type,
    make_replace_op,
)
from taiyi_core_session.types import (
    KNOWN_SESSION_EVENT_TYPES,
    EpochHeader,
    JsonValue,
    SessionEvent,
    SessionEventType,
    SessionHeader,
    SessionId,
    make_session_id,
)

__all__ = [
    # JSON helpers
    "snapshot_json_value",
    "deep_freeze",
    "freeze_restored_object",
    # Event adoption / snapshot
    "adopt_session_event",
    "snapshot_session_event",
    # Validation
    "validate_session_header",
    "validate_restored_session_header",
    "snapshot_session_header",
    "assert_session_event_envelope",
    "assert_current_llm_shape",
    "assert_message_event_shape",
    "assert_adapter_defaults",
    "assert_supported_request_header",
    "has_provider_model",
    # Surface types (re-exported)
    "SurfaceOp",
    "SurfaceIntent",
    "SurfaceEventType",
    "ReplaceOpDict",
    "make_replace_op",
    # Surface runtime
    "is_surface_event",
    "is_append_surface_event",
    "is_replacement_surface_event",
    "derive_event_message",
    "SurfaceFoldReplacement",
    "SurfaceFoldResult",
    "SessionSurface",
    "fold_surface",
    "SurfaceManager",
    # Request header fold
    "canonical_header",
    "header_equals",
    "fold_request_header",
    # Dispatch helpers
    "collect_session_callbacks",
    "invoke_contained_session_observers",
    # Session class
    "Session",
    "SessionEntry",
    "SessionForkSource",
    "SessionForkErrorCode",
    "SessionForkError",
    "SessionStore",
    "ATTACHMENTS",
]


# ===========================================================================
# JSON helpers
# ===========================================================================


_SENTINEL = object()


class FrozenDict(dict):
    """A dict subclass whose mutation methods raise :class:`TypeError`.

    Mirrors upstream ``Object.freeze`` semantics: the dict keeps its JSON
    shape (so ``json.dumps`` still produces the same wire payload) while
    blocking every mutation entry point — ``__setitem__``,
    ``__delitem__``, ``update``, ``pop``, ``popitem``, ``clear``.
    """

    __slots__ = ()

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("does not support item assignment")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("does not support item deletion")

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        raise TypeError("does not support item assignment")

    def pop(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        raise TypeError("does not support item assignment")

    def popitem(self) -> Any:
        raise TypeError("does not support item assignment")

    def clear(self) -> None:
        raise TypeError("does not support item assignment")


def snapshot_json_value(value: object) -> JsonValue | None:
    """Validate + detach one value through a JSON round-trip.

    Returns the detached snapshot, or ``None`` when the value is not
    losslessly JSON-serializable. Mirrors upstream `snapshotJsonValue`.
    """
    try:
        text = json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def deep_freeze(value: Any) -> Any:
    """Recursively deep-freeze one JSON-safe tree.

    Each nested dict is wrapped in :class:`FrozenDict`, a ``dict`` subclass
    whose mutation methods raise :class:`TypeError`. The wrapper keeps the
    underlying object JSON-serializable (so ``json.dumps`` produces the same
    wire payload as the original dict) while making the structure immutable
    in place — callers holding either the wrapped object or its
    replacement get the same ``TypeError`` on mutation.
    """
    if isinstance(value, MutableMapping):
        for key in list(value.keys()):
            child = value[key]
            if isinstance(child, (Mapping, list)):
                value[key] = deep_freeze(child)
        frozen = FrozenDict(value)
        return frozen
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (Mapping, list)):
                value[index] = deep_freeze(item)
        return value
    return value


def freeze_restored_object(value: Any) -> Any:
    """Iteratively deep-freeze one acyclic JSON tree (no call-stack consumption).

    Mirrors upstream ``freezeRestoredObject``: a worklist-driven traversal that
    freezes every reachable dict/list by wrapping dicts in :class:`FrozenDict`
    and recursing into the original children through ``pending``. Wrapping the
    parent reference first keeps the parent's pointer aligned with the frozen
    view before we queue the original child to descend.
    """
    pending: list[Any] = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            try:
                keys = list(current.keys())
            except TypeError:
                continue
            for key in keys:
                child = current[key]
                if isinstance(child, Mapping):
                    current[key] = FrozenDict(child)
                    pending.append(child)
                elif isinstance(child, list):
                    pending.append(child)
        elif isinstance(current, list):
            for index, item in enumerate(current):
                if isinstance(item, Mapping):
                    current[index] = FrozenDict(item)
                    pending.append(item)
                elif isinstance(item, list):
                    pending.append(item)
    return value


# ===========================================================================
# Session header validation
# ===========================================================================


def _is_safe_int(value: object) -> bool:
    """Return True iff ``value`` is a non-negative safe Python int."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**53


def validate_session_header(id: SessionId, input: object) -> SessionHeader:
    """Validate and freeze one detached creation header in place."""
    if not isinstance(input, Mapping) or isinstance(input, (list, str)):
        raise ValueError("session header is not a plain JSON record")
    record: Mapping[str, Any] = input
    version = record.get("version")
    if version != 0:
        raise ValueError(f"session header version must be 0, got {version!r}")
    if record.get("id") != id:
        raise ValueError(
            f'session header id "{record.get("id")}" does not match session id "{id}"'
        )
    created_at = record.get("createdAt")
    if not _is_safe_int(created_at):
        raise ValueError("session header createdAt must be a non-negative safe integer")
    cwd = record.get("cwd")
    if cwd is not None:
        if not isinstance(cwd, str):
            raise ValueError("session header cwd must be a string")
        if not os.path.isabs(cwd):
            raise ValueError(f'session header cwd must be an absolute path, got "{cwd}"')
    parent_session = record.get("parentSession")
    if parent_session is not None and not isinstance(parent_session, str):
        raise ValueError("session header parentSession must be a string")
    if "seedLength" in record:
        seed_length = record["seedLength"]
        if not _is_safe_int(seed_length):
            raise ValueError("session header seedLength must be a non-negative safe integer")
    origin = record.get("origin")
    if origin is not None and origin != "subagent":
        raise ValueError('session header origin must be "subagent"')
    if "delegationDepth" in record:
        delegation_depth = record["delegationDepth"]
        if not _is_safe_int(delegation_depth):
            raise ValueError("session header delegationDepth must be a non-negative safe integer")
    agent_preset = record.get("agentPreset")
    if agent_preset is not None and not isinstance(agent_preset, str):
        raise ValueError("session header agentPreset must be a string")
    deep_freeze(dict(record))
    return dict(record)  # type: ignore[return-value]


def validate_restored_session_header(id: SessionId, input: object) -> SessionHeader:
    """Validate and freeze one exclusively owned persistence header in place."""
    if input is not None and isinstance(input, Mapping):
        proto = getattr(input, "__class__", None)
        if proto is not None and proto not in (dict, Mapping):
            raise ValueError("session header is not a plain JSON record")
    return validate_session_header(id, input)


def snapshot_session_header(id: SessionId, source: SessionHeader | None = None) -> SessionHeader:
    """Detach, validate, and freeze the creation metadata published by a session."""
    input_payload: object = (
        {"version": 0, "id": id, "createdAt": __import__("time").time_ns() // 1_000_000}
        if source is None
        else source
    )
    snapshot = snapshot_json_value(input_payload)
    if snapshot is None:
        raise ValueError("session header is not losslessly JSON-serializable")
    return validate_session_header(id, snapshot)


# ===========================================================================
# Session event validation
# ===========================================================================

_EVENT_ENVELOPE_KEYS = frozenset(
    {"type", "seq", "time", "data", "surfaceOp", "sourceEventSeqs", "ignorable"}
)


def has_provider_model(value: object) -> bool:
    """Return True iff ``value`` is an object carrying a non-empty provider + model."""
    if not isinstance(value, Mapping):
        return False
    provider = value.get("provider")
    model = value.get("model")
    return (
        isinstance(provider, str)
        and bool(provider)
        and isinstance(model, str)
        and bool(model)
    )


def assert_adapter_defaults(
    value: object,
    config: Mapping[str, Any],
    index: int,
) -> None:
    """Validate adapter-default markers imported from a durable request header."""
    if value is None:
        return
    if not isinstance(value, Mapping) or isinstance(value, list):
        raise ValueError(f"seed request/header at index {index} has invalid adapterDefaults")
    defaults = value
    allowed = {"reasoningEffort", "maxTokens"}
    if any(k not in allowed for k in defaults.keys()):
        raise ValueError(f"seed request/header at index {index} has invalid adapterDefaults")
    if any(v is not True for v in defaults.values()):
        raise ValueError(f"seed request/header at index {index} has invalid adapterDefaults")
    if defaults.get("reasoningEffort") is True and config.get("reasoningEffort") is None:
        raise ValueError(f"seed request/header at index {index} has invalid adapterDefaults")
    if defaults.get("maxTokens") is True and config.get("maxTokens") is None:
        raise ValueError(f"seed request/header at index {index} has invalid adapterDefaults")


def assert_message_event_shape(event: Mapping[str, Any], subject: str) -> None:
    """Validate the message envelope inside a user/assistant/tool event."""
    event_type = event.get("type")
    if event_type not in ("user/message", "assistant/message", "tool/result"):
        return
    data = event.get("data")
    record = data if isinstance(data, Mapping) else None
    message = data if event_type == "user/message" else (record.get("message") if record else None)
    if not isinstance(message, Mapping):
        raise ValueError(f"{subject} lacks an identified message")
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise ValueError(f"{subject} lacks an identified message")
    expected_role = "assistant" if event_type == "assistant/message" else "user"
    if message.get("role") != expected_role:
        raise ValueError(f'{subject} message must have role "{expected_role}"')
    source = message.get("source")
    if not isinstance(source, Mapping):
        raise ValueError(f"{subject} message has invalid source")
    source_kind = source.get("kind")
    if not isinstance(source_kind, str) or not source_kind:
        raise ValueError(f"{subject} message has invalid source")
    content = message.get("content")
    if not isinstance(content, list):
        raise ValueError(f"{subject} message has invalid content")
    if event_type == "assistant/message":
        if source_kind != "model" or not has_provider_model(source):
            raise ValueError(f"{subject} message must have model source")
        return
    if event_type != "tool/result":
        return
    if source_kind != "tool":
        raise ValueError(f"{subject} message must have tool source")
    call_id = source.get("callId")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError(f"{subject} message must have tool source")
    if len(content) != 1:
        raise ValueError(f"{subject} message must contain one tool-result block")
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "tool-result":
        raise ValueError(f"{subject} message must contain one tool-result block")
    if not isinstance(block.get("content"), list):
        raise ValueError(f"{subject} message must contain one tool-result block")
    if block.get("toolCallId") != call_id:
        raise ValueError(f"{subject} message has mismatched tool call ids")


def assert_current_llm_shape(event: Mapping[str, Any], index: int) -> None:
    """Reject obsolete request headers and malformed messages at the seed/load boundary."""
    event_type = event.get("type")
    data = event.get("data")
    record = data if isinstance(data, Mapping) else None
    if event_type == "request/header":
        header = record.get("header") if record else None
        header_record = header if isinstance(header, Mapping) and not isinstance(header, list) else None
        if header_record is None:
            raise ValueError(f"seed request/header at index {index} lacks provider/model")
        config = header_record.get("config")
        if not has_provider_model(config):
            raise ValueError(f"seed request/header at index {index} lacks provider/model")
        reasoning_effort = config.get("reasoningEffort")
        if reasoning_effort is not None:
            if not isinstance(reasoning_effort, str) or not reasoning_effort:
                raise ValueError(f"seed request/header at index {index} has an invalid reasoningEffort")
        adapter_defaults = header_record.get("adapterDefaults")
        assert_adapter_defaults(adapter_defaults, config, index)
    if event_type not in ("user/message", "assistant/message", "tool/result"):
        return
    assert_message_event_shape(event, f"seed {event_type} at index {index}")


def assert_supported_request_header(event_type: str, data: object, location: str) -> None:
    """Reject request-header vocabulary removed with the legacy delta codec."""
    if event_type == "request/header-delta":
        raise ValueError(f"{location} uses unsupported legacy request/header-delta format")
    if event_type == "request/header" and isinstance(data, Mapping) and not isinstance(data, list):
        if data.get("reason") == "fallback":  # type: ignore[union-attr]
            raise ValueError(f'{location} uses unsupported legacy request/header reason "fallback"')


def assert_session_event_envelope(value: Mapping[str, Any], index: int) -> None:
    """Validate the fixed event envelope after one-pass JSON materialization."""
    if value.get("type") == "request/header-delta":
        raise ValueError(f"seed event at index {index} uses unsupported legacy request/header-delta format")
    for key in value.keys():
        if key not in _EVENT_ENVELOPE_KEYS:
            raise ValueError(f"seed event at index {index} has an invalid event envelope")
    event_type = value.get("type")
    seq = value.get("seq")
    time = value.get("time")
    ignorable = value.get("ignorable")
    if (
        not isinstance(event_type, str)
        or not isinstance(seq, int) or isinstance(seq, bool) or not (0 <= seq < 2**53)
        or not isinstance(time, int) or isinstance(time, bool)
        or value.get("data") is None
        or (ignorable is not None and ignorable is not True)
    ):
        raise ValueError(f"seed event at index {index} has an invalid event envelope")
    if event_type in ("request/header", "user/message", "assistant/message", "tool/result"):
        assert_current_llm_shape(value, index)


# ===========================================================================
# Event adoption / snapshot
# ===========================================================================


def adopt_session_event(event: SessionEvent) -> SessionEvent:
    """Validate one exclusively-owned event and deeply freeze its identified message.

    Returns the same event object after wrapping nested data dicts in
    read-only :class:`FrozenDict` views. Mutation attempts on the returned
    nested dicts raise :class:`TypeError`. Non-message events (no identified
    message to freeze) pass through unchanged. ``assert_message_event_shape``
    has already verified the message shape, so the freeze calls run
    unconditionally on the validated message.
    """
    assert_message_event_shape(event, f'session event at seq {event.get("seq")}')
    event_type = event.get("type")
    if event_type == "user/message":
        event["data"] = deep_freeze(dict(event.get("data", {})))
    elif event_type in ("assistant/message", "tool/result"):
        data = dict(event.get("data", {}))
        data["message"] = deep_freeze(dict(data.get("message", {})))
        event["data"] = data
    return event


def snapshot_session_event(event: SessionEvent) -> SessionEvent:
    """Detach one event as a fresh deep copy that remains mutable by callers.

    Returns a deepcopy of ``event``. Unlike :func:`adopt_session_event`, the
    returned snapshot is NOT deep-frozen, so a downstream consumer can
    extend or rewrite the event before appending it to a fresh log.
    """
    return deepcopy(dict(event))


# ===========================================================================
# Dispatch helpers
# ===========================================================================


def _unwrap_cordis_callback(callback: Callable[..., Any]) -> Callable[..., Any]:
    """Unwrap a cordis listener wrapper so the original callable can be invoked directly.

    The cordis Python port wraps free-function listeners with a closure that
    prepends ``this_arg`` (the context). Upstream TS instead uses ``cb.bind(this)``
    which sets ``this`` without adding an extra arg. To match upstream's
    call-shape semantics for free-function session listeners, we strip the
    cordis wrapper and return the underlying function so callers can pass
    only the event payload.
    """
    closure = getattr(callback, "__closure__", None)
    if closure:
        for cell in closure:
            try:
                value = cell.cell_contents
            except Exception:  # pragma: no cover
                continue
            if callable(value):
                return value
    # Bound methods (skipped by cordis wrapping) return unchanged.
    return callback


def collect_session_callbacks(ctx: Context, args: Sequence[Any]) -> list[Callable[..., Any]]:
    """Resolve one listener snapshot via cordis `ctx.events.dispatch('emit', ...)`.

    Mirrors upstream `collectSessionCallbacks` semantics: returns the
    resolved listener list (not the dispatch tuple). The caller must have
    stripped the event name from ``args`` and prepended the carrier + name.
    """
    try:
        result = ctx.events.dispatch("emit", list(args))
    except Exception:
        return []
    return list(result[0]) if result and result[0] else []


def invoke_contained_session_observers(
    ctx: Context,
    name: str,
    id: SessionId,
    args: Sequence[Any],
    callbacks: Sequence[Callable[..., Any]],
) -> None:
    """Invoke observe-only listeners with per-listener error containment."""
    for callback in callbacks:
        target = _unwrap_cordis_callback(callback)
        try:
            returned = target(*args)
        except Exception as error:  # noqa: BLE001
            try:
                ctx.logger.warn(f'session "{id}": {name} listener threw: {error}')
            except Exception:  # pragma: no cover — defensive
                pass
            continue
        if returned is not None and hasattr(returned, "__await__"):
            try:
                coro = returned
                coro.close()  # type: ignore[union-attr]
            except Exception:  # pragma: no cover — defensive
                pass


# ===========================================================================
# Surface runtime (1:1 port of upstream `surface.ts`)
# ===========================================================================


_SURFACE_EVENT_TYPES = frozenset({"user/message", "assistant/message", "tool/result"})


def is_surface_event(event: Mapping[str, Any]) -> bool:
    """Narrow an event to a surface-eligible event carrying its required marker."""
    if event.get("type") not in _SURFACE_EVENT_TYPES:
        return False
    return event.get("surfaceOp") is not None


def is_append_surface_event(event: Mapping[str, Any]) -> bool:
    """Narrow to an append-origin surface event (the durable transcript source)."""
    return is_surface_event(event) and event.get("surfaceOp") == "append"


def is_replacement_surface_event(event: Mapping[str, Any]) -> bool:
    """Narrow to a surface replacement node (shadowed prior range)."""
    return is_surface_event(event) and event.get("surfaceOp") != "append"


def derive_event_message(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Project one event into the LLM message it derives to, or None.

    Non-surface events (chunks, boundaries, log-only records) return None.
    Empty-content assistant/message returns None — such events exist only
    to host usage.
    """
    event_type = event.get("type")
    data = event.get("data") or {}
    if event_type == "user/message":
        return data
    if event_type == "assistant/message":
        msg = data.get("message") if isinstance(data, Mapping) else None
        if isinstance(msg, Mapping) and len(msg.get("content") or []) == 0:
            return None
        return msg
    if event_type == "tool/result":
        msg = data.get("message") if isinstance(data, Mapping) else None
        return msg
    return None


class SurfaceFoldReplacement:
    """One replacement operation observed while folding a session surface."""

    __slots__ = ("seq", "start", "end", "shadowed_seqs")

    def __init__(self, seq: int, start: int, end: int, shadowed_seqs: Sequence[int]) -> None:
        self.seq = seq
        self.start = start
        self.end = end
        self.shadowed_seqs: list[int] = list(shadowed_seqs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SurfaceFoldReplacement(seq={self.seq}, start={self.start}, "
            f"end={self.end}, shadowed_seqs={self.shadowed_seqs!r})"
        )


class SurfaceFoldResult:
    """Complete result of replaying the surface operations in a session log."""

    __slots__ = ("nodes", "replacements")

    def __init__(
        self,
        nodes: Sequence[int],
        replacements: Sequence[SurfaceFoldReplacement],
    ) -> None:
        self.nodes: list[int] = list(nodes)
        self.replacements: list[SurfaceFoldReplacement] = list(replacements)

    def __repr__(self) -> str:  # pragma: no cover
        return f"SurfaceFoldResult(nodes={self.nodes!r}, replacements={self.replacements!r})"


class SessionSurface:
    """Readonly live projection of the message-producing session events."""

    __slots__ = ("_nodes", "_replace_generation")

    def __init__(self, nodes: Sequence[int], replace_generation: int) -> None:
        self._nodes: list[int] = list(nodes)
        self._replace_generation: int = replace_generation

    @property
    def nodes(self) -> list[int]:
        """Current surface event sequences in model-visible order."""
        return list(self._nodes)

    @property
    def replace_generation(self) -> int:
        """Monotonic count of committed positional replacements."""
        return self._replace_generation


def _is_event_seq(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**53


def _is_replace_op(value: Mapping[str, Any]) -> bool:
    return (
        set(value.keys()) == {"op", "start", "end"}
        and value.get("op") == "replace"
        and _is_event_seq(value.get("start"))
        and _is_event_seq(value.get("end"))
    )


def _surface_op_of(event: Mapping[str, Any]) -> SurfaceOp | None:
    """Validate event-local surface eligibility; return the op or None."""
    event_type = event.get("type")
    surface_op = event.get("surfaceOp")
    source_seqs = event.get("sourceEventSeqs")
    if not is_surface_eligible_type(event_type or ""):
        if surface_op is not None:
            raise ValueError(
                f'session event "{event_type}" is not surface-eligible and cannot carry surfaceOp'
            )
        if source_seqs is not None:
            raise ValueError(
                f'session event "{event_type}" is not surface-eligible and cannot carry sourceEventSeqs'
            )
        return None
    if surface_op is None:
        raise ValueError(
            f'session event "{event_type}" is surface-eligible and requires a surfaceOp marker'
        )
    if surface_op == "append":
        return "append"  # type: ignore[return-value]
    if not isinstance(surface_op, Mapping):
        raise ValueError(f'session event "{event_type}" carries an invalid surfaceOp')
    if not _is_replace_op(surface_op):
        raise ValueError(f'session event "{event_type}" carries an invalid replace surfaceOp')
    return {"op": "replace", "start": surface_op["start"], "end": surface_op["end"]}


def _assert_provenance(event: Mapping[str, Any], shadowed_seqs: Sequence[int]) -> None:
    """Validate cited source-event seqs against prior log entries + replacement range."""
    raw = event.get("sourceEventSeqs")
    sources: list[int] = []
    if raw is not None:
        if not isinstance(raw, list):
            raise ValueError(f"sourceEventSeqs on event at seq {event.get('seq')} must be an array when present")
        if len(raw) == 0 and event.get("type") != "assistant/message":
            raise ValueError("sourceEventSeqs must not be empty except on assistant/message")
        for source in raw:
            if not _is_event_seq(source):
                raise ValueError(
                    f'session event "{event.get("type")}" sourceEventSeqs must densely contain non-negative safe integers'
                )
            if source >= event["seq"]:
                raise ValueError(
                    f"sourceEventSeqs must reference earlier events: {source} >= current seq {event['seq']}"
                )
            sources.append(source)
        if len(set(sources)) != len(sources):
            raise ValueError("sourceEventSeqs must not contain duplicates")
    missing = [s for s in shadowed_seqs if s not in set(sources)]
    if missing:
        raise ValueError(
            f"surface replace: sourceEventSeqs must include every shadowed surface node; missing {', '.join(str(m) for m in missing)}"
        )


def _replacement_range(
    state_nodes: list[int],
    op: Mapping[str, Any],
) -> tuple[int, int, list[int]]:
    try:
        start_idx = state_nodes.index(op["start"])
    except ValueError as err:
        raise ValueError(f"surface replace: start seq {op['start']} not found in surface") from err
    try:
        end_idx = state_nodes.index(op["end"])
    except ValueError as err:
        raise ValueError(f"surface replace: end seq {op['end']} not found in surface") from err
    if start_idx > end_idx:
        raise ValueError(
            f"surface replace: start seq {op['start']} (index {start_idx}) is after end seq {op['end']} (index {end_idx})"
        )
    return start_idx, end_idx, state_nodes[start_idx : end_idx + 1]


def _plan_surface_event(
    state_nodes: list[int],
    event: Mapping[str, Any],
    expected_seq: int,
) -> tuple[str, Any] | None:
    """Validate one event at its replay boundary; return ('append', seq) | ('replace', plan)."""
    if event.get("seq") != expected_seq:
        raise ValueError(
            f"session event seq {event.get('seq')} is not contiguous; expected {expected_seq}"
        )
    surface_op = _surface_op_of(event)
    if surface_op is None:
        return None
    if surface_op == "append":
        _assert_provenance(event, [])
        return ("append", expected_seq)
    start_idx, end_idx, shadowed_seqs = _replacement_range(state_nodes, surface_op)
    _assert_provenance(event, shadowed_seqs)
    return (
        "replace",
        {
            "kind": "replace",
            "seq": expected_seq,
            "start": surface_op["start"],
            "end": surface_op["end"],
            "start_idx": start_idx,
            "end_idx": end_idx,
            "shadowed_seqs": shadowed_seqs,
        },
    )


def _apply_surface_event(
    state_nodes: list[int],
    state_replace_gen: list[int],
    event: Mapping[str, Any],
    expected_seq: int,
) -> SurfaceFoldReplacement | None:
    plan = _plan_surface_event(state_nodes, event, expected_seq)
    if plan is None:
        return None
    kind, payload = plan
    if kind == "append":
        state_nodes.append(payload)
        return None
    # replace
    state_nodes[payload["start_idx"] : payload["end_idx"] + 1] = [payload["seq"]]
    state_replace_gen[0] += 1
    return SurfaceFoldReplacement(
        seq=payload["seq"],
        start=payload["start"],
        end=payload["end"],
        shadowed_seqs=payload["shadowed_seqs"],
    )


def fold_surface(events: Sequence[Mapping[str, Any]]) -> SurfaceFoldResult:
    """Replay a complete session log through the canonical surface fold."""
    state_nodes: list[int] = []
    state_replace_gen: list[int] = [0]
    replacements: list[SurfaceFoldReplacement] = []
    for index, event in enumerate(events):
        replacement = _apply_surface_event(state_nodes, state_replace_gen, event, index)
        if replacement is not None:
            replacements.append(replacement)
    return SurfaceFoldResult(state_nodes, replacements)


class SurfaceManager:
    """Incremental ordered surface view and append-boundary validator."""

    def __init__(
        self,
        log_provider: Callable[[], Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
    ) -> None:
        self._state_nodes: list[int] = []
        self._state_replace_gen: list[int] = [0]
        self._last_processed_seq: int = -1
        self._pending_plan: tuple[Mapping[str, Any], int, tuple[str, Any] | None] | None = None
        if callable(log_provider):
            self._log_provider: Callable[[], Sequence[Mapping[str, Any]]] = log_provider
        else:
            snapshot = list(log_provider)
            self._log_provider = lambda: snapshot

    def _current_log(self) -> list[Mapping[str, Any]]:
        return list(self._log_provider())

    def _process_delta(self) -> None:
        log = self._current_log()
        if not log:
            return
        tail_seq = len(log) - 1
        for seq in range(self._last_processed_seq + 1, tail_seq + 1):
            event = log[seq]
            pending = self._pending_plan
            if pending is not None and pending[0] is event and pending[1] == seq:
                plan = pending[2]
                if plan is None:
                    pass
                elif plan[0] == "append":
                    self._state_nodes.append(plan[1])
                else:
                    payload = plan[1]
                    self._state_nodes[payload["start_idx"] : payload["end_idx"] + 1] = [payload["seq"]]
                    self._state_replace_gen[0] += 1
            else:
                _apply_surface_event(self._state_nodes, self._state_replace_gen, event, seq)
            if pending is not None and pending[1] <= seq:
                self._pending_plan = None
            self._last_processed_seq = seq

    @property
    def replace_generation(self) -> int:
        self._process_delta()
        return self._state_replace_gen[0]

    @property
    def nodes(self) -> list[int]:
        self._process_delta()
        return list(self._state_nodes)

    def validate_next(self, event: Mapping[str, Any]) -> None:
        self._process_delta()
        expected_seq = len(self._current_log())
        plan = _plan_surface_event(self._state_nodes, event, expected_seq)
        self._pending_plan = (event, expected_seq, plan)

    def update_log(self, log: Sequence[Mapping[str, Any]]) -> None:
        self._log_provider = lambda log=log: log
        self._pending_plan = None


# ===========================================================================
# Request-header fold (canonical, equality, fold)
# ===========================================================================


def canonical_header(header: EpochHeader | Mapping[str, Any]) -> Mapping[str, Any]:
    """Normalize a header to canonical form: empty system/tools become absent."""
    out: dict[str, Any] = {"config": header.get("config")}
    adapter_defaults = header.get("adapterDefaults")
    if isinstance(adapter_defaults, Mapping) and (
        adapter_defaults.get("reasoningEffort") is True
        or adapter_defaults.get("maxTokens") is True
    ):
        out["adapterDefaults"] = dict(adapter_defaults)
    system = header.get("system")
    if isinstance(system, str) and len(system) > 0:
        out["system"] = system
    tools = header.get("tools")
    if isinstance(tools, list) and len(tools) > 0:
        out["tools"] = list(tools)
    return out


def _same_schema(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True, separators=(",", ":")) == json.dumps(
        b, sort_keys=True, separators=(",", ":")
    )


def header_equals(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Field-wise equality over canonical headers (config, system, tools)."""
    a_defaults = a.get("adapterDefaults") or {}
    b_defaults = b.get("adapterDefaults") or {}
    if (
        json.dumps(a.get("config"), sort_keys=True, separators=(",", ":"))
        != json.dumps(b.get("config"), sort_keys=True, separators=(",", ":"))
        or a_defaults.get("reasoningEffort") != b_defaults.get("reasoningEffort")
        or a_defaults.get("maxTokens") != b_defaults.get("maxTokens")
        or a.get("system") != b.get("system")
    ):
        return False
    at = a.get("tools") or []
    bt = b.get("tools") or []
    if not isinstance(at, list) or not isinstance(bt, list):
        return False
    if len(at) != len(bt):
        return False
    return all(
        _same_schema(a_item, b_item)  # type: ignore[arg-type]
        for a_item, b_item in zip(at, bt, strict=True)
    )


def fold_request_header(
    events: Iterable[Mapping[str, Any]],
    from_state: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    """Fold request-header events into the latest canonical header."""
    state: Mapping[str, Any] | None = from_state
    for event in events:
        if event.get("type") == "request/header":
            data = event.get("data") or {}
            if isinstance(data, Mapping):
                header = data.get("header")
                if isinstance(header, Mapping):
                    state = canonical_header(header)
    return state


# ===========================================================================
# Session class
# ===========================================================================


class Session:
    """Event-sourced session: append-only log of SessionEvents.

    Plain class (not a Service). Create live instances via ``ctx.sessions.create()``
    and detached instances via :meth:`create` / :meth:`from_restore`.
    """

    def __init__(  # noqa: D107 — internal constructor; public surface is `create` / `from_restore`
        self,
        id: SessionId,
        seed: Sequence[SessionEvent] | None = None,
        header: SessionHeader | None = None,
        mode: str = "snapshot",
        _validate_header: bool = True,
    ) -> None:
        self._id_value = id
        self._log: list[SessionEvent] = []
        self._events_snapshot: list[SessionEvent] | None = None
        self._header_fold: Mapping[str, Any] | None = None
        self._header_fold_seq = 0
        self._context_fold: Mapping[str, Any] | None = None
        self._context_fold_seq = 0
        self._derived: list[Mapping[str, Any]] = []
        self._derived_nodes = 0
        self._derived_generation = 0

        restored_header: SessionHeader | None = None
        if mode == "restore":
            restored_header = validate_restored_session_header(id, header)
        # Establish the surface manager first so seed validation can use it.
        self._surface_manager = SurfaceManager(lambda: self._log)
        # Validate seed events and adopt them.
        if seed is not None:
            for index, source in enumerate(seed):
                if mode == "restore":
                    snapshot: SessionEvent = source  # type: ignore[assignment]
                else:
                    snap = snapshot_json_value(source)
                    if snap is None:
                        raise ValueError(f"seed event at index {index} is not losslessly JSON-serializable")
                    snapshot = snap  # type: ignore[assignment]
                assert_session_event_envelope(snapshot, index)
                assert_supported_request_header(
                    snapshot.get("type", ""),  # type: ignore[arg-type]
                    snapshot.get("data"),
                    f"seed event at index {index}",
                )
                if snapshot.get("seq") != index:
                    raise ValueError(
                        f"seed event at index {index} has seq {snapshot.get('seq')} (expected {index}); seed must be contiguous from 0"
                    )
                try:
                    self._surface_manager.validate_next(snapshot)
                except (ValueError, Exception) as error:
                    raise ValueError(
                        f"invalid seed event at index {index}: {error}"
                    ) from error
                if mode == "restore":
                    freeze_restored_object(snapshot)
                else:
                    deep_freeze(snapshot)
                self._log.append(snapshot)  # type: ignore[arg-type]

        # Establish the surface manager over the loaded log.

        self._first_live_seq = len(self._log)

        # Establish the header.
        if mode == "restore" and restored_header is not None:
            self._header_dict: SessionHeader = dict(restored_header)
        elif header is not None:
            self._header_dict = snapshot_session_header(id, header)
        else:
            self._header_dict = snapshot_session_header(id)

        # Append session/end-seed if seed supplied and last event is not already one.
        # An empty seed produces an empty log (no marker appended) so forking
        # an empty source with no boundary yields a child with no events.
        if (
            seed is not None
            and len(seed) > 0
            and (not self._log or self._log[-1].get("type") != "session/end-seed")
        ):
            self._append_internal(
                "session/end-seed",
                {},
                surface_intent=None,
                publish=False,
            )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        id: SessionId,
        seed: Sequence[SessionEvent] | None = None,
        header: SessionHeader | None = None,
    ) -> Session:
        """Build a detached session by validating + snapshotting borrowed seed."""
        return Session(id, seed, header, mode="snapshot")

    @staticmethod
    def from_restore(
        id: SessionId,
        seed: Sequence[SessionEvent],
        header: SessionHeader,
    ) -> Session:
        """Restore a detached session by taking ownership of fresh persistence values."""
        return Session(id, seed, header, mode="restore")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> SessionId:
        """The session identity, derived from its durable header's single copy."""
        return self._id_value

    @property
    def header(self) -> SessionHeader:
        """The immutable validated storage metadata."""
        return self._header_dict

    @property
    def first_live_seq(self) -> int:
        """First seq appended IN THIS PROCESS (length of constructor seed; 0 without one)."""
        return self._first_live_seq

    @property
    def events(self) -> tuple[SessionEvent, ...]:
        """Immutable snapshot of the append-only event log (reused until next append)."""
        if self._events_snapshot is None:
            self._events_snapshot = list(self._log)
        return tuple(self._events_snapshot)

    @property
    def seq(self) -> int:
        """Next event's sequence number (= log length; contiguity contract)."""
        return len(self._log)

    @property
    def surface(self) -> SessionSurface:
        """The ordered surface over this session's event log."""
        return SessionSurface(self._surface_manager.nodes, self._surface_manager.replace_generation)

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(
        self,
        type: SessionEventType,
        data: Mapping[str, Any],
        surface_intent: SurfaceIntent | None = None,
    ) -> SessionEvent:
        """Append one typed event and synchronously notify store-owned observers."""
        return self._append_internal(type, data, surface_intent=surface_intent, publish=True)

    def _append_internal(
        self,
        type: SessionEventType,
        data: Mapping[str, Any],
        surface_intent: SurfaceIntent | None,
        publish: bool,
    ) -> SessionEvent:
        surface_metadata: dict[str, Any] = {}
        if surface_intent is not None:
            if "sourceEventSeqs" in surface_intent:
                surface_metadata["sourceEventSeqs"] = surface_intent["sourceEventSeqs"]
            if "surfaceOp" in surface_intent:
                surface_metadata["surfaceOp"] = surface_intent["surfaceOp"]
        data_snapshot = snapshot_json_value(data)
        if data_snapshot is None:
            raise ValueError(f'session event "{type}" carries non-JSON-serializable data')
        assert_supported_request_header(type, data_snapshot, f'session event "{type}"')
        surface_meta_snapshot = snapshot_json_value(surface_metadata)
        if surface_meta_snapshot is None:
            raise ValueError(f'session event "{type}" carries non-JSON-serializable surface metadata')
        if type not in KNOWN_SESSION_EVENT_TYPES:
            raise ValueError(f'event type "{type}" is not in KNOWN_SESSION_EVENT_TYPES')
        event_dict: dict[str, Any] = {
            "type": type,
            "seq": len(self._log),
            "time": __import__("time").time_ns() // 1_000_000,
            "data": data_snapshot,
        }
        if "surfaceOp" in surface_meta_snapshot:
            event_dict["surfaceOp"] = surface_meta_snapshot["surfaceOp"]
        if "sourceEventSeqs" in surface_meta_snapshot:
            event_dict["sourceEventSeqs"] = surface_meta_snapshot["sourceEventSeqs"]
        # Validate the event against surface manager.
        self._surface_manager.validate_next(event_dict)
        self._log.append(event_dict)
        self._events_snapshot = None
        if publish:
            self._publish_event(event_dict)
        return event_dict

    def _publish_event(self, event: SessionEvent) -> None:
        """Forward one committed event to the store-owned observers."""
        try:
            entry = ATTACHMENTS.get(self)
        except Exception:
            entry = None
        if entry is None:
            return
        if entry.appending:
            raise RuntimeError("session append cannot reenter while another append is being published")
        try:
            entry.appending = True
            args: list[Any] = [entry.carrier, "session/event", self, event]
            callbacks = collect_session_callbacks(entry.emit_ctx, args)
            invoke_contained_session_observers(
                entry.emit_ctx, "session/event", entry.id, [self, event, "session/event"], callbacks
            )
        finally:
            entry.appending = False
            if entry.detach_requested and not entry.appending:
                try:
                    entry.detach()
                except Exception:  # pragma: no cover
                    pass

    # ------------------------------------------------------------------
    # Header / context fold
    # ------------------------------------------------------------------

    def request_header(self) -> Mapping[str, Any] | None:
        """The EpochHeader in force after the log's last header event."""
        if self._header_fold_seq < len(self._log):
            tail = self._log[self._header_fold_seq :]
            self._header_fold = fold_request_header(tail, self._header_fold)
            self._header_fold_seq = len(self._log)
        return self._header_fold

    def request_context(self) -> Mapping[str, Any] | None:
        """The latest resolved route metadata, or undefined before the first event."""
        if self._context_fold_seq < len(self._log):
            for event in self._log[self._context_fold_seq :]:
                if event.get("type") == "request/context":
                    data = event.get("data") or {}
                    if isinstance(data, Mapping):
                        self._context_fold = dict(data)
            self._context_fold_seq = len(self._log)
        return self._context_fold

    # ------------------------------------------------------------------
    # Derived messages
    # ------------------------------------------------------------------

    def derive_messages(self) -> list[Mapping[str, Any]]:
        """Derive the LLM message history by walking the surface."""
        nodes = self._surface_manager.nodes
        generation = self._surface_manager.replace_generation
        if generation != self._derived_generation:
            self._derived = []
            self._derived_nodes = 0
            self._derived_generation = generation
        for seq in nodes[self._derived_nodes :]:
            if seq < 0 or seq >= len(self._log):
                continue
            event = self._log[seq]
            msg = derive_event_message(event)
            if msg is not None:
                self._derived.append(msg)
        self._derived_nodes = len(nodes)
        return list(self._derived)

    def derive_event_message(self, event: SessionEvent) -> Mapping[str, Any] | None:
        """Instance face of the pure per-node `derive_event_message` export."""
        return derive_event_message(event)


# ===========================================================================
# SessionStore
# ===========================================================================


# Attachments map: Session instance → entry that owns publication hooks.
ATTACHMENTS: weakref.WeakKeyDictionary[Session, SessionEntry] = weakref.WeakKeyDictionary()


class SessionEntry:
    """All mutable lifecycle state for one exact store entry."""

    __slots__ = (
        "id",
        "session",
        "carrier",
        "emit_ctx",
        "announced",
        "announcing",
        "appending",
        "detach_requested",
        "detach",
    )

    def __init__(
        self,
        id: SessionId,
        session: Session,
        carrier: Any,
        emit_ctx: Context,
        detach_fn: Callable[[], None],
    ) -> None:
        self.id = id
        self.session = session
        self.carrier = carrier
        self.emit_ctx = emit_ctx
        self.announced = False
        self.announcing = False
        self.appending = False
        self.detach_requested = False
        self.detach = detach_fn


SessionForkSource = Session | SessionId

SessionForkErrorCode = (
    Literal["SESSION_NOT_FOUND"]
    | Literal["SESSION_NOT_LIVE"]
    | Literal["SESSION_ALREADY_EXISTS"]
    | Literal["INVALID_BOUNDARY"]
    | Literal["OPEN_TURN"]
)


class SessionForkError(Exception):
    """Typed error for session fork rejections."""

    def __init__(self, message: str, code: SessionForkErrorCode) -> None:
        super().__init__(message)
        self.code = code

    def __repr__(self) -> str:  # pragma: no cover
        return f"SessionForkError({self.args[0]!r}, code={self.code!r})"


class SessionStore:
    """In-memory session store (ctx.sessions). Persistence is a plugin concern."""

    def __init__(self, ctx: Context) -> None:  # noqa: D107
        from cordis import Service

        self._ctx = ctx
        self._store: dict[SessionId, SessionEntry] = {}
        self._counter = 0
        # Mirror upstream `super(ctx, 'sessions')` so the cordis Service base
        # picks up the lifecycle hooks. Direct usage without subclassing is
        # acceptable for Phase 0 because we drive dispose manually.
        self._service_base = Service.__new__(Service)
        self._service_base.__init__(ctx, **{})

    # ------------------------------------------------------------------
    # Construction transactions
    # ------------------------------------------------------------------

    def create(
        self,
        id: SessionId | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> Session:
        """Create a session owned by the calling fiber (lifecycle-coupled)."""
        options_dict: dict[str, Any] = dict(options or {})
        session = self.prepare(id, options_dict)
        detach = self.enter(session)
        # Single effect owned by the calling fiber (Python port: register the
        # detach disposer as a context effect so it fires on ctx.dispose).
        self._ctx.effect(detach, label="sessions.create()")
        self.announce(session)
        return session

    def prepare(
        self,
        id: SessionId | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> Session:
        """Build a session WITHOUT entering it into the store."""
        options_dict: dict[str, Any] = dict(options or {})
        if id is None:
            session_id: SessionId
            while True:
                session_id = make_session_id(f"session-{self._counter + 1}")
                self._counter += 1
                if session_id not in self._store:
                    break
        else:
            session_id = make_session_id(str(id))
        if session_id in self._store:
            raise ValueError(f'session "{session_id}" already exists')
        seed_source = options_dict.get("seedSource")
        if seed_source == "persistence":
            seed = options_dict.get("seed", [])
            meta = options_dict.get("meta", {})
            return Session.from_restore(session_id, list(seed), meta)
        seed = options_dict.get("seed")
        meta = options_dict.get("meta", {})
        header: dict[str, Any] = {
            "version": 0,
            "id": session_id,
            "createdAt": meta.get("createdAt", __import__("time").time_ns() // 1_000_000),
        }
        for key in ("cwd", "parentSession", "seedLength", "origin", "delegationDepth", "agentPreset"):
            if key in meta and meta[key] is not None:
                header[key] = meta[key]
        return Session.create(session_id, seed, header)

    def enter(self, session: Session) -> Callable[[], None]:
        """Enter a prepared session into the store. Returns a detach disposer."""
        # Lazy import scope package here to avoid an import cycle at module load.
        from taiyi_core_scope import scope_of as _scope_of
        from taiyi_core_scope import scope_target as _scope_target

        id = session.id
        carrier = _scope_target(session, _scope_of(self._ctx))
        if id in self._store:
            raise ValueError(f'session "{id}" already exists')
        if session in ATTACHMENTS:
            raise ValueError(f'session "{id}" is already attached to a store')
        store_ref = self

        def _detach_now() -> None:
            entry = store_ref._store.get(id)
            if entry is None:
                return
            store_ref._store.pop(id, None)
            try:
                ATTACHMENTS.pop(session, None)
            except Exception:  # pragma: no cover
                pass
            if entry.announced:
                store_ref._emit_disposed(entry)

        entry = SessionEntry(
            id=id,
            session=session,
            carrier=carrier,
            emit_ctx=self._ctx,
            detach_fn=_detach_now,
        )
        self._store[id] = entry
        ATTACHMENTS[session] = entry
        entered = True

        def detach() -> None:
            nonlocal entered
            if not entered:
                return
            entered = False
            if entry.announcing or entry.appending:
                entry.detach_requested = True
                return
            _detach_now()

        return detach

    def announce(self, session: Session) -> None:
        """Emit ``session/created`` exactly once for an entered session."""
        entry = self._live_entry_for(session)
        if entry.announced or entry.announcing:
            raise ValueError(f'session "{entry.id}" was already announced')
        entry.announced = True
        entry.announcing = True
        try:
            args: list[Any] = [entry.carrier, "session/created", session]
            callbacks = collect_session_callbacks(self._ctx, args)
            for callback in callbacks:
                target = _unwrap_cordis_callback(callback)
                try:
                    returned = target(session)
                except Exception as error:  # noqa: BLE001
                    try:
                        self._ctx.logger.warn(
                            f'session "{entry.id}": session/created listener threw: {error}'
                        )
                    except Exception:  # pragma: no cover
                        pass
                    continue
                if returned is not None and hasattr(returned, "__await__"):
                    try:
                        returned.close()  # type: ignore[union-attr]
                    except Exception:  # pragma: no cover
                        pass
        finally:
            entry.announcing = False
            if entry.detach_requested and not entry.appending:
                try:
                    entry.detach()
                except Exception:  # pragma: no cover
                    pass

    def _emit_disposed(self, entry: SessionEntry) -> None:
        args: list[Any] = [entry.carrier, "session/disposed", entry.session]
        callbacks = collect_session_callbacks(self._ctx, args)
        invoke_contained_session_observers(
            self._ctx, "session/disposed", entry.id, [entry.session], callbacks
        )

    async def flush(self, session: Session) -> bool:
        """Dispatch the awaited ``session/flush`` durability checkpoint."""
        entry = self._live_entry_for(session)
        args: list[Any] = [entry.carrier, "session/flush", session]
        callbacks = collect_session_callbacks(self._ctx, args)
        if not callbacks:
            return False
        results: list[Any] = []
        for callback in callbacks:
            target = _unwrap_cordis_callback(callback)
            try:
                result = target(session)
            except Exception as error:
                results.append(_FutureError(error))
                continue
            results.append(result)
        # Await each (sync result passes through).
        awaited: list[Any] = []
        for r in results:
            if hasattr(r, "__await__"):
                try:
                    awaited.append(await r)
                except Exception as error:
                    raise error
            else:
                awaited.append(r)
        return True

    def _live_entry_for(self, session: Session) -> SessionEntry:
        entry = ATTACHMENTS.get(session)
        if entry is None or self._store.get(entry.id) is not entry:
            raise ValueError(f'session "{session.id}" is not live in this store')
        return entry

    def get(self, id: SessionId) -> Session | None:
        """Look up a live session by id."""
        entry = self._store.get(id)
        return entry.session if entry is not None else None

    def list(self) -> list[Session]:
        """All live sessions, in creation order."""
        return [entry.session for entry in self._store.values()]

    # ------------------------------------------------------------------
    # Fork
    # ------------------------------------------------------------------

    def fork(
        self,
        source: SessionForkSource,
        boundary: int | None = None,
        child_session_id: SessionId | None = None,
    ) -> Session:
        """Create a live child session from a stable prefix of a live source."""
        if child_session_id is not None and self.get(child_session_id) is not None:
            raise SessionForkError(
                f'session "{child_session_id}" already exists', "SESSION_ALREADY_EXISTS"
            )
        live_source = self._resolve_fork_source(source)
        seed = self._fork_seed(live_source, boundary)
        return self.create(
            child_session_id,
            {
                "seed": seed,
                "meta": {
                    **({"cwd": live_source.header["cwd"]} if live_source.header.get("cwd") else {}),
                    "parentSession": live_source.id,
                    "seedLength": len(seed),
                },
            },
        )

    def _fork_seed(self, session: Session, requested_boundary: int | None) -> list[SessionEvent]:
        events = list(session.events)
        last_event = events[-1] if events else None
        if requested_boundary is None:
            if last_event is None:
                return []
            boundary = last_event.get("seq")  # type: ignore[assignment]
        else:
            boundary = requested_boundary
        if not _is_safe_int(boundary):
            raise SessionForkError(
                f'fork boundary for session "{session.id}" must be a non-negative safe integer, got {boundary!r}',
                "INVALID_BOUNDARY",
            )
        if boundary >= len(events):
            last_seq = last_event.get("seq") if last_event else None
            raise SessionForkError(
                f'fork boundary {boundary} does not exist in session "{session.id}" (last seq: {last_seq})',
                "INVALID_BOUNDARY",
            )
        boundary_event = events[boundary]
        if boundary_event is None or boundary_event.get("seq") != boundary:
            raise SessionForkError(
                f'fork boundary {boundary} does not match a contiguous event seq in session "{session.id}"',
                "INVALID_BOUNDARY",
            )
        # Last turn-start or turn-end at-or-before boundary must be turn/end, not turn/start.
        last_turn_boundary: SessionEvent | None = None
        for event in reversed(events[: boundary + 1]):
            if event.get("type") in ("turn/start", "turn/end"):
                last_turn_boundary = event
                break
        if last_turn_boundary is not None and last_turn_boundary.get("type") == "turn/start":
            raise SessionForkError(
                f'fork boundary {boundary} in session "{session.id}" ends inside open turn {last_turn_boundary.get("data", {}).get("turn")}',
                "OPEN_TURN",
            )
        return list(events[: boundary + 1])

    def _resolve_fork_source(self, source: SessionForkSource) -> Session:
        if isinstance(source, str):
            session = self.get(make_session_id(source))
            if session is None:
                raise SessionForkError(f'session "{source}" not found', "SESSION_NOT_FOUND")
            return session
        live = self.get(source.id)
        if live is None:
            raise SessionForkError(f'session "{source.id}" not found', "SESSION_NOT_FOUND")
        if live is not source:
            raise SessionForkError(
                f'session "{source.id}" is not the live store instance', "SESSION_NOT_LIVE"
            )
        return source


class _FutureError:
    """Placeholder error wrapper used by `SessionStore.flush`'s settle logic."""

    __slots__ = ("error",)

    def __init__(self, error: BaseException) -> None:
        self.error = error

    def __await__(self) -> Iterator[Any]:
        raise self.error
        yield  # pragma: no cover — keeps this an async-returning function

    def __repr__(self) -> str:  # pragma: no cover
        return f"_FutureError({self.error!r})"
