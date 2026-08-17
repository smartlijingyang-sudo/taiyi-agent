"""Schema 工具：dict → validated config。

复刻 schemastery 的 Schema.from() / schema(meta) 入口。
"""
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from . import Schema

T = TypeVar("T", bound=BaseModel)


def from_dict(model: type[T], data: Any) -> T:
    """dict / None → typed config 实例。失败抛 ValidationError。"""
    if data is None:
        return model()
    return model.model_validate(data)


def safe_from_dict(model: type[T], data: Any, fallback: T | None = None) -> T:
    """不抛异常的 from_dict；失败返回 fallback。"""
    try:
        return from_dict(model, data)
    except ValidationError:
        return fallback if fallback is not None else model()


__all__ = ["from_dict", "safe_from_dict", "Schema"]