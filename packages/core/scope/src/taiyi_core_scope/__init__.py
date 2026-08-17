"""taiyi-core-scope — per-agent 隔离注册原语。

对标 deepseek-harness dsh-core-scope：ctx.scope() 之上，
提供 `Scope`：在父 ctx 内创建一个隔离命名空间，
新挂载的 services / events / effects 局限在 scope 内。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from cordis import Context, Disposer

__all__ = ["Scope", "scope_plugin"]


class Scope:
    """per-agent 命名空间容器。"""

    def __init__(self, name: str, parent: Context) -> None:
        self.name = name
        self.parent = parent
        self.ctx = parent.scope(name=f"scope:{name}")
        self._mounted: list[Disposer] = []

    def mount(self, plugin_fn: Callable, config: dict | None = None) -> Disposer:
        d = self.ctx.plugin(plugin_fn, config)
        self._mounted.append(d)
        return d

    def emit(self, event: str, *args) -> "object":
        import asyncio

        return asyncio.ensure_future(self.ctx.emit(event, *args))

    async def dispose(self) -> None:
        for d in reversed(self._mounted):
            await d.dispose()
        await self.ctx.dispose()


def scope_plugin(ctx: Context) -> None:
    """注册 Scope 服务到 ctx。"""
    # 这个 plugin 不主动注册 service，而是暴露 helper 函数。
    # service 在 agent 创建时按需 new。
    ctx.state["_scope_helper"] = _helper


def _helper(parent: Context, name: str) -> Scope:
    return Scope(name=name, parent=parent)