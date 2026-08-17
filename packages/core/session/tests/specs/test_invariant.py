"""Tests for `taiyi_core_session.invariant` companion barrel."""

from __future__ import annotations

from taiyi_core_session.invariant import (
    KNOWN_SESSION_EVENT_TYPES,
    SESSION_FORMAT_VERSION,
    AgentCancelCause,
    Session,
    SessionEvent,
    SessionEventType,
    SessionForkError,
    SessionStore,
    SurfaceFoldResult,
    SurfaceIntent,
    SurfaceManager,
    SurfaceOp,
    TodoItem,
    TurnEndReason,
    adopt_session_event,
    canonical_header,
    deep_freeze,
    derive_event_message,
    fold_request_header,
    fold_surface,
    has_provider_model,
    header_equals,
    is_json_value,
    make_session_id,
    snapshot_json_value,
    validate_session_header,
)
from taiyi_core_session.session import (
    Session as _Impl_Session,
)
from taiyi_core_session.session import (
    SessionForkError as _Impl_SessionForkError,
)
from taiyi_core_session.session import (
    SessionStore as _Impl_SessionStore,
)
from taiyi_core_session.session import (
    SurfaceFoldResult as _Impl_SurfaceFoldResult,
)
from taiyi_core_session.session import (
    SurfaceManager as _Impl_SurfaceManager,
)
from taiyi_core_session.session import (
    adopt_session_event as _impl_adopt,
)
from taiyi_core_session.session import (
    canonical_header as _impl_canonical,
)
from taiyi_core_session.session import (
    deep_freeze as _impl_freeze,
)
from taiyi_core_session.session import (
    derive_event_message as _impl_derive,
)
from taiyi_core_session.session import (
    fold_request_header as _impl_fold_req,
)
from taiyi_core_session.session import (
    fold_surface as _impl_fold_surface,
)
from taiyi_core_session.session import (
    has_provider_model as _impl_has_pm,
)
from taiyi_core_session.session import (
    header_equals as _impl_header_equals,
)
from taiyi_core_session.session import (
    snapshot_json_value as _impl_snapshot,
)
from taiyi_core_session.session import (
    validate_session_header as _impl_validate_header,
)
from taiyi_core_session.types import (
    KNOWN_SESSION_EVENT_TYPES as _impl_known,  # noqa: N811
)
from taiyi_core_session.types import (
    SessionEvent as _impl_session_event,  # noqa: N813
)
from taiyi_core_session.types import (
    SessionEventType as _impl_session_event_type,  # noqa: N813
)
from taiyi_core_session.types import (
    TodoItem as _impl_todo,  # noqa: N813
)
from taiyi_core_session.types import (
    is_json_value as _impl_is_json,
)
from taiyi_core_session.types import (
    make_session_id as _impl_make_session_id,
)


def test_invariant_re_exports_match_implementation() -> None:
    """The companion barrel re-exports the same object identities."""
    assert Session is _Impl_Session
    assert SessionStore is _Impl_SessionStore
    assert SessionForkError is _Impl_SessionForkError
    assert SurfaceManager is _Impl_SurfaceManager
    assert SurfaceFoldResult is _Impl_SurfaceFoldResult
    assert adopt_session_event is _impl_adopt
    assert canonical_header is _impl_canonical
    assert deep_freeze is _impl_freeze
    assert derive_event_message is _impl_derive
    assert fold_request_header is _impl_fold_req
    assert fold_surface is _impl_fold_surface
    assert has_provider_model is _impl_has_pm
    assert header_equals is _impl_header_equals
    assert is_json_value is _impl_is_json
    assert snapshot_json_value is _impl_snapshot
    assert validate_session_header is _impl_validate_header
    assert KNOWN_SESSION_EVENT_TYPES is _impl_known
    assert SessionEvent is _impl_session_event
    assert SessionEventType is _impl_session_event_type
    assert TodoItem is _impl_todo
    assert make_session_id is _impl_make_session_id


def test_invariant_round_trip_through_session() -> None:
    """`Session.create` + `append` + `derive_messages` end-to-end through the barrel."""
    s = Session.create(make_session_id("s"))
    s.append(
        "user/message",
        {"id": "1", "role": "user", "source": {"kind": "user"}, "content": [{"type": "text", "text": "hi"}]},
        surface_intent={"surfaceOp": "append"},
    )
    msgs = s.derive_messages()
    assert len(msgs) == 1


def test_invariant_exposes_format_version_and_agent_cancel_cause() -> None:
    """`SESSION_FORMAT_VERSION` and `AgentCancelCause` are reachable via the barrel."""
    assert SESSION_FORMAT_VERSION == 0
    cause: AgentCancelCause = {"kind": "user"}
    assert cause["kind"] == "user"
    # Also that TurnEndReason / SurfaceOp / SurfaceIntent are reachable.
    _ = TurnEndReason
    _ = SurfaceOp
    _ = SurfaceIntent
    _ = SessionEvent
