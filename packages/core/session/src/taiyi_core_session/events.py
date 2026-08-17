"""`taiyi_core_session.events` — public session-event vocabulary.

1:1 Python port of the ``KNOWN_SESSION_EVENT_TYPES`` portion of
`~/deepseek-harness/packages/core/session/src/known-event-types.ts`. Re-exports
:data:`SessionEventType` and :data:`KNOWN_SESSION_EVENT_TYPES` from
:mod:`taiyi_core_session.types` so callers can mount the package and import
its event vocabulary from a stable, plan-defined module.
"""

from __future__ import annotations

from taiyi_core_session.types import (
    KNOWN_SESSION_EVENT_TYPES,
    SessionEventType,
)

__all__ = [
    "KNOWN_SESSION_EVENT_TYPES",
    "SessionEventType",
]


# Sanity: 44 distinct core event types.
assert len(KNOWN_SESSION_EVENT_TYPES) == 44, (
    f"SessionEventType vocabulary drift: expected 44 types, got {len(KNOWN_SESSION_EVENT_TYPES)}"
)
