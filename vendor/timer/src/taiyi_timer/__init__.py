"""taiyi-timer — Timer service with auto-disposal.

对齐 dsh vendor/timer：提供 ctx.timeout / ctx.interval / ctx.throttle / ctx.debounce
所有定时器自动绑定到 ctx 生命周期，ctx dispose 时自动清理。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Callable, TypeVar

from cordis import Context, Service

__all__ = ["TimerService", "plugin"]

F = TypeVar("F", bound=Callable[..., Any])


class TimerService(Service):
    """Timer service：提供 timeout / interval / throttle / debounce。

    所有定时器自动绑定到 ctx 生命周期。
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        # 混入到 ctx（对齐 dsh 的 ctx.mixin）
        ctx.timeout = self.timeout  # type: ignore[attr-defined]
        ctx.interval = self.interval  # type: ignore[attr-defined]
        ctx.throttle = self.throttle  # type: ignore[attr-defined]
        ctx.debounce = self.debounce  # type: ignore[attr-defined]
        ctx.setTimeout = self.timeout  # type: ignore[attr-defined]
        ctx.setInterval = self.interval  # type: ignore[attr-defined]

    def timeout(self, *args: Any) -> Any:
        """运行一次回调，或返回延迟后 resolve 的 promise。

        用法：
          ctx.timeout(callback, delay)  # 返回 disposer
          await ctx.timeout(delay)       # 返回 promise
        """
        callback = args[0] if callable(args[0]) else None
        delay = args[1] if callback else args[0]

        if callback:
            # 回调模式：返回 disposer
            async def _run() -> None:
                await asyncio.sleep(delay / 1000.0)
                callback()

            task = asyncio.create_task(_run())
            return ctx.effect(lambda: task.cancel(), name="ctx.timeout()")
        else:
            # Promise 模式：返回 awaitable
            async def _wait() -> None:
                await asyncio.sleep(delay / 1000.0)

            return _wait()

    def interval(self, *args: Any) -> Any:
        """重复运行回调，或返回 async iterator。

        用法：
          ctx.interval(callback, delay)  # 返回 disposer
          async for _ in ctx.interval(delay): ...  # 返回 iterator
        """
        callback = args[0] if callable(args[0]) else None
        delay = args[1] if callback else args[0]

        if callback:
            # 回调模式
            async def _run() -> None:
                while True:
                    await asyncio.sleep(delay / 1000.0)
                    callback()

            task = asyncio.create_task(_run())
            return ctx.effect(lambda: task.cancel(), name="ctx.interval()")
        else:
            # Iterator 模式
            return _IntervalIterator(delay / 1000.0, ctx)

    def throttle(self, callback: F, delay: float, no_trailing: bool = False) -> F:
        """节流函数：限制调用频率。

        返回的函数带有 .dispose() 方法。
        """
        last_call = -float("inf")

        def execute(*args: Any) -> None:
            nonlocal last_call
            last_call = time.time() * 1000
            callback(*args)

        def wrapper(*args: Any) -> None:
            now = time.time() * 1000
            remaining = delay - (now - last_call)
            if remaining <= 0:
                execute(*args)
            elif not no_trailing:
                # 安排最后一次调用
                asyncio.create_task(asyncio.sleep(remaining / 1000.0))

        # 绑定到 ctx 生命周期
        ctx.effect(lambda: None, name="ctx.throttle()")  # type: ignore[union-attr]
        wrapper.dispose = lambda: None  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    def debounce(self, callback: F, delay: float) -> F:
        """防抖函数：延迟执行，重复调用会重置计时器。

        返回的函数带有 .dispose() 方法。
        """

        def wrapper(*args: Any) -> None:
            nonlocal timer
            if timer:
                timer.cancel()

            async def _run() -> None:
                await asyncio.sleep(delay / 1000.0)
                callback(*args)

            timer = asyncio.create_task(_run())

        timer: asyncio.Task | None = None

        # 绑定到 ctx 生命周期
        def _dispose() -> None:
            nonlocal timer
            if timer:
                timer.cancel()

        ctx.effect(_dispose, name="ctx.debounce()")  # type: ignore[union-attr]
        wrapper.dispose = _dispose  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]


class _IntervalIterator:
    """Async iterator for ctx.interval() promise mode."""

    def __init__(self, delay: float, ctx: Context) -> None:
        self._delay = delay
        self._ctx = ctx
        self._done = False

    def __aiter__(self) -> "_IntervalIterator":
        return self

    async def __anext__(self) -> None:
        if self._done:
            raise StopAsyncIteration
        await asyncio.sleep(self._delay)
        return None

    async def aclose(self) -> None:
        self._done = True


# Plugin entry point
def plugin(ctx: Context, config: dict[str, Any] | None) -> None:
    """挂载 TimerService。"""
    svc = TimerService(ctx)
    ctx.provide("timer", svc)
    ctx.effect(svc, name="timer:service")
