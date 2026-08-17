"""Plugin — 装饰器 + 装载器。

cordis 的 plugin 是 `async function plugin(ctx, config)`。
装饰器 `@plugin` 只是做语义标记 + 运行时检查。

Python 版额外提供：
  - `Plugin` Protocol（typing）
  - 通用 `apply(plugin_fn, ctx, config)` 同步 / 异步驱动
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


class Plugin(Protocol):
    """plugin 协议：async fn(ctx, config) -> None。"""

    async def __call__(self, ctx: Any, config: Any) -> None: ...


@runtime_checkable
class _IsPlugin(Protocol):
    """duck-typing 检测。"""

    __taiyi_plugin__: bool


def plugin(func: Callable[[Any, Any], Awaitable[None]]) -> Callable:
    """装饰器：标记一个 async 函数为 plugin。

    用法：
        @plugin
        async def setup(ctx, config):
            ...

    校验：函数必须 async。配置 / ctx 透传。
    """

    if not inspect.iscoroutinefunction(func):
        raise TypeError(
            f"@plugin requires async function; "
            f"got {func.__name__!r} which is "
            f"{'async' if inspect.iscoroutinefunction(func) else 'sync'}."
        )

    func.__taiyi_plugin__ = True  # type: ignore[attr-defined]
    return func


async def apply(plugin_fn: Callable, ctx: Any, config: Any) -> None:
    """通用插件启动器：无论 plugin_fn 是 sync fn / async fn / wrapped plugin。"""
    # 解包 @plugin 装饰器
    raw = getattr(plugin_fn, "raw", plugin_fn)
    if not callable(raw):
        raise TypeError(f"plugin {plugin_fn!r} is not callable")
    result = raw(ctx, config)
    if inspect.iscoroutine(result):
        await result