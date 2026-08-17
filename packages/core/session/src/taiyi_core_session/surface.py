"""`taiyi_core_session.surface` — surface placement marker types.

1:1 Python port of the surface-type portion of
`~/deepseek-harness/packages/core/session/src/types.ts` (lines covering
``SurfaceOp`` / ``SurfaceEventType`` / ``SurfaceIntent``).

The runtime surface manager (incremental view, fold, validation,
``derive_event_message``, type guards) lives in :mod:`taiyi_core_session.session`
per the Phase 0 plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypedDict

__all__ = [
    "SurfaceOp",
    "SurfaceEventType",
    "SurfaceIntent",
    "ReplaceOpDict",
    "make_replace_op",
    "is_surface_op_append",
    "is_surface_op_replace",
    "is_surface_eligible_type",
]


class _ReplaceOpDict(TypedDict):
    op: Literal["replace"]
    start: int
    end: int


# How a session event entered the ordered surface.
# - ``'append'``: added to the tail — normal path for user / assistant / tool messages.
# - ``{ op: 'replace', start, end }``: replaces surface nodes [start, end] inclusive.
SurfaceOp = Literal["append"] | _ReplaceOpDict


# The subset of SessionEventType values whose events produce LLM messages and
# are eligible to appear on the ordered surface.
SurfaceEventType = Literal["user/message", "assistant/message", "tool/result"]


class SurfaceIntent(TypedDict, total=False):
    """Surface placement and cited source-event seqs for ``Session.append``.

    Required on message-producing events and forbidden on log-only events.
    """

    surfaceOp: SurfaceOp
    # Complete set of known source-event seqs. `assistant/message` may use a
    # present empty array for a known empty provider stream; absent means the
    # event does not record which earlier events produced it.
    sourceEventSeqs: list[int]


# Helper for callers that want to construct a replace op without quoting literals.
def make_replace_op(start: int, end: int) -> _ReplaceOpDict:
    """Build a positional-replacement surface op."""
    return {"op": "replace", "start": start, "end": end}


# Re-export the underlying TypedDict for typing callers that import it explicitly.
ReplaceOpDict = _ReplaceOpDict


def is_surface_op_append(op: Any) -> bool:
    """Return True iff ``op`` is the ``'append'`` surface op."""
    return op == "append"


def is_surface_op_replace(op: Any) -> bool:
    """Return True iff ``op`` is a positional-replacement surface op dict."""
    return isinstance(op, Mapping) and op.get("op") == "replace"


def is_surface_eligible_type(event_type: str) -> bool:
    """Return True iff the event type can join the model-visible surface."""
    return event_type in {"user/message", "assistant/message", "tool/result"}
