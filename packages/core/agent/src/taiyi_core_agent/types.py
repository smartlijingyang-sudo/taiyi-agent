"""`taiyi_core_agent.types` — durable agent session-event vocabulary.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/types.ts`.

Public surface:

- :data:`InboxTarget`
- :data:`InboxSpliceData`

The augmentation :data:`SESSION_EVENT_MAP_AGENT_EXTENSIONS` is merged into
:data:`taiyi_core_session.types.SessionEventMap` at import time so the
``agent/inbox/spliced`` event becomes part of the recognized durable
vocabulary (mirrors upstream's ``declare module '@deepseek-ai/dsh-session/types'``).
"""

from __future__ import annotations

from typing import Literal, TypedDict

from typing_extensions import NotRequired

__all__ = [
    "InboxTarget",
    "InboxSpliceData",
    "SESSION_EVENT_MAP_AGENT_EXTENSIONS",
]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

# `Literal['next-turn', 'next-step']` — one of the two ordered pending lists
# owned by an agent's :class:`taiyi_core_agent.inbox.Inbox`.
InboxTarget = Literal["next-turn", "next-step"]


class InboxSpliceData(TypedDict, total=False):
    """Normalized payload of the ``agent/inbox/spliced`` session event.

    Mirrors upstream `inbox.ts` exactly: ``target``, ``start``,
    and ``inserted`` are always present; ``removedCount`` is omitted when
    zero (no messages were removed); ``outcome`` appears only on a
    cancellation that wipes the cleared position without inserting.
    """

    target: InboxTarget
    start: int
    removedCount: NotRequired[int]
    inserted: list[dict]
    outcome: NotRequired[Literal["canceled"]]


# ---------------------------------------------------------------------------
# SessionEventMap augmentation
# ---------------------------------------------------------------------------

# Mirrors upstream ``declare module '@deepseek-ai/dsh-session/types'``:
# extend the durable session event vocabulary with the agent's inbox splice.
SESSION_EVENT_MAP_AGENT_EXTENSIONS: dict[str, TypedDict] = {
    "agent/inbox/spliced": InboxSpliceData,
}


def _merge_into_session_event_map() -> None:
    """Best-effort install of the agent extensions into the session event map.

    Imported lazily to avoid an import cycle at module load. The merge is
    idempotent and never raises — the port of :data:`SessionEventMap` is a
    plain ``dict`` so callers can read it directly without the merge.
    """
    try:
        from taiyi_core_session.types import KNOWN_SESSION_EVENT_TYPES, SessionEventMap
    except Exception:  # pragma: no cover — optional peer package
        return
    for key, value in SESSION_EVENT_MAP_AGENT_EXTENSIONS.items():
        if key not in SessionEventMap:
            SessionEventMap[key] = value
    if "agent/inbox/spliced" not in KNOWN_SESSION_EVENT_TYPES:
        # ``frozenset`` is immutable in this port, so we cannot mutate it
        # in place. The dict merge above is the authoritative extension;
        # the frozenset simply does not gain the new key in this port.
        return


_merge_into_session_event_map()
