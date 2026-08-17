# taiyi-core-session

Event-sourced session log + in-memory store + derived LLM message history.

1:1 Python port of `@deepseek-ai/dsh-scope`-adjacent package `@deepseek-ai/dsh-session`.
Append-only event log; persistence is a plugin concern (subscribe to `session/event`,
drain on `session/flush`).

## Public surface

```python
from taiyi_core_session import (
    Session, SessionStore, SessionForkError,
    SessionId, SessionHeader, SESSION_FORMAT_VERSION,
    SessionEvent, SessionEventType, SessionEventMap,
    KNOWN_SESSION_EVENT_TYPES,
    SurfaceOp, SurfaceIntent, SurfaceEventType,
    TurnEndReason, AgentCancelCause,
    TodoItem, EpochHeader, RequestContext,
)
```

## Port decisions

| Upstream | Python |
|---|---|
| `Branded<'SessionId'>` (string brand) | `NewType('SessionId', str)` + `SessionId(id)` constructor |
| `SessionEventMap` interface (44 keys) | `TypedDict`-like `dict[str, Any]` with typed payload type aliases |
| Discriminated `SessionEvent<T>` union | runtime dict with `type`/`data` discrimination; structural typing |
| `deepFreeze` recursive | custom `_deep_freeze` helper using object identity stack |
| `structuredClone` | `copy.deepcopy` (lossless JSON-safe) |
| `snapshotJsonValue` | `json.dumps` round-trip validation + deep copy |
| `WeakMap<Session, SessionEntry>` | `WeakKeyDictionary` (Session is user-defined class, hashable by id) |
| `Number.isSafeInteger` | `isinstance(x, int) and abs(x) < 2**53` |
| `node:path.isAbsolute` | `os.path.isabs` |
| `cordis.events.dispatch('emit', ...)` | `ctx.events.dispatch('emit', ...)` (cordis already supports this) |

## Phase 0 scope

In-scope files (1:1 ports of upstream):
- `types.py` — SessionId, SessionHeader, SessionEventMap, SessionEvent, TodoItem,
  EpochHeader, RequestContext, SurfaceOp, SurfaceIntent, TurnEndReason,
  AgentCancelCause, KNOWN_SESSION_EVENT_TYPES
- `surface.py` — SurfaceManager, foldSurface, deriveEventMessage, type guards
- `session.py` — Session class
- `store.py` — SessionStore + SessionForkError
- `plugin.py` — cordis plugin entry

Out-of-scope for Phase 0 (deferred):
- Legacy `request/header-delta` codec migration
- `chunk-rows.ts` (storage row packing)
- `repair.ts` (crash-recovery closer markers)
- `preparation.ts` (multi-stage enter/prepare helper)
- `invariant.ts` companion (run-time relational checks)