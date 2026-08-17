# `taiyi-core-agent` — Agent service: live registry + factory delegation

1:1 Python port of `@deepseek-ai/dsh-agent`
(`~/deepseek-harness/packages/core/agent/`).

## Port-decisions

| Upstream concept | Python port | Notes |
| --- | --- | --- |
| `Context.inject(['typert'], cb)` | best-effort, skipped when `ctx.typert` missing | typert is not ported yet; equivalent runtime registration runs when present |
| `AsyncLocalStorage<Agent>` | `contextvars.ContextVar` | mirrors the two-layer storage with one var per role |
| `WeakMap<Agent, AgentStatus>` | `weakref.WeakKeyDictionary` | keyed by the Agent so agent lifetime stays caller-owned |
| `Promise<void>` | `asyncio.Future[None]` | `_dispose_initiators` memoizes the future |
| `ctx.serial(...)` for fused `Agent` events | same `ctx.serial(...)` | passes the carrier as `thisArg` (upstream) |
| `ctx.waterfall(...)` for fused `Agent` events | same `ctx.waterfall(...)` | passes the carrier as `thisArg` |
| `ctx.emit(...)` for fused `Agent` events | manual `events.dispatch('emit', ...)` + per-listener try/except | upstream comments note Cordis's `Array.map` starves later listeners on a synchronous throw |
| `cordis.Service.dispose` | inherited through `cordis.Service` subclass | identity exposed via `Service.dispose` |

## Upstream source mapping

| Upstream file | Python port |
| --- | --- |
| `index.ts` | `registry.py` + `runtime_types.py` + `factory.py` |
| `runtime-types.ts` | `runtime_types.py` |
| `types.ts` | `types.py` |
| `inbox.ts` | `inbox.py` |
| `consumed-work.ts` | `consumed_work.py` |
| `dispatch.ts` | `dispatch.py` (+ `carrier.py`, `event.py`, `context.py`) |
| `invariant.ts` | `invariant/__init__.py` + `invariant/contract.md` |
| `model-selection.ts` | `model_selection.py` |

## Public surface

See `src/taiyi_core_agent/__init__.py` for the full re-export list.

## Tests

```bash
uv run pytest packages/core/agent/ --cov=packages/core/agent --cov-fail-under=100
```
