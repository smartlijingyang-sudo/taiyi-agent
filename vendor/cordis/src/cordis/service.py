"""Service — 注入 ctx 的命名单例。

cordis 的 Service：
  - 构造时拿 ctx
  - 可选 start() / dispose() 生命周期
  - 通过 ctx.provide(name, self) 注册
  - 子 ctx 通过 ctx.inject(name) 拿到

Python 版：
  - Service 是 base class（也可作 Protocol 使用）
  - 派生类必须能在构造时拿 ctx
  - dispose 是 async（cordis TS 是 sync，Python 这里走 async）
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from .context import Context


class Service:
    """service 基类。

    子类惯例：
        class MyService(Service):
            def __init__(self, ctx: Context, ...):
                super().__init__(ctx)
                ...

            async def start(self) -> None:
                ...

            async def dispose(self) -> None:
                ...
    """

    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx

    async def start(self) -> None:
        """可选初始化钩子；在 effect 挂载前调用。"""

    async def dispose(self) -> None:
        """可选拆卸钩子；在 ctx 拆卸时调用。"""


class ServiceAware:
    """service-aware ctx 扩展：ctx 上 service 名 → 实例 的注入点。"""

    @staticmethod
    def attach(ctx: "Context", name: str, instance: Any) -> None:
        ctx.provide(name, instance)

    @staticmethod
    def detach(ctx: "Context", name: str) -> Any:
        return ctx._services.pop(name, None) if hasattr(ctx, "_services") else None