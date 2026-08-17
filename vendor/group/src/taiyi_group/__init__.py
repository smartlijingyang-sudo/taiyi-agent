"""taiyi-group — Entry group service.

对齐 dsh vendor/group：管理嵌套的 loader entry 列表，支持创建、更新、删除，带回滚支持。
"""
from __future__ import annotations

from typing import Any

from cordis import Context, Service

__all__ = ["Group", "EntryGroup", "plugin"]


class EntryGroup:
    """Entry 组的运行时所有者。"""

    key = "cordis.group"

    def __init__(self, ctx: Context, tree: Any) -> None:
        self.ctx = ctx
        self.tree = tree
        self.data: list[dict] = []

        # 绑定到当前 fiber 的 entry
        entry = getattr(ctx.fiber, "entry", None)
        if entry:
            entry.subgroup = self

    @property
    def context(self) -> Context:
        return self.ctx

    async def create(self, options: dict) -> str:
        """创建新的 entry。"""
        entry_id = self.tree.ensure_id(options)
        existing = self.tree.store.get(entry_id)
        
        # TODO: 实现 entry 创建和更新逻辑
        # 这里需要调用 loader 的 entry 创建机制
        return entry_id

    def unlink(self, options: dict) -> None:
        """从 data 中移除 options。"""
        if options in self.data:
            self.data.remove(options)

    async def remove(self, entry_id: str, is_dispose: bool = False) -> None:
        """删除 entry。"""
        entry = self.tree.store.get(entry_id)
        if not entry:
            return
        
        # TODO: 实现 entry 的 dispose 逻辑
        if not is_dispose:
            self.unlink(entry.options)
        
        del self.tree.store[entry_id]
        self.context.emit("loader/partial-dispose", entry, entry.options, False)

    async def update(self, config: list[dict]) -> None:
        """更新 entry 列表（支持回滚）。"""
        old_config = self.data
        seen = set()
        
        # 检查重复 ID
        for options in config:
            entry_id = self.tree.ensure_id(options)
            if entry_id in seen:
                raise TypeError(f"duplicate loader entry id: {entry_id}")
            seen.add(entry_id)
        
        old_map = {opt["id"]: opt for opt in old_config if "id" in opt}
        new_map = {opt["id"]: opt for opt in config if "id" in opt}

        try:
            # 创建新的 entries
            for options in config:
                await self.create(options)
            
            # 删除不存在的 entries
            for entry_id in old_map:
                if entry_id not in new_map:
                    await self.remove(entry_id, True)
            
            self.data = config
        except Exception as error:
            # 回滚
            rollback_errors = []
            for entry_id in reversed(list(new_map.keys())):
                if entry_id in old_map:
                    continue
                try:
                    await self.remove(entry_id, True)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            
            for options in old_config:
                try:
                    await self.create(options)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            
            self.data = old_config
            if rollback_errors:
                raise ExceptionGroup("loader entry rollback failed", [error, *rollback_errors])
            raise

    async def stop(self) -> None:
        """停止所有 entries。"""
        for options in self.data:
            await self.remove(options.get("id", ""), True)


class Group(EntryGroup):
    """挂载嵌套 loader entry 组的插件。"""

    initial: list[dict] = []

    def __init__(self, ctx: Context, config: list[dict]) -> None:
        # 获取 parent tree
        entry = getattr(ctx.fiber, "entry", None)
        tree = entry.parent.tree if entry and hasattr(entry, "parent") else None
        super().__init__(ctx, tree)
        
        self.config = config
        ctx.on("internal/update", self.update)

    async def init(self) -> None:
        """初始化：更新配置。"""
        await self.update(self.config)


def plugin(ctx: Context, config: list[dict] | None) -> None:
    """挂载 Group。"""
    cfg = config or Group.initial
    group = Group(ctx, cfg)
    # Group 在构造时自动注册
