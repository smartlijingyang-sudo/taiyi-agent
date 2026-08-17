"""Array / dict utilities."""
from __future__ import annotations

from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def make_array(value: T | Iterable[T]) -> list[T]:
    """将单值或可迭代值包装为 list。和 JS Array.prototype 习惯对齐。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def observe(initial, producer):
    """不可变更新：f(x) -> x'。"""
    return producer(initial)


def dict_filter(d: dict, predicate: Callable[[tuple, object], bool]) -> dict:
    """带键的 dict 过滤。"""
    return {k: v for k, v in d.items() if predicate((k, v), v)}


def is_empty(value) -> bool:
    """None / [] / {} / '' 都视为空。"""
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, dict, set)):
        return len(value) == 0
    return False