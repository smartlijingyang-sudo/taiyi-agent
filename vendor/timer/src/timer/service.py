"""`timer.service` — TimerService (setTimeout / setInterval / throttle / debounce / timeout).

1:1 with `~/deepseek-harness/vendor/timer/src/index.ts` (147 LOC).

Mapping notes
-------------
- `setTimeout(callback, delay)` (TS) → `setTimeout(fn, ms, *args)` (Python).
  Returns a cancel handle (callable that calls `task.cancel()`).
- `setInterval(callback, delay)` (TS) → `setInterval(fn, ms)` (Python).
  Returns a cancel handle.
- `throttle(callback, delay)` (TS) → `throttle(fn, ms)` (Python).
  Leading-only (first call immediate, subsequent calls within the window
  skipped). Matches the simpler test contract documented in the task spec.
- `debounce(callback, delay)` (TS) → `debounce(fn, ms)` (Python).
  Each call resets the pending timer.
- `timeout(delay)` / `timeout(callback, delay)` (TS) → `timeout(promise, ms)`
  (Python). Awaits the awaitable, raising `TimerError` after `ms` ms.

The upstream `interval(delay)` async-iterator overload and
`timeout(delay)` Promise overload are intentionally NOT ported — the
Python downsizing keeps the simpler `setTimeout` / `setInterval` /
`timeout(promise, ms)` triad that `taiyi-agent` consumers actually use.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from cordis import Context, Service

_F = TypeVar("_F", bound=Callable[..., Any])

# Type aliases ----------------------------------------------------------------

CancelHandle = Callable[[], None]
"""A returned callable that cancels the scheduled work."""

if TYPE_CHECKING:
    from typing import Protocol

    class WrapperWithDispose(Protocol):
        """Callable wrapper that exposes a `.dispose()` method.

        Returned by `throttle` and `debounce` so callers can cancel any
        pending trailing work without having to keep the wrapper reference.
        """

        def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
        def dispose(self) -> None: ...
else:
    WrapperWithDispose = Callable[..., Any]


# Exceptions ------------------------------------------------------------------


class TimerError(Exception):
    """Raised by `TimerService.timeout` when an awaitable exceeds its budget.

    A dedicated class (rather than the built-in `TimeoutError` or
    `asyncio.TimeoutError`) gives callers a single, stable exception to
    catch across the `taiyi-agent` codebase.
    """


# Service ---------------------------------------------------------------------


class TimerService(Service):
    """Timer helper service mixing `setTimeout`, `setInterval`, `throttle`,
    `debounce`, and `timeout` into the agent's tooling surface.

    All scheduled timers are tracked in `_pending` and cancelled when the
    owning context is disposed, mirroring the upstream `ctx.effect(...)`
    cleanup that the TS implementation registers through `Cordis`.
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._pending: set[asyncio.Task[Any]] = set()

    # -- internal helpers ----------------------------------------------------

    def _track(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Register a task so it is cancelled on `Service.dispose`."""
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    @staticmethod
    def _cancel(task: asyncio.Task[Any]) -> None:
        """Cancel a task, tolerating a closed/different event loop."""
        if task.done():
            return
        try:
            task.cancel()
        except RuntimeError:
            # Task belongs to a different (now-closed) loop. Drop it.
            pass

    # -- public API ----------------------------------------------------------

    def setTimeout(self, fn: Callable[..., Any], ms: int, *args: Any) -> CancelHandle:  # noqa: N802 — 1:1 port of upstream `setTimeout`.
        """Schedule `fn(*args)` to run once after `ms` milliseconds.

        Returns a cancel handle that prevents the callback from firing
        if invoked before the delay elapses.
        """

        async def runner() -> None:
            try:
                await asyncio.sleep(ms / 1000)
                fn(*args)
            except asyncio.CancelledError:
                pass

        task = self._track(asyncio.create_task(runner()))

        def cancel() -> None:
            self._cancel(task)

        return cancel

    def setInterval(self, fn: Callable[..., Any], ms: int) -> CancelHandle:  # noqa: N802 — 1:1 port of upstream `setInterval`.
        """Schedule `fn()` to run every `ms` milliseconds until cancelled.

        Returns a cancel handle that stops further invocations.
        """

        async def runner() -> None:
            try:
                while True:
                    await asyncio.sleep(ms / 1000)
                    fn()
            except asyncio.CancelledError:
                pass

        task = self._track(asyncio.create_task(runner()))

        def cancel() -> None:
            self._cancel(task)

        return cancel

    def throttle(self, fn: Callable[..., Any], ms: int) -> WrapperWithDispose:
        """Wrap `fn` so the first call fires immediately and subsequent calls
        within the `ms` window are skipped.

        The wrapper exposes a `.dispose()` method (no-op, kept for API
        parity with `debounce`).
        """
        last_call = -float("inf")

        def wrapper(*args: Any) -> None:
            nonlocal last_call
            now = time.monotonic() * 1000
            if now - last_call >= ms:
                last_call = now
                fn(*args)

        def dispose() -> None:
            # No trailing trailing timer in the leading-only port.
            pass

        wrapper.dispose = dispose  # type: ignore[attr-defined]
        return cast("WrapperWithDispose", wrapper)

    def debounce(self, fn: Callable[..., Any], ms: int) -> WrapperWithDispose:
        """Wrap `fn` so calls collapse into a single fire after `ms` of silence.

        Each call cancels the previous pending timer and schedules a new one.
        """
        slot: list[asyncio.Task[Any] | None] = [None]

        def wrapper(*args: Any) -> None:
            previous = slot[0]
            if previous is not None and not previous.done():
                previous.cancel()

            async def runner() -> None:
                try:
                    await asyncio.sleep(ms / 1000)
                    fn(*args)
                except asyncio.CancelledError:
                    pass

            slot[0] = self._track(asyncio.create_task(runner()))

        def dispose() -> None:
            current = slot[0]
            if current is not None and not current.done():
                current.cancel()
            slot[0] = None

        wrapper.dispose = dispose  # type: ignore[attr-defined]
        return cast("WrapperWithDispose", wrapper)

    async def timeout(self, promise: Awaitable[Any], ms: int) -> Any:
        """Await `promise`; raise `TimerError` if it does not settle in `ms`."""
        try:
            return await asyncio.wait_for(promise, timeout=ms / 1000)
        except TimeoutError as exc:
            raise TimerError(f"timeout after {ms}ms") from exc

    # -- lifecycle -----------------------------------------------------------

    async def dispose(self) -> None:
        """Cancel every pending timer and wait for the cancellations to land."""
        pending = list(self._pending)
        self._pending.clear()
        for task in pending:
            self._cancel(task)
        # Drain cancelled tasks so they don't emit "Task was destroyed but
        # it is pending" warnings when the loop closes.
        for task in pending:
            try:
                await task
            except BaseException:  # noqa: BLE001 — both cancellation & runtime errors
                pass


__all__ = ["TimerService", "TimerError", "CancelHandle", "WrapperWithDispose"]
