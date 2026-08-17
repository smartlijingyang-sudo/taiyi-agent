"""Loader — 从 YAML / dict 配置装载插件树。

cordis loader 的 Python 等价物：
  - Bundle        — 一组 plugin rows
  - PluginRow     — 单个 plugin 配置行
  - Loader        — 装配器
  - mount()       — 异步挂载整个 bundle 列表
  - dump_config() — 对齐 dsh --dump-config
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Union

import yaml

from .context import Context
from .disposer import Disposer
from .plugin import apply


@dataclass
class PluginRow:
    """单 plugin 配置行。

    形态（dict）：
        {"plugin": "pkg.module:fn", "config": {...}, "disabled": False}
    """

    plugin: str
    config: dict = field(default_factory=dict)
    disabled: bool = False

    @classmethod
    def from_value(cls, value: Union[str, dict]) -> "PluginRow":
        if isinstance(value, str):
            return cls(plugin=value)
        if not isinstance(value, dict):
            raise TypeError(f"plugin row must be str or dict, got {type(value)}")
        if "plugin" not in value:
            raise ValueError(f"plugin row missing 'plugin': {value}")
        return cls(
            plugin=value["plugin"],
            config=value.get("config") or {},
            disabled=bool(value.get("disabled", False)),
        )


@dataclass
class Bundle:
    """一组 plugin rows 的有序集合。"""

    name: str
    rows: list[PluginRow] = field(default_factory=list)

    @classmethod
    def from_data(cls, name: str, data: dict) -> "Bundle":
        rows_data = data.get("plugins") or data.get("entries") or []
        return cls(
            name=name,
            rows=[PluginRow.from_value(r) for r in rows_data],
        )


@dataclass
class Loader:
    """装配器：管理 bundle 列表 + mount / unmount。"""

    ctx: Context
    bundles: list[Bundle] = field(default_factory=list)

    def add(self, bundle: Bundle) -> "Loader":
        self.bundles.append(bundle)
        return self

    async def mount(self) -> Disposer:
        """按顺序 mount 所有 bundle；返回总 disposer。"""
        all_disposers: list[Disposer] = []
        for bundle in self.bundles:
            d = await mount_bundle(self.ctx, bundle)
            all_disposers.append(d)
        return Disposer(
            lambda: asyncio.gather(*(d.dispose() for d in reversed(all_disposers))),
            name="loader",
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _resolve_plugin(path: str) -> Callable:
    """解析 'pkg.module:attr' 或 'pkg.module.attr'。

    如果 attr 是 @plugin 装饰的（带 raw），返回 raw；否则直接返回。
    """
    if ":" in path:
        module_path, attr = path.split(":", 1)
    else:
        module_path, attr = path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    fn = getattr(mod, attr)
    if hasattr(fn, "raw"):
        return fn.raw
    return fn


def load_bundle(path: Union[str, Path]) -> Bundle:
    """从 YAML 文件加载 bundle。"""
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    name = p.stem
    return Bundle.from_data(name, data)


def load_bundles_from_dir(path: Union[str, Path]) -> list[Bundle]:
    """从目录加载所有 .yaml / .yml bundle 文件，按文件名字典序。"""
    p = Path(path)
    out: list[Bundle] = []
    for f in sorted(p.glob("*.y*ml")):
        out.append(load_bundle(f))
    return out


def merge_bundles(bundles: list[Bundle]) -> Bundle:
    """合并多个 bundle 为一个；rows 按顺序拼接，过滤 disabled。"""
    merged = Bundle(name="+".join(b.name for b in bundles))
    for b in bundles:
        merged.rows.extend(r for r in b.rows if not r.disabled)
    return merged


async def mount_bundle(ctx: Context, bundle: Bundle) -> Disposer:
    """挂载单个 bundle 的所有 plugin rows。"""
    services_before = set(ctx._services.keys())
    effects_before = list(ctx._effects)

    for row in bundle.rows:
        if row.disabled:
            continue
        await ctx.plugin(_resolve_plugin(row.plugin), row.config)

    async def _dispose_bundle() -> None:
        # 移除 bundle 添加的 services
        added = set(ctx._services.keys()) - services_before
        for k in added:
            svc = ctx._services.pop(k, None)
            d = getattr(svc, "dispose", None)
            if d is not None:
                try:
                    r = d()
                    if inspect.iscoroutine(r):
                        await r
                except Exception:
                    pass
        # 移除 bundle 添加的 effects（按逆序）
        new_effects = ctx._effects[len(effects_before):]
        for e in reversed(new_effects):
            try:
                await e.dispose()
            except Exception:
                pass
        ctx._effects = ctx._effects[: len(effects_before)]

    return Disposer(_dispose_bundle, name=f"bundle({bundle.name})")


async def mount(ctx: Context, bundles: list[Bundle]) -> Disposer:
    """按顺序 mount 所有 bundle，返回总 disposer。"""
    loader = Loader(ctx=ctx, bundles=list(bundles))
    return await loader.mount()


def dump_config(
    bundles: list[Bundle],
    *,
    profile: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """对齐 dsh --dump-config：打印当前要 mount 的 plugin tree。"""
    lines: list[str] = []
    if profile:
        lines.append(f"# profile: {profile}")
    total = sum(len(b.rows) for b in bundles)
    lines.append(f"# total rows: {total}")
    lines.append("")
    for b in bundles:
        lines.append(f"## bundle: {b.name}")
        for r in b.rows:
            cfg = ""
            if r.config:
                cfg_items = ", ".join(f"{k}={v!r}" for k, v in r.config.items())
                cfg = f"  # {cfg_items}"
            status = " (disabled)" if r.disabled else ""
            lines.append(f"  - plugin: {r.plugin}{cfg}{status}")
        lines.append("")
    return "\n".join(lines)