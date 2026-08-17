"""Event 系统 — 五种 dispatch mode。

cordis TS 版的事件派发（与 Python 1:1 对应）：
  - emit     — 同步触发所有监听器，忽略返回值（fire and forget）
  - parallel — 并发 await 所有监听器
  - serial   — 顺序 await，第一个 bail（非 null/false/undefined）即停
  - bail     — 同步首遇 bail 即停（与 serial 的同步版本）
  - waterfall — 每个监听器须显式 next() 才往下走

监听器可以是 sync 或 async function；dispatch 自动适应。
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar, Union

T = TypeVar("T")


class DispatchMode(str, Enum):
    EMIT = "emit"
    PARALLEL = "parallel"
    SERIAL = "serial"
    BAIL = "bail"
    WATERFALL = "waterfall"


def is_bailed(value: Any) -> bool:
    """cordis 的「bail 判定」：null / False / undefined 视为不 bail，其它视为 bail。"""
    return value is not None and value is not False


# 监听器形态：
#   - 普通监听器：(arg) -> None  | async (arg) -> None
#   - waterfall 监听器：(arg, next) -> T  | async (arg, next) -> T

NormalListener = Callable[..., Union[None, Awaitable[None]]]
WaterfallNext = Callable[[Any], Awaitable[Any]]
WaterfallListener = Callable[..., Union[Any, Awaitable[Any]]]
AnyListener = Union[NormalListener, WaterfallListener]


@dataclass
class EventOptions:
    """注册监听器时的选项。"""

    prepend: bool = False
    """若 True，添加到事件链头部；否则尾部。"""

    global_: bool = False
    """若 True，跳过 ctx 过滤（cordis 的 'global' 监听器）。"""

    @classmethod
    def of(cls, value: Union[bool, "EventOptions"]) -> "EventOptions":
        if isinstance(value, EventOptions):
            return value
        return cls(prepend=bool(value))


# EventsMap 类型扩展：plugin 通过 TypeVar 在 ctx 上声明自己的事件签名。
# 真实场景里：plugin 会 monkey-patch 一个 Protocol 来声明自己的 events。
EventsMap = dict


@dataclass
class _Hook:
    """cordis 中的 Hook（已注册的监听器记录）。"""

    listener: AnyListener
    options: EventOptions = field(default_factory=EventOptions)
    priority: int = 0


async def bail(value: Any) -> Any:
    """显式 bail：serial / bail dispatch 用此函数抛出终止信号。

    cordis 用返回值；Python 版用 sentinel（Bail 类）。
    """
    _BAIL_TOKEN = object()

    class Bail:
        def __init__(self, v: Any) -> None:
            self.value = v

    raise _BailSignal(Bail(value))


class _BailSignal(Exception):
    """serial / bail dispatch 内部终止信号。"""

    def __init__(self, payload: Any) -> None:
        super().__init__("bail")
        self.payload = payload