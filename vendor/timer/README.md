# timer

`taiyi-timer` is a 1:1 Python port of [`@deepseek-ai/timer`](https://github.com/deepseek-ai/timer),
the `TimerService` helper that ships with `deepseek-harness`. It offers a
small set of cancellable timers (`setTimeout`, `setInterval`), a throttler
and debouncer, and a `timeout` race helper, all backed by `asyncio`.

## Architecture decisions

The upstream TypeScript implementation leans on:
- `setTimeout` / `setInterval` / `clearTimeout` / `clearInterval` from Node,
- `ctx.effect` registration for cleanup-on-dispose,
- `Promise.withResolvers` for the `timeout(delay)` overload.

The Python port maps these to:

1. **`setTimeout` / `setInterval` → `asyncio.create_task` + `asyncio.sleep`.**
   Each scheduled callback runs in a coroutine. The returned *cancel handle*
   is a small callable that calls `task.cancel()` on the underlying task.

2. **`throttle` / `debounce` closures → plain Python closures.** The upstream
   `_schedule` helper is replaced by a small `_track` helper that registers
   the scheduled task in the service's pending set so it cleans up on
   `ctx.dispose()`. The `wrapper.dispose` attribute is preserved.

3. **`timeout(promise, ms)` → `asyncio.wait_for` + custom `TimerError`.**
   The Python `asyncio.TimeoutError` clashes with the built-in `TimeoutError`,
   so we expose a dedicated `TimerError` class (subclass of `Exception`) and
   always raise that from `timeout`. The `asyncio.wait_for` call still uses
   `asyncio.TimeoutError` internally; we re-raise as `TimerError` so callers
   have a single, stable exception to catch.

4. **Time-unit basis is milliseconds.** Upstream uses `Date.now()` (ms) and
   `setTimeout(ms, ...)`. The Python port uses `time.monotonic() * 1000` for
   monotonic timestamps and `asyncio.sleep(ms / 1000)` for delays. The `Time`
   helper exposes the same canonical constants the upstream `1e3 / 60 / 60 /
   24` ladder uses.

5. **No `Promise.withResolvers` overload.** The upstream `timeout` /
   `interval` overloads that return a Promise or AsyncIterator are NOT
   ported. The Python port stays with the simpler `setTimeout(fn, ms, args)`
   / `setInterval(fn, ms)` / `timeout(promise, ms)` triad that the consumer
   code in `taiyi-agent` actually needs.

6. **No `ctx.mixin` / `ctx.effect` integration.** The upstream explicitly
   mixes `setTimeout` / `setInterval` / `timeout` / `interval` / `throttle` /
   `debounce` into the Cordis `Context` so callers can write
   `ctx.setTimeout(...)`. The Python port keeps the methods on `TimerService`
   only — consumers that want the mixed-in form can build that on top.
   Auto-dispose of pending timers is wired through `Service.__init__`
   (which already registers `ctx.effect(self.dispose)`).

## Public surface

- `TimerService` — `setTimeout` / `setInterval` / `throttle` / `debounce` /
  `timeout`.
- `TimerError` — raised when `timeout` fires.
- `Time` — `none` / `second` / `minute` / `hour` / `day` constants in ms.

See `invariant/contract.md` for the public contract (mirrors `__init__.py`).

## Tests

```sh
uv run pytest vendor/timer/tests -q --cov=vendor/timer --cov-fail-under=100
```

Per-file 100% coverage is enforced.
