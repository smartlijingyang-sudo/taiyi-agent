"""Tests for `timer.service` — TimerService (setTimeout / setInterval / throttle / debounce / timeout)."""

from __future__ import annotations

import asyncio

import pytest
from cordis import Context

from timer import TimerError, TimerService


class TestSetTimeout:
    """`setTimeout(fn, ms, *args)` schedules a one-shot callback."""

    async def test_set_timeout_fires_after_delay(self) -> None:
        """`setTimeout` invokes the callback after the requested delay."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        handle = svc.setTimeout(lambda: calls.append(1), 40)
        assert calls == []

        await asyncio.sleep(0.08)
        assert calls == [1]

        # Idempotent cancel after fire.
        handle()
        await ctx.dispose()

    async def test_set_timeout_cancel_before_fire(self) -> None:
        """Calling the cancel handle before the delay prevents the callback."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        handle = svc.setTimeout(lambda: calls.append(1), 60)
        handle()
        await asyncio.sleep(0.1)
        assert calls == []

        await ctx.dispose()

    async def test_set_timeout_passes_args(self) -> None:
        """`setTimeout` forwards positional args to the callback."""
        ctx = Context()
        svc = TimerService(ctx)
        captured: list[tuple[object, ...]] = []

        def fn(*args: object) -> None:
            captured.append(args)

        svc.setTimeout(fn, 30, 1, "two", 3.0)
        await asyncio.sleep(0.06)
        assert captured == [(1, "two", 3.0)]

        await ctx.dispose()

    async def test_set_timeout_cancel_handle_is_callable(self) -> None:
        """The cancel handle is a callable that can be invoked any time."""
        ctx = Context()
        svc = TimerService(ctx)

        handle = svc.setTimeout(lambda: None, 10)
        assert callable(handle)
        handle()  # Should not raise.

        await ctx.dispose()


class TestSetInterval:
    """`setInterval(fn, ms)` schedules a repeating callback."""

    async def test_set_interval_fires_repeatedly(self) -> None:
        """`setInterval` fires the callback more than once within ~3 windows."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        handle = svc.setInterval(lambda: calls.append(1), 25)
        await asyncio.sleep(0.09)
        assert len(calls) >= 2

        handle()
        await ctx.dispose()

    async def test_set_interval_cancel_stops_further(self) -> None:
        """Cancelling the interval stops further callbacks."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        handle = svc.setInterval(lambda: calls.append(1), 20)
        await asyncio.sleep(0.05)
        snapshot = len(calls)
        assert snapshot >= 1

        handle()
        await asyncio.sleep(0.05)
        assert len(calls) == snapshot

        await ctx.dispose()


class TestThrottle:
    """`throttle(fn, ms)` — first call immediate, then at most once per window."""

    async def test_throttle_first_call_immediate(self) -> None:
        """The first call fires synchronously."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.throttle(lambda: calls.append(1), 50)
        fn()
        assert calls == [1]

        await ctx.dispose()

    async def test_throttle_subsequent_call_within_window_skipped(self) -> None:
        """Calls within the window are skipped (no-op)."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.throttle(lambda: calls.append(1), 80)
        fn()
        fn()
        fn()
        assert calls == [1]

        await asyncio.sleep(0.05)
        assert calls == [1]
        await ctx.dispose()

    async def test_throttle_call_after_window_fires(self) -> None:
        """A call after the window expires fires again."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.throttle(lambda: calls.append(1), 30)
        fn()
        await asyncio.sleep(0.05)
        fn()
        assert calls == [1, 1]

        await ctx.dispose()

    async def test_throttle_wrapper_has_dispose(self) -> None:
        """The throttled wrapper exposes a `.dispose` method that is safe to call."""
        ctx = Context()
        svc = TimerService(ctx)

        fn = svc.throttle(lambda: None, 50)
        assert hasattr(fn, "dispose")
        assert callable(fn.dispose)
        fn.dispose()
        fn.dispose()  # idempotent

        await ctx.dispose()


class TestDebounce:
    """`debounce(fn, ms)` — collapse calls within the window."""

    async def test_debounce_collapses_within_window(self) -> None:
        """Multiple calls within the window collapse into a single fire."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.debounce(lambda: calls.append(1), 50)
        fn()
        fn()
        fn()
        await asyncio.sleep(0.08)

        assert calls == [1]
        await ctx.dispose()

    async def test_debounce_fires_after_window(self) -> None:
        """The callback fires after the window of silence."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.debounce(lambda: calls.append(1), 30)
        fn()
        await asyncio.sleep(0.06)
        assert calls == [1]

        await ctx.dispose()

    async def test_debounce_resets_timer_on_each_call(self) -> None:
        """A second call within the window defers the fire further."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.debounce(lambda: calls.append(1), 40)
        fn()
        await asyncio.sleep(0.02)
        fn()  # resets the timer
        await asyncio.sleep(0.02)
        assert calls == []  # not yet — the timer was reset

        await asyncio.sleep(0.05)
        assert calls == [1]

        await ctx.dispose()

    async def test_debounce_wrapper_has_dispose(self) -> None:
        """The debounced wrapper exposes a `.dispose` method that cancels pending timers."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.debounce(lambda: calls.append(1), 50)
        fn()
        fn.dispose()
        await asyncio.sleep(0.08)
        assert calls == []

        await ctx.dispose()


class TestTimeout:
    """`timeout(promise, ms)` — race an awaitable against a delay."""

    async def test_timeout_passes_when_faster(self) -> None:
        """Returns the awaitable's result when it completes within the window."""
        ctx = Context()
        svc = TimerService(ctx)

        async def task() -> str:
            await asyncio.sleep(0.01)
            return "done"

        result = await svc.timeout(task(), 200)
        assert result == "done"

        await ctx.dispose()

    async def test_timeout_raises_timeout_error_when_slower(self) -> None:
        """Raises `TimerError` when the awaitable exceeds the window."""
        ctx = Context()
        svc = TimerService(ctx)

        async def task() -> str:
            await asyncio.sleep(0.2)
            return "done"

        with pytest.raises(TimerError):
            await svc.timeout(task(), 30)

        await ctx.dispose()


class TestDispose:
    """`Service.dispose()` cancels every pending timer."""

    async def test_dispose_cancels_all_pending_timers(self) -> None:
        """Disposing the context cancels all `setTimeout` / `setInterval` tasks."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        def make_callback(value: int):
            def callback() -> None:
                calls.append(value)
            return callback

        for i in range(5):
            svc.setTimeout(make_callback(i), 50)

        # also schedule an interval
        handle = svc.setInterval(lambda: calls.append(99), 30)
        del handle  # never cancelled explicitly

        await ctx.dispose()

        # Give the cancelled tasks a chance to settle / fail.
        await asyncio.sleep(0.1)
        assert calls == []

    async def test_dispose_is_idempotent(self) -> None:
        """Calling `dispose` twice does not raise."""
        ctx = Context()
        svc = TimerService(ctx)

        svc.setTimeout(lambda: None, 50)
        await ctx.dispose()
        await ctx.dispose()


class TestTimerError:
    """`TimerError` is a custom exception used by `timeout`."""

    def test_timer_error_is_exception(self) -> None:
        """`TimerError` is a subclass of `Exception`."""
        assert issubclass(TimerError, Exception)

    def test_timer_error_carries_message(self) -> None:
        """`TimerError` carries a message string."""
        err = TimerError("boom")
        assert str(err) == "boom"
        assert isinstance(err, TimerError)


class TestCancelDuringSleep:
    """Cancelling in-flight coroutines swallows `CancelledError` cleanly."""

    async def test_set_timeout_cancel_before_sleep_completes(self) -> None:
        """Cancelling a `setTimeout` mid-sleep swallows the `CancelledError`."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        handle = svc.setTimeout(lambda: calls.append(1), 200)
        # Cancel before the timer fires — the runner's `except CancelledError`
        # should swallow the cancellation cleanly.
        await asyncio.sleep(0.01)
        handle()
        await asyncio.sleep(0.05)
        assert calls == []

        await ctx.dispose()

    async def test_set_interval_cancel_during_sleep(self) -> None:
        """Cancelling a `setInterval` mid-sleep swallows the `CancelledError`."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        handle = svc.setInterval(lambda: calls.append(1), 30)
        await asyncio.sleep(0.05)
        handle()
        await asyncio.sleep(0.05)
        # No further calls after cancellation.
        snapshot = len(calls)
        await asyncio.sleep(0.05)
        assert len(calls) == snapshot

        await ctx.dispose()

    async def test_set_timeout_dispose_during_sleep(self) -> None:
        """Disposing the context mid-sleep cancels every pending task."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        svc.setTimeout(lambda: calls.append(1), 200)
        await asyncio.sleep(0.01)
        await ctx.dispose()
        await asyncio.sleep(0.05)
        assert calls == []


class TestCancelClosedLoopTask:
    """`_cancel` tolerates tasks that belong to a different (now-closed) loop."""

    async def test_cancel_task_from_closed_loop(self) -> None:
        """Calling `_cancel` on a task whose loop is closed does not raise."""
        from unittest.mock import MagicMock

        # Simulate a Task whose loop is closed: `Task.cancel()` raises
        # `RuntimeError` in that case. The `_cancel` helper should swallow it.
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel.side_effect = RuntimeError("Event loop is closed")

        ctx = Context()
        svc = TimerService(ctx)
        # Should not raise. Accessing the private helper is intentional in
        # this test — the behavior is the contract we want to verify.
        svc._cancel(mock_task)  # pyright: ignore[reportPrivateUsage]
        await ctx.dispose()


class TestDebounceDisposeBranches:
    """`debounce(...).dispose()` covers both branches of the pending-task check."""

    async def test_debounce_dispose_with_no_pending_task(self) -> None:
        """`dispose()` is safe to call when no task is pending."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.debounce(lambda: calls.append(1), 50)
        # No call yet — there is no pending task; the `if not None` branch
        # of the dispose helper must still be safe.
        fn.dispose()
        await asyncio.sleep(0.08)
        assert calls == []

        await ctx.dispose()

    async def test_debounce_dispose_with_completed_task(self) -> None:
        """`dispose()` is safe to call after the pending task has completed."""
        ctx = Context()
        svc = TimerService(ctx)
        calls: list[int] = []

        fn = svc.debounce(lambda: calls.append(1), 20)
        fn()
        await asyncio.sleep(0.04)
        assert calls == [1]
        # The task is now done; the `not current.done()` branch should be
        # skipped without raising.
        fn.dispose()
        fn.dispose()

        await ctx.dispose()


class TestInvariantModule:
    """`timer.invariant` re-exports the public surface."""

    def test_invariant_module_exports(self) -> None:
        """Every public name is also exported from `timer.invariant`."""
        from timer import invariant

        for name in ("TimerService", "TimerError", "Time", "CancelHandle"):
            assert hasattr(invariant, name), f"missing invariant export: {name}"


__all__ = [
    "TestSetTimeout",
    "TestSetInterval",
    "TestThrottle",
    "TestDebounce",
    "TestTimeout",
    "TestDispose",
    "TestTimerError",
    "TestCancelDuringSleep",
    "TestCancelClosedLoopTask",
    "TestDebounceDisposeBranches",
    "TestInvariantModule",
]
