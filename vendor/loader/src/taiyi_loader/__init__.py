"""taiyi-loader — Plugin loader with entry tree.

对齐 dsh vendor/loader：提供插件加载器，管理 entry 树，支持分组、嵌套、隔离。

核心概念：
  - Entry: 单个插件配置（plugin + config + enabled/disabled）
  - EntryGroup: entry 列表的运行时所有者
  - EntryTree: 所有 entry 的树形存储
  - Loader: 顶层服务，拥有 entry tree 并导入配置的插件
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from cordis import Context, Service

__all__ = ["Entry", "EntryGroup", "EntryTree", "Loader", "plugin"]


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


@dataclass
class EntryOptions:
    """Entry 配置选项。"""

    plugin: str
    config: dict[str, Any] = field(default_factory=dict)
    disabled: bool = False
    patches: list[dict] = field(default_factory=list)


class Entry:
    """单个插件 entry。

    管理插件的生命周期：加载、启动、更新、停止。
    """

    def __init__(self, loader: "Loader", options: EntryOptions | None = None) -> None:
        self.loader = loader
        self.options = options or EntryOptions(plugin="")
        self.parent: EntryGroup | None = None
        self.subgroup: EntryGroup | None = None
        
        # Entry 状态
        self._fiber: Context | None = None
        self._disposer: Callable | None = None
        self._ready = False

    @property
    def id(self) -> str:
        return f"{self.options.plugin}:{id(self)}"

    @property
    def context(self) -> Context:
        return self.loader.ctx

    async def update(self, options: EntryOptions | dict, create: bool = False, reuse: bool = False) -> None:
        """更新 entry 配置。

        Args:
            options: 新配置
            create: 是否强制创建（替换现有）
            reuse: 是否重用现有 fiber
        """
        if isinstance(options, dict):
            options = EntryOptions(**options)
        
        old_options = self.options
        self.options = options
        
        # 如果插件已加载，需要重新加载
        if self._ready and not reuse:
            await self._dispose()
        
        if not options.disabled:
            await self._load()

    async def _load(self) -> None:
        """加载插件。"""
        if self._ready:
            return
        
        # 创建子 fiber
        self._fiber = self.loader.ctx.scope(name=f"entry:{self.options.plugin}")
        
        # 解析并调用插件
        plugin_fn = self._resolve_plugin(self.options.plugin)
        if plugin_fn:
            try:
                await self._fiber.plugin(plugin_fn, self.options.config)
                self._ready = True
            except Exception as e:
                # 加载失败，清理
                if self._fiber:
                    await self._fiber.dispose()
                    self._fiber = None
                raise

    async def _dispose(self) -> None:
        """卸载插件。"""
        if not self._ready:
            return
        
        if self._fiber:
            await self._fiber.dispose()
            self._fiber = None
        
        self._ready = False

    @staticmethod
    def _resolve_plugin(plugin_path: str) -> Callable | None:
        """解析插件路径为可调用对象。"""
        import importlib
        
        try:
            if ":" in plugin_path:
                module_path, attr = plugin_path.split(":", 1)
            else:
                module_path, attr = plugin_path.rsplit(".", 1)
            
            mod = importlib.import_module(module_path)
            fn = getattr(mod, attr, None)
            if fn and hasattr(fn, "raw"):
                return fn.raw
            return fn
        except (ImportError, AttributeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# EntryGroup
# ---------------------------------------------------------------------------


class EntryGroup:
    """Entry 列表的运行时所有者。"""

    key = "cordis.group"

    def __init__(self, ctx: Context, tree: "EntryTree") -> None:
        self.ctx = ctx
        self.tree = tree
        self.data: list[EntryOptions] = []

    @property
    def context(self) -> Context:
        return self.ctx

    async def create(self, options: EntryOptions | dict) -> str:
        """创建新的 entry。"""
        if isinstance(options, dict):
            options = EntryOptions(**options)
        
        entry_id = self.tree.ensure_id(options)
        existing = self.tree.store.get(entry_id)
        entry = existing or Entry(self.tree.loader)
        
        entry.parent = self
        self.tree.store[entry_id] = entry
        
        try:
            await entry.update(options, create=True)
            return entry_id
        except Exception:
            if not existing:
                del self.tree.store[entry_id]
            raise

    async def remove(self, entry_id: str, is_dispose: bool = False) -> None:
        """删除 entry。"""
        entry = self.tree.store.get(entry_id)
        if not entry:
            return
        
        await entry._dispose()
        
        if not is_dispose:
            if entry.options in self.data:
                self.data.remove(entry.options)
        
        del self.tree.store[entry_id]

    async def update(self, config: list[EntryOptions | dict]) -> None:
        """更新 entry 列表。"""
        old_config = self.data
        
        # 规范化配置
        normalized = []
        for opt in config:
            if isinstance(opt, dict):
                normalized.append(EntryOptions(**opt))
            else:
                normalized.append(opt)
        
        # 检查重复 ID
        seen = set()
        for options in normalized:
            entry_id = self.tree.ensure_id(options)
            if entry_id in seen:
                raise TypeError(f"duplicate loader entry id: {entry_id}")
            seen.add(entry_id)
        
        old_map = {self.tree.ensure_id(opt): opt for opt in old_config}
        new_map = {self.tree.ensure_id(opt): opt for opt in normalized}

        try:
            # 创建新的 entries
            for options in normalized:
                await self.create(options)
            
            # 删除不存在的 entries
            for entry_id in old_map:
                if entry_id not in new_map:
                    await self.remove(entry_id, is_dispose=True)
            
            self.data = normalized
        except Exception as error:
            # 回滚
            for entry_id in reversed(list(new_map.keys())):
                if entry_id in old_map:
                    continue
                try:
                    await self.remove(entry_id, is_dispose=True)
                except Exception:
                    pass
            
            for options in old_config:
                try:
                    await self.create(options)
                except Exception:
                    pass
            
            self.data = old_config
            raise

    async def stop(self) -> None:
        """停止所有 entries。"""
        for options in list(self.data):
            entry_id = self.tree.ensure_id(options)
            await self.remove(entry_id, is_dispose=True)


# ---------------------------------------------------------------------------
# EntryTree
# ---------------------------------------------------------------------------


class EntryTree:
    """所有 entry 的树形存储。"""

    def __init__(self, loader: "Loader") -> None:
        self.loader = loader
        self.store: dict[str, Entry] = {}
        self._id_counter = 0

    def ensure_id(self, options: EntryOptions) -> str:
        """为 entry 生成或获取 ID。"""
        # 如果有显式 ID，使用它
        if hasattr(options, "id"):
            return options.id  # type: ignore
        
        # 否则生成一个
        self._id_counter += 1
        return f"{options.plugin}:{self._id_counter}"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class Loader(Service):
    """插件加载器服务。

    拥有 entry tree，导入配置的插件。
    """

    def __init__(self, ctx: Context, config: dict[str, Any] | None = None) -> None:
        super().__init__(ctx)
        self.config = config or {}
        self.tree = EntryTree(self)
        self.builtins: dict[str, Any] = {}
        
        # 设置 base URL
        if "base_url" in self.config:
            ctx.base_url = self.config["base_url"]  # type: ignore

    async def load_entry(self, options: EntryOptions | dict) -> str:
        """加载单个 entry。"""
        if isinstance(options, dict):
            options = EntryOptions(**options)
        
        entry_id = self.tree.ensure_id(options)
        entry = Entry(self, options)
        self.tree.store[entry_id] = entry
        
        await entry.update(options, create=True)
        return entry_id

    async def load_entries(self, config: list[EntryOptions | dict]) -> list[str]:
        """批量加载 entries。"""
        entry_ids = []
        for options in config:
            entry_id = await self.load_entry(options)
            entry_ids.append(entry_id)
        return entry_ids

    async def dispose(self) -> None:
        """卸载所有 entries。"""
        for entry in list(self.tree.store.values()):
            await entry._dispose()
        self.tree.store.clear()


def plugin(ctx: Context, config: dict[str, Any] | None) -> None:
    """挂载 Loader 服务。"""
    loader = Loader(ctx, config)
    ctx.provide("loader", loader)
    ctx.effect(loader, name="loader:service")
