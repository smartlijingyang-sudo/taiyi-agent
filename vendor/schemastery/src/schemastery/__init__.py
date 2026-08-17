"""taiyi-schemastery — 轻量 schema 校验。

用 pydantic 作为底座，对外暴露 Schema/Field/Union/List/Dict/Const/Optional 等
可与 deepseek-harness dsh.<group>.Config 对齐的 surface。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, TypeVar

T = TypeVar("T", bound="Schema")


class Schema(BaseModel):
    """BaseModel 的别名 — 与 deepseek-harness 的 Schema 类对应。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


__all__ = ["Schema", "Field", "BaseModel", "Any"]