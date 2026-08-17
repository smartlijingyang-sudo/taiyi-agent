"""Context — cordis 的核心 fiber 容器。

提供的语义：
  - 父子 fiber（parent / root / scope）
  - service 注册 / 注入（provide / inject / requires）
  - 事件 5 种派发（emit / parallel / serial / bail / waterfall）
  - effect 注册与逆序 dispose（effect / ctx.dispose()）
  - plugin 挂载（plugin / apply）
  - 生命周期 hooks（ready / dispose）

state 在 fiber 链上共享（child 共享 parent 的 state 对象）；
config 在 fiber 链上合并（child.config 继承并覆盖）。
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Generic, Optional, TypeVar, Union

from .disposer import Disposer, dispose_all
from .event import (
    AnyListener,
    DispatchMode,
    EventOptions,
    _BailSignal,
    _Hook,
    is_bailed,
)
from .plugin import apply
from .registry import Registry
from .service import Service

T = TypeVar("T")


@dataclass
class Hook:
    """生命周期 hook。"""

    name: str
    callback: Callable[["Context"], Union[None, Awaitable[None]]]


def hook(name: str) -> Callable[[Callable], Callable]:
    """装饰器：标记生命周期回调。

    用法：
        @hook('ready')
        async def on_ready(ctx):
            ...
    """

    def deco(fn: Callable) -> Callable:
        fn.__taiyi_hook__ = name  # type: ignore[attr-defined]
        return fn

    return deco


async def ready(ctx: "Context") -> None:
    """触发 ctx.hooks.emit('ready', ctx) 的便利函数。"""
    await ctx.hooks_emit("ready")


async def dispose(ctx: "Context") -> None:
    """便利函数：ctx.dispose() 的别名。"""
    await ctx.dispose()


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

_MISSING = object()


class Context:
    """fiber 容器（cordis Context 的 Python 实现）。

    状态布局：
      - parent / root          fiber 链
      - name                   调试用
      - state                  dict（共享）
      - config                 dict（合并）
      - _services              dict[str, Any]
      - _events                dict[mode, dict[name, list[_Hook]]]
      - _effects               list[Disposer]
      - _children              list[Context]
      - _disposed              bool
    """

    def __init__(
        self,
        *,
        config: Optional[dict] = None,
        parent: Optional["Context"] = None,
        name: str = "root",
        state: Optional[dict] = None,
    ) -> None:
        self.parent = parent
        self.name = name

        # config：子继承父，覆写自己
        merged_config: dict = {}
        if parent is not None:
            merged_config.update(parent.config)
        if config:
            merged_config.update(config)
        self.config = merged_config

        # state：子共享父的 state dict
        if parent is not None:
            self.state = parent.state
        else:
            self.state = dict(state or {})

        self._services: dict[str, Any] = {}
        self._events: dict[str, list[_Hook]] = {}
        self._effects: list[Disposer] = []
        self._children: list["Context"] = []
        self._hooks: list[Hook] = []
        self._disposed = False

    # ------------------------------------------------------------------
    # fiber 关系
    # ------------------------------------------------------------------

    @property
    def root(self) -> "Context":
        node: "Context" = self
        while node.parent is not None:
            node = node.parent
        return node

    def scope(self, name: Optional[str] = None, *, config: Optional[dict] = None) -> "Context":
        """创建子 fiber。子共享 parent.state，child.config 继承 + 覆盖。"""
        child = Context(
            config=config,
            parent=self,
            name=name or f"{self.name}.scope",
        )
        self._children.append(child)
        return child

    @property
    def is_disposed(self) -> bool:
        return self._disposed

    # ------------------------------------------------------------------
    # service 注入
    # ------------------------------------------------------------------

    def provide(self, key: str, instance: Any) -> None:
        """在当前 fiber 注册一个服务。"""
        if key in self._services:
            raise KeyError(f"service {key!r} already provided on ctx {self.name!r}")
        self._services[key] = instance

    def inject(self, key: str, default: Any = _MISSING) -> Any:
        """从 fiber 链查找服务；找不到按 default 行为。"""
        cur: Optional["Context"] = self
        while cur is not None:
            if key in cur._services:
                return cur._services[key]
            cur = cur.parent
        if default is _MISSING:
            raise KeyError(f"service {key!r} not found in fiber chain")
        return default

    def has(self, key: str) -> bool:
        cur: Optional["Context"] = self
        while cur is not None:
            if key in cur._services:
                return True
            cur = cur.parent
        return False

    def requires(self, *keys: str) -> tuple:
        """cordis 风格：注入多个服务，返回 tuple。"""
        return tuple(self.inject(k) for k in keys)

    def services(self) -> dict[str, Any]:
        """合并整个 fiber 链的可见 services。"""
        merged: dict[str, Any] = {}
        chain: list["Context"] = []
        cur: Optional["Context"] = self
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        for node in reversed(chain):
            merged.update(node._services)
        return merged

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def _add_hook(self, name: str, listener: AnyListener, options: EventOptions) -> Disposer:
        priority = 1000 if options.prepend else 0
        hook_obj = _Hook(listener=listener, options=options, priority=priority)
        lst = self._events.setdefault(name, [])
        if options.prepend:
            lst.insert(0, hook_obj)
        else:
            lst.append(hook_obj)
        # 高 priority 先触发
        lst.sort(key=lambda h: -h.priority)

        def _off() -> bool:
            if hook_obj in lst:
                lst.remove(hook_obj)
                return True
            return False

        return Disposer(_off, name=f"hook:{name}")

    def on(
        self,
        name: str,
        listener: AnyListener,
        options: Union[bool, EventOptions] = False,
    ) -> Disposer:
        """注册普通监听器。监听器返回 null/False/Undefined 视为不 bail。"""
        return self._add_hook(name, listener, EventOptions.of(options))

    def once(
        self,
        name: str,
        listener: AnyListener,
        options: Union[bool, EventOptions] = False,
    ) -> Disposer:
        """只触发一次的监听器；首次触发后自动 dispose。"""
        off = self._add_hook(name, listener, EventOptions.of(options))

        async def once_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await _maybe_await(listener(*args, **kwargs))
            finally:
                await off.dispose()

        # 用 wrapper 替换原始 listener：再次 _add_hook 会创建新的；这里直接覆盖 _events 列表里的引用
        # 简化做法：把 _events[name][0] 替换为 _Hook(once_wrapper, options, priority)
        lst = self._events.get(name, [])
        # 找到刚加入的那个并替换
        for i, h in enumerate(lst):
            if h.listener is listener:
                lst[i] = _Hook(listener=once_wrapper, options=h.options, priority=h.priority)
                break
        return off

    def parallel(
        self,
        name: str,
        listener: AnyListener,
        options: Union[bool, EventOptions] = False,
    ) -> Disposer:
        """注册 parallel 监听器（emit 时并发 await）。"""
        return self.on(name, listener, options)

    def serial(
        self,
        name: str,
        listener: AnyListener,
        options: Union[bool, EventOptions] = False,
    ) -> Disposer:
        """注册 serial 监听器（emit 时按序 await，遇 bail 即停）。"""
        return self.on(name, listener, options)

    def bail(
        self,
        name: str,
        listener: AnyListener,
        options: Union[bool, EventOptions] = False,
    ) -> Disposer:
        """注册 bail 监听器（emit 时按序同步触发，遇 bail 即停）。"""
        return self.on(name, listener, options)

    def waterfall(
        self,
        name: str,
        listener: AnyListener,
        options: Union[bool, EventOptions] = False,
    ) -> Disposer:
        """注册 waterfall 监听器；listener 签名必须是 (arg, next) -> value。"""
        return self.on(name, listener, options)

    async def emit(self, name: str, *args: Any) -> Any:
        """统一 emit 入口；按监听器的 priority 顺序串行调用。

        Python 版精简：所有事件都是 await（async event loop 一致）。
        - bail 判定：监听器返回值非 None/False 即停
        - waterfall：监听器须显式 next()
        """
        listeners = list(self._events.get(name, []))
        # 无监听器：空操作
        if not listeners:
            return None

        # 检测是否全部 waterfall
        first_kind = self._infer_kind(name, listeners[0])
        if first_kind == DispatchMode.WATERFALL:
            return await self._dispatch_waterfall(listeners, args)

        # 否则按 bail / serial 处理：sync 模式遇 bail 即停
        result: Any = None
        for hook_obj in listeners:
            try:
                value = hook_obj.listener(*args)
                value = await _maybe_await(value)
            except _BailSignal as sig:
                return sig.payload.value
            if is_bailed(value):
                result = value
                break
        return result

    async def parallel_emit(self, name: str, *args: Any) -> list[Any]:
        """显式并发派发（替代 emit 的同步遍历）。"""
        listeners = list(self._events.get(name, []))
        if not listeners:
            return []
        results = await asyncio.gather(
            *(_maybe_await(h.listener(*args)) for h in listeners),
            return_exceptions=False,
        )
        return list(results)

    def _infer_kind(self, name: str, hook_obj: _Hook) -> DispatchMode:
        """判断事件类型：waterfall 用 listener 签名（参数 >= 2），其它按名字启发。

        实际使用里，waterfall 监听器至少两个参数（event_arg, next）。
        """
        sig = inspect.signature(hook_obj.listener)
        n_params = len([
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ])
        if n_params >= 2:
            return DispatchMode.WATERFALL
        return DispatchMode.SERIAL

    async def _dispatch_waterfall(self, listeners: list[_Hook], args: tuple) -> Any:
        """waterfall dispatch：每个监听器包住 next 调用；不调用 next 即 veto。

        next 链构造（递归）：
          make_next(i) -> async fn(value) -> listener[i](value, make_next(i+1))
        
        如果监听器不调用 next()，返回传入该监听器的值（veto 语义）。
        """
        async def make_next(idx: int):
            if idx >= len(listeners):
                async def end(value: Any) -> Any:
                    return value
                return end

            listener = listeners[idx].listener
            inner = await make_next(idx + 1)

            async def call_with(value: Any) -> Any:
                # 追踪是否调用了 next
                next_called = False
                next_value = value
                
                async def wrapped_next(v: Any) -> Any:
                    nonlocal next_called, next_value
                    next_called = True
                    next_value = await inner(v)
                    return next_value
                
                ret = listener(value, wrapped_next)
                if inspect.iscoroutine(ret):
                    ret = await ret
                
                # 如果没有调用 next，返回传入的值
                if not next_called:
                    return value
                return ret

            return call_with

        if not listeners:
            return args[0] if args else None

        first_next = await make_next(0)
        start = args[0] if args else None
        return await first_next(start)

    # ------------------------------------------------------------------
    # 生命周期 hooks
    # ------------------------------------------------------------------

    def on_lifecycle(self, name: str, callback: Callable) -> Disposer:
        """注册 ctx 生命周期 hook（ready / dispose）。"""
        h = Hook(name=name, callback=callback)
        self._hooks.append(h)

        def _off() -> None:
            if h in self._hooks:
                self._hooks.remove(h)

        return Disposer(_off, name=f"lifecycle:{name}")

    async def hooks_emit(self, name: str) -> None:
        for h in list(self._hooks):
            if h.name == name:
                ret = h.callback(self)
                if inspect.iscoroutine(ret):
                    await ret

    # ------------------------------------------------------------------
    # effect / dispose
    # ------------------------------------------------------------------

    def effect(
        self,
        setup: Optional[Callable] = None,
        *,
        disposer: Optional[Callable] = None,
        name: str = "<effect>",
    ) -> Disposer:
        """注册 effect。

        用法：
          ctx.effect(lambda: None)                          # 仅标记（无 disposer）
          ctx.effect(setup_fn, disposer=cleanup_fn)         # 显式 setup + disposer
          ctx.effect(service_instance)                      # 对象自带 dispose()
          ctx.effect(lambda: my_service, name='svc')        # lazy 创建 service
        """
        cb: Optional[Callable]
        if setup is not None and not callable(setup):
            # 误传对象：当 service / mixin 处理
            obj = setup
            cb = obj.dispose if hasattr(obj, "dispose") else None

            async def _start() -> None:
                start = getattr(obj, "start", None)
                if start is not None:
                    r = start()
                    if inspect.iscoroutine(r):
                        await r

            setup = _start
        else:
            cb = disposer

        # 同步执行 setup
        if setup is not None:
            r = setup()
            if inspect.iscoroutine(r):
                # 在 async 上下文里：直接 await
                try:
                    asyncio.get_running_loop()
                    asyncio.ensure_future(r)
                except RuntimeError:
                    asyncio.run(r)

        d = Disposer(cb, name=name)
        self._effects.append(d)
        return d

    async def dispose(self) -> None:
        """拆卸 fiber。顺序：children → effects → services。"""
        if self._disposed:
            return
        self._disposed = True
        await self.hooks_emit("dispose")

        # 子先拆
        for child in list(self._children):
            await child.dispose()
        self._children.clear()

        # effects 逆序拆
        for d in reversed(self._effects):
            try:
                await d.dispose()
            except Exception:
                pass
        self._effects.clear()

        # services 拆（如有 dispose）
        for svc in self._services.values():
            d = getattr(svc, "dispose", None)
            if d is not None:
                try:
                    r = d()
                    if inspect.iscoroutine(r):
                        await r
                except Exception:
                    pass

        # 从 parent 移除
        if self.parent is not None and self in self.parent._children:
            self.parent._children.remove(self)

    # ------------------------------------------------------------------
    # plugin
    # ------------------------------------------------------------------

    async def plugin(self, plugin_fn: Callable, config: Any = None) -> Disposer:
        """异步挂载 plugin。plugin 是 async fn(ctx, config)。

        把 config merge 到 ctx.config；plugin 在当前 ctx 上运行（共享 fiber）。
        返回的 disposer 用于卸载（仅清理由 plugin 添加的 services）。
        """
        if config is not None and isinstance(config, dict):
            self.config = {**self.config, **config}

        # snapshot 服务：plugin 安装完后只移除自己添加的
        before = set(self._services.keys())

        # plugin 可能 await 也可能不 await
        if hasattr(plugin_fn, "__taiyi_plugin__") or getattr(plugin_fn, "raw", None):
            # @plugin 装饰的
            raw = getattr(plugin_fn, "raw", plugin_fn)
        else:
            raw = plugin_fn

        await apply(raw, self, self.config)
        await self.hooks_emit("plugin:ready")

        async def _dispose() -> None:
            # 移除 plugin 添加的 services（除 Service 实例外）
            added = set(self._services.keys()) - before
            for k in added:
                svc = self._services.pop(k, None)
                d = getattr(svc, "dispose", None)
                if d is not None:
                    try:
                        r = d()
                        if inspect.iscoroutine(r):
                            await r
                    except Exception:
                        pass

        return Disposer(_dispose, name=f"plugin:{getattr(raw, '__name__', 'plugin')}")


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


async def _maybe_await(value: Any) -> Any:
    if inspect.iscoroutine(value):
        return await value
    return value