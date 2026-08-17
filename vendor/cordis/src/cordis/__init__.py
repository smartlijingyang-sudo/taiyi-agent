"""taiyi-cordis — 插件框架（vendored @deepseek-ai/cordis 的 Python 复刻）。

设计原则（对齐 dsh cordis）：
  - 一切皆插件：plugin = async fn(ctx, config)
  - Effect 可逆：setup 返回 disposer，卸载时 dispose
  - Event 五种派发：emit / parallel / serial / bail / waterfall
  - Service：ctx 上的命名单例，可被 inject / provide
  - Registry：typed collection
  - Fiber：每个 ctx 是 fiber；root → child 形成父子链
  - Loader：YAML / dict 配置 → plugin tree

公共 surface 见下方 __all__。
"""
from __future__ import annotations

# dataclass + Protocol + async generators + contextvars 都是 Python 习惯表达
# 与 TS 版不同之处：
#   - sync/async 边界明确：effect 可装 sync 或 coroutine，但 dispose 一定 await
#   - 类型用 Protocol + TypeVar 表达，不靠 runtime metadata
#   - 注册表维护插入顺序；events 按 priority 排序

from .context import Context, Hook, hook, ready, dispose
from .disposer import Disposer, DisposableMixin, dispose_all
from .event import (
    DispatchMode,
    EventOptions,
    EventsMap,
    bail,
    is_bailed,
)
from .loader import (
    Bundle,
    Loader,
    PluginRow,
    dump_config,
    load_bundle,
    merge_bundles,
    mount,
)
from .plugin import Plugin, plugin
from .registry import Registry
from .service import Service

__all__ = [
    # context / lifecycle
    "Context",
    "Hook",
    "hook",
    "ready",
    "dispose",
    # effect / disposer
    "Disposer",
    "DisposableMixin",
    "dispose_all",
    # event
    "DispatchMode",
    "EventOptions",
    "EventsMap",
    "bail",
    "is_bailed",
    # plugin / loader
    "Plugin",
    "plugin",
    "Bundle",
    "PluginRow",
    "Loader",
    "load_bundle",
    "merge_bundles",
    "mount",
    "dump_config",
    # service / registry
    "Service",
    "Registry",
]