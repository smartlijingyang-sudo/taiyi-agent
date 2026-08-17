# `taiyi_core_session` — Public API Contract

This file describes the contract surface for `taiyi_core_session`.
Consumers should import from `taiyi_core_session.invariant` (this subpackage)
rather than the implementation modules.

## Surface

### Types (types.py)

| Symbol | Kind | Description |
|---|---|---|
| `JsonValue` | type alias | Losslessly JSON-serializable Python value |
| `is_json_value(value)` | function | Runtime test for `JsonValue` |
| `SessionId` | NewType | Opaque identity-compared session id |
| `make_session_id(raw)` | function | Brand a raw string as a `SessionId` |
| `SessionHeader` | TypedDict | Durable storage metadata (version, id, createdAt, cwd, lineage, ...) |
| `CreateSessionOptions`, `RestoredSessionOptions`, `PrepareSessionOptions` | TypedDict | Construction options for `SessionStore.prepare` |
| `CreateSessionMeta` | TypedDict | Caller-supplied storage fields (excluding stamped fields) |
| `TodoItem` | TypedDict | One entry of the `todo/write` event's whole-list snapshot |
| `EpochHeader` | TypedDict | Logged request state outside derived history |
| `RequestContext` | TypedDict | Route metadata for one resolved model route |
| `RequestHeaderReason` | Literal | `'initial' \| 'resume' \| 'change'` |
| `SessionEventMap` | dict | Map: event-type name → typed payload dict |
| `SessionEventType` | Literal | Union of all 44 event-type name strings |
| `KNOWN_SESSION_EVENT_TYPES` | frozenset | The 44 known event types — drives persistence validation |
| `SessionEvent` | Mapping[str, Any] | Runtime dict carrying the envelope |

### Turn end (turn.py)

| Symbol | Description |
|---|---|
| `SESSION_FORMAT_VERSION` | Pinned at `0`; bump only on breaking structural change |
| `AgentCancelCause` | Why an active agent driver was cancelled |
| `TurnEndCancelCause` | Durable cancellation cause (incl. `legacy`) |
| `TurnEndReason` | Union of completion, abort, blocked, error, max-tokens, interrupted |
| `TurnEnd{Completed,Aborted,Blocked,Error,MaxTokens,Interrupted}` | TypedDict variants |

### Surface types (surface.py)

| Symbol | Description |
|---|---|
| `SurfaceOp` | `'append'` or `{op: 'replace', start, end}` |
| `SurfaceEventType` | `'user/message' \| 'assistant/message' \| 'tool/result'` |
| `SurfaceIntent` | `surfaceOp` + optional `sourceEventSeqs` for `Session.append` |
| `ReplaceOpDict` | TypedDict for the replace-op variant |
| `make_replace_op(start, end)` | Construct a replace-op dict |
| `is_surface_op_append(op)` | Predicate |
| `is_surface_op_replace(op)` | Predicate |
| `is_surface_eligible_type(t)` | Whether `t` can join the model-visible surface |

### Session class (session.py)

| Symbol | Description |
|---|---|
| `Session` | Append-only event log; plain class (not Service) |
| `Session.create(id, seed?, header?)` | Static constructor for detached session |
| `Session.from_restore(id, seed, header)` | Static constructor for restore path |
| `Session.append(type, data, surface_intent?)` | Append one typed event; publishes `session/event` |
| `Session.events` | Immutable snapshot of the append-only log |
| `Session.header` | The immutable validated storage metadata |
| `Session.seq` | Next event's seq (= log length; contiguity contract) |
| `Session.id` | Derived from header |
| `Session.first_live_seq` | First seq appended in this process (= seed length) |
| `Session.request_header()` | Fold of `request/header` events |
| `Session.request_context()` | Fold of `request/context` events |
| `Session.derive_messages()` | LLM message history from the ordered surface |
| `Session.surface` | The live ordered surface (`SessionSurface`) |

### Helpers (session.py)

| Symbol | Description |
|---|---|
| `snapshot_json_value(v)` | JSON-roundtrip validation + detach |
| `deep_freeze(value)` | Recursive deep freeze |
| `freeze_restored_object(value)` | Iterative deep freeze (no call-stack consumption) |
| `adopt_session_event(event)` | Validate + deep-freeze exclusively-owned event |
| `snapshot_session_event(event)` | Detach + adopt |
| `validate_session_header(id, input)` | Validate + freeze one creation header |
| `validate_restored_session_header(id, input)` | Validate + freeze one persistence header |
| `snapshot_session_header(id, source?)` | Detach + validate + freeze |
| `assert_session_event_envelope(value, index)` | Validate fixed event envelope |
| `assert_current_llm_shape(event, index)` | Reject legacy request/header + malformed messages |
| `assert_message_event_shape(event, subject)` | Validate message envelope (user/assistant/tool) |
| `assert_adapter_defaults(value, config, index)` | Validate adapter-default markers |
| `assert_supported_request_header(type, data, location)` | Reject `request/header-delta` + `fallback` reason |
| `has_provider_model(value)` | Predicate for provider+model string pair |
| `is_surface_event`, `is_append_surface_event`, `is_replacement_surface_event` | Surface type guards |
| `derive_event_message(event)` | Per-node projection rule |
| `SurfaceManager` | Incremental live surface view + append validator |
| `fold_surface(events)` | Pure offline reconstruction |
| `SurfaceFoldResult`, `SurfaceFoldReplacement` | Fold result types |
| `canonical_header(h)` | Normalize header to canonical form |
| `header_equals(a, b)` | Field-wise equality over canonical headers |
| `fold_request_header(events, from?)` | Fold header events into latest canonical header |
| `collect_session_callbacks(ctx, args)` | Dispatch helper |

### Store (session.py)

| Symbol | Description |
|---|---|
| `SessionStore` | In-memory store; subscribers on `session/event` for persistence |
| `SessionStore.create(id?, options?)` | One-shot `prepare → enter → announce` |
| `SessionStore.prepare(id?, options?)` | Build WITHOUT entering |
| `SessionStore.enter(session)` | Install publish hooks; returns detach disposer |
| `SessionStore.announce(session)` | Emit `session/created` exactly once |
| `SessionStore.flush(session)` | Awaited parallel durability checkpoint |
| `SessionStore.get(id)` | Live session by id |
| `SessionStore.list()` | All live sessions, in creation order |
| `SessionStore.fork(source, boundary?, child_id?)` | Fork a live child session |
| `SessionForkError` | Typed error with `code` |
| `SessionForkErrorCode` | Literal of 5 codes |
| `SessionForkSource` | `Session \| SessionId` |
| `SessionEntry` | Mutable per-session lifecycle state |
| `ATTACHMENTS` | `Session → SessionEntry` WeakKeyDictionary |

## Behavior

1. **Append-only.** `Session.append` is the only mutation path; `events` is a
   frozen snapshot.
2. **Format-version pinned at 0.** Persistence backends reject any other
   version on load.
3. **Identity-compared keys.** Session keys are opaque objects; `SessionId`
   is a runtime string.
4. **Cycle / scope checks.** Surface folds reject cycles, non-contiguous
   seqs, open-turn forks, and surface replacements that don't include every
   shadowed node in `sourceEventSeqs`.
5. **Listeners contained.** `session/created`, `session/disposed`,
   `session/event` callbacks' errors are logged and contained; they do
   not change the return value or prevent later observers from running.
6. **Detach semantics.** `enter`'s detach disposer waits for synchronous
   `announcing` / `appending` to unwind before removing the entry —
   matches upstream's rollback-on-throw contract.
7. **JSON-safe log.** Every event's `data` and surface metadata must be
   losslessly JSON-serializable; non-serializable payloads fail at the
   `append` site, not at backend flush.