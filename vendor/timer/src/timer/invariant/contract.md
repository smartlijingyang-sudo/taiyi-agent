# timer.invariant — Public contract

Stable API surface for `taiyi-timer`. Every name exported here is
considered part of the contract; downstream packages consume the API
through this module.

## Types

- `TimerService` — `setTimeout` / `setInterval` / `throttle` / `debounce`
  / `timeout` / `dispose`.
- `TimerError` — raised by `timeout` when the awaitable exceeds its budget.
- `CancelHandle` — a callable returned by `setTimeout` / `setInterval`
  that cancels the scheduled work.
- `Time` — millisecond-duration constants (`none`, `millisecond`,
  `second`, `minute`, `hour`, `day`).

## Behavioral contract

1. **All scheduled timers are auto-cancelled.** When the owning
   `cordis.Context` is disposed (via `await ctx.dispose()`), every pending
   `setTimeout` / `setInterval` task is cancelled. The `Service` base
   class wires this through `ctx.effect(self.dispose)`.

2. **Cancel handles are idempotent.** Calling a cancel handle after the
   task has already fired (or after it has been cancelled) is a no-op.

3. **`throttle` is leading-only.** The first call fires immediately;
   subsequent calls within the window are skipped. After the window
   expires, the next call fires immediately again.

4. **`debounce` collapses calls.** Each call cancels the previous pending
   timer and schedules a new one. The callback fires only after `ms` of
   silence.

5. **`timeout` raises `TimerError`, not `asyncio.TimeoutError`.** The
   `asyncio.TimeoutError` used internally by `asyncio.wait_for` is
   always re-raised as `TimerError` so callers catch a single,
   consistent exception type.

6. **Time-unit basis is milliseconds.** All `ms` arguments are
   interpreted in milliseconds. Use `Time.second` / `Time.minute` / etc.
   for human-readable durations.
