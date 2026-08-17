"""`taiyi_core_session.plugin` — cordis plugin entry.

1:1 port of `@deepseek-ai/dsh-session`'s default export. Installs the
:class:`SessionStore` under ``ctx.sessions`` and declares the four
session lifecycle events on the cordis ``Events`` interface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cordis import Context, plugin

from taiyi_core_session.session import Session, SessionStore
from taiyi_core_session.types import SessionId

__all__ = ["setup"]


@plugin(name="session", inject=[])
async def setup(ctx: Context, config: Any = None) -> Callable[[], None]:
    """Install the session store under ``ctx.sessions`` and return a disposer."""
    store = SessionStore(ctx)
    dispose = ctx.reflect.provide("sessions", store)  # type: ignore[attr-defined]
    return dispose


# NOTE: the upstream `declare module '@deepseek-ai/cordis'` block (which
# augments the cordis Context/Events types with `sessions`,
# `session/created`, `session/disposed`, `session/event`, `session/flush`,
# and the typert lookup map) has no Python equivalent. Callers use the
# concrete `ctx.sessions` attribute at runtime and the events are dispatched
# through the cordis event bus as strings (`ctx.events.dispatch("emit",
# [..., "session/created", session])`).

__session_event_names__: tuple[str, ...] = (
    "session/created",
    "session/disposed",
    "session/event",
    "session/flush",
)


__session_lookup__: dict[str, Any] = {
    "session": {
        "parameter": "session",
        "wire": "sessionId",
        "host_type": Session,
        "wire_type": SessionId,
    }
}
