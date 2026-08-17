# cordis

`taiyi-cordis` is a 1:1 Python port of [`@deepseek-ai/cordis`](https://github.com/deepseek-ai/cordis),
the dependency-injection / plugin framework that powers `taiyi-agent`.
This package defines the **runtime contract** for every other plugin in the
project: `Context`, `Fiber`, `Service`, `Event`, `Effect`, `Loader`, and the
`@plugin` decorator.

## Architecture decisions

The upstream TypeScript implementation leans on language features that do not
exist in Python. The 10 decisions below describe how each one is mapped:

1. **`Symbol.for(x)` → string keys.** Cordis uses `Symbol.for('cordis.x')` to
   create cross-realm keys. Python strings are hashable and are the natural
   replacement. Symbol-keyed slots become plain string attributes (`__disposer__`,
   `__dispose__`, `_cordis_*`).

2. **`Symbol.dispose` → `Disposer` protocol + `__dispose__`.** The TS contract
   `Symbol.dispose` becomes a `Disposer` `Protocol` (`async def dispose(self): ...`).
   Objects with a `__dispose__` coroutine are auto-detected by the effect
   runner and registered as disposers.

3. **WeakRef → `weakref.ref`.** Disposable lists keep strong refs for active
   cleanups, and rely on the Python GC for everything else; the
   TS `WeakMap<T, sn>` is replaced by direct `weakref.ref` storage where a
   reverse lookup is required (rare — most mappings use a plain list).

4. **`AbortController` → `asyncio.Event` + a flag.** Abort signals in
   upstream become a single flag plus a waitable `asyncio.Event`. Cancellation
   is one-shot: abort then discard.

5. **`EventEmitter` → custom listener list.** The TS event bus becomes a small
   `Event` class plus a `_hooks: dict[str, list[Hook]]` store. Listeners can be
   sync or async callables; the framework awaits the coroutine automatically.

6. **`Disposable` / `Mixin.dispose` → Python protocols.** Symbol-keyed methods
   become plain Python methods. Cross-fiber interception uses
   `Context.extend(meta)` (a Python `__init__`-style shadow).

7. **`Promise<T>` → `Awaitable[T]` / `AsyncIterator[T]`.** Every method that
   upstream returned a `Promise<...>` returns an `Awaitable[...]` (typically
   `Coroutine[Any, Any, T]`). Stream shapes use `AsyncIterator[T]`.

8. **`TaskGroup` → `asyncio.TaskGroup`** (Python 3.11+). Parallel event
   dispatch uses `async with asyncio.TaskGroup() as tg: ...` to mirror TS
   structured concurrency.

9. **`AsyncLocalStorage` → `contextvars.ContextVar`.** Per-context scope and
   "nearest" semantics use `contextvars.copy_context()` and explicit
   `ContextVar` reads inside `inject()`.

10. **`tsconfig.strict` → pyright strict + `dataclass(frozen=True)`.** Public
    APIs are typed; data containers prefer `frozen=True` dataclasses.
    Runtime invariants (`assert isinstance(ctx, Context)`) are explicit.

## Public surface (summary)

- `Context` / `Service` — DI + lifecycle; see `Context.provide/inject/isolate/fork/scope`.
- `Fiber` — plugin runtime + 6-state machine (`PENDING` / `LOADING` /
  `ACTIVE` / `FAILED` / `UNLOADING` / `DISPOSED`).
- `Event` — 5 dispatch modes (`emit` / `parallel` / `serial` / `bail` / `waterfall`).
- `Effect` — composable reverse-order disposal (`Effect.of(...)`).
- `Loader` — dict/YAML → plugin tree; `mount()` and `dump_config()`.
- `@plugin` decorator — `async def setup(ctx, config): ...`.
- `Registry` / `ReflectService` / `Logger` — typed map, scope metadata, 5-level logger.

See `invariant/contract.md` for the full contract description.

## Tests

```sh
uv run pytest vendor/cordis/tests -q --cov=vendor/cordis --cov-fail-under=100
```

Per-file 100% coverage is enforced.
