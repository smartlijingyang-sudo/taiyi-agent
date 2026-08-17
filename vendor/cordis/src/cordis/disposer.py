"""Disposer — 可逆 effect 的句柄。

cordis 的 Effect 在 Python 里被建模为：
    effect = setup() → disposable
    dispose() → 异步执行 disposable（一次且仅一次）

支持：
  - sync disposable 函数
  - async disposable coroutine
  - 服务对象（自动调用其 dispose 方法）
  - DisposableMixin：标准 dispose 接口
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, Optional, Union

DisposableCallback = Callable[[], Optional[Awaitable[None]]]


class DisposableMixin:
    """混入：让对象拥有标准 dispose() 钩子。"""

    async def dispose(self) -> None:  # pragma: no cover
        return None


class Disposer:
    """effect / 监听器 / plugin 的句柄。

    多次调用 dispose() 只执行一次（幂等）。
    同步与异步 disposable 都支持。
    """

    def __init__(
        self,
        callback: Optional[Union[DisposableCallback, "DisposableMixin"]] = None,
        *,
        name: str = "<disposer>",
    ) -> None:
        self._callback: Optional[DisposableCallback]
        if isinstance(callback, DisposableMixin):
            obj = callback
            self._callback = obj.dispose
        else:
            self._callback = callback
        self._done = False
        self._lock = asyncio.Lock()
        self._name = name

    @property
    def done(self) -> bool:
        return self._done

    @property
    def name(self) -> str:
        return self._name

    async def dispose(self) -> None:
        if self._done:
            return
        async with self._lock:
            if self._done:
                return
            self._done = True
            if self._callback is None:
                return
            try:
                result = self._callback()
                if inspect.iscoroutine(result):
                    await result
            except BaseException as e:
                # 保留上游可观察，但不让一个 disposer 拖垮整个链
                from cosmokit import get_logger

                get_logger("taiyi.cordis").error(
                    f"dispose error in {self._name!r}: {e!r}"
                )
                raise

    def __repr__(self) -> str:
        return f"<Disposer {self._name} done={self._done}>"


async def dispose_all(*disposers: Disposer) -> None:
    """并发 dispose 多个 disposer；任一抛错即终止整批。"""
    await asyncio.gather(*(d.dispose() for d in disposers), return_exceptions=False)