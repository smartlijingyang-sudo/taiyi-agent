"""taiyi-core-session — event-sourced session log + in-memory store + derived LLM message history.

1:1 Python port of `@deepseek-ai/dsh-session`. Append-only event log;
persistence is a plugin concern (subscribe to ``session/event``, drain on
``session/flush``).

Public surface:

- :class:`Session`, :class:`SessionStore`, :class:`SessionForkError`
- :data:`SessionId`, :data:`SessionHeader`, :data:`SESSION_FORMAT_VERSION`
- :data:`SessionEvent`, :data:`SessionEventType`, :data:`SessionEventMap`,
  :data:`KNOWN_SESSION_EVENT_TYPES`
- :data:`SurfaceOp`, :data:`SurfaceIntent`, :data:`SurfaceEventType`
- :data:`TurnEndReason`, :data:`AgentCancelCause`
- :data:`TodoItem`, :data:`EpochHeader`, :data:`RequestContext`,
  :data:`RequestHeaderReason`
- :mod:`taiyi_core_session.plugin` — cordis plugin entry
"""

from __future__ import annotations

from taiyi_core_session.events import (  # noqa: F401
    KNOWN_SESSION_EVENT_TYPES as _KNOWN_REEXPORT,  # already exported above
)
from taiyi_core_session.session import (  # noqa: F401 — full surface re-export
    ATTACHMENTS,
    Session,
    SessionEntry,
    SessionForkError,
    SessionForkErrorCode,
    SessionForkSource,
    SessionStore,
    SessionSurface,
    SurfaceFoldReplacement,
    SurfaceFoldResult,
    SurfaceManager,
    adopt_session_event,
    assert_adapter_defaults,
    assert_current_llm_shape,
    assert_message_event_shape,
    assert_session_event_envelope,
    assert_supported_request_header,
    canonical_header,
    collect_session_callbacks,
    deep_freeze,
    derive_event_message,
    fold_request_header,
    fold_surface,
    freeze_restored_object,
    has_provider_model,
    header_equals,
    is_append_surface_event,
    is_replacement_surface_event,
    is_surface_event,
    snapshot_json_value,
    snapshot_session_event,
    snapshot_session_header,
    validate_restored_session_header,
    validate_session_header,
)
from taiyi_core_session.surface import (
    ReplaceOpDict,
    SurfaceEventType,
    SurfaceIntent,
    SurfaceOp,
    is_surface_eligible_type,
    is_surface_op_append,
    is_surface_op_replace,
    make_replace_op,
)
from taiyi_core_session.turn import (
    SESSION_FORMAT_VERSION,
    AgentCancelCause,
    TurnEndAborted,
    TurnEndBlocked,
    TurnEndCancelCause,
    TurnEndCompleted,
    TurnEndError,
    TurnEndInterrupted,
    TurnEndMaxTokens,
    TurnEndReason,
)
from taiyi_core_session.types import (
    KNOWN_SESSION_EVENT_TYPES,
    CreateSessionMeta,
    CreateSessionOptions,
    EpochHeader,
    JsonValue,
    PrepareSessionOptions,
    RequestContext,
    RequestHeaderReason,
    RestoredSessionOptions,
    SessionEvent,
    SessionEventMap,
    SessionEventType,
    SessionHeader,
    SessionId,
    TodoItem,
    is_json_value,
    make_session_id,
)

__version__ = "0.1.0"

__all__ = [
    # JSON domain
    "JsonValue",
    "is_json_value",
    # Identity
    "SessionId",
    "make_session_id",
    # Format version
    "SESSION_FORMAT_VERSION",
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
    # Events
    "SessionEventMap",
    "SessionEventType",
    "KNOWN_SESSION_EVENT_TYPES",
    "SessionEvent",
    # Surface types
    "SurfaceOp",
    "SurfaceEventType",
    "SurfaceIntent",
    "ReplaceOpDict",
    "is_surface_eligible_type",
    "is_surface_op_append",
    "is_surface_op_replace",
    "make_replace_op",
    # Turn / cancel
    "AgentCancelCause",
    "TurnEndCancelCause",
    "TurnEndCompleted",
    "TurnEndAborted",
    "TurnEndBlocked",
    "TurnEndError",
    "TurnEndMaxTokens",
    "TurnEndInterrupted",
    "TurnEndReason",
    # JSON / event validation / freeze
    "snapshot_json_value",
    "deep_freeze",
    "freeze_restored_object",
    "adopt_session_event",
    "snapshot_session_event",
    "validate_session_header",
    "validate_restored_session_header",
    "snapshot_session_header",
    "assert_session_event_envelope",
    "assert_current_llm_shape",
    "assert_message_event_shape",
    "assert_adapter_defaults",
    "assert_supported_request_header",
    "has_provider_model",
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
    # Store
    "ATTACHMENTS",
    "SessionEntry",
    "SessionForkSource",
    "SessionForkErrorCode",
    "SessionForkError",
    "SessionStore",
    "Session",
    # Meta
    "__version__",
]
