"""Stream chunk vocabulary — provider streams 在 agent loop 之间的统一协议。

对齐 dsh-llm/types.ts 的 `StreamChunk` discriminated union。MVP 简化：只暴露
content / tool_call / done / error 四种常见类型；thinking / reasoning / usage
等扩展字段保留为可选 chunk 字段，downstream 可选消费。

设计要点：
  - StreamChunk 是 dataclass，便于 IDE 提示和 to_dict / from_dict 序列化
  - `to_dict()` 输出**两个** tool_call id 键（`tool_call_id` 和 `id`），让
    老代码 `chunk.to_dict().get("id")` 也能找到 —— 这是为了兼容
    taiyi-llm-deepseek 现存 producer 和 taiyi-core-agent-loop 现存 consumer。
  - `from_dict()` 同时接受 `id` / `tool_call_id` 两个 key
  - 旧 producer 用 `StreamChunk(type="tool_call", id="c1")` 直接构造，本类
    接受 `id=` kwarg 并内部翻译为 `tool_call_id`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---- chunk type constants ----------------------------------------------

CHUNK_CONTENT = "content"
CHUNK_TOOL_CALL = "tool_call"
CHUNK_DONE = "done"
CHUNK_ERROR = "error"

# 扩展类型（dsh 完整协议）：MVP 不必实现，但保留常量避免拼写错误
CHUNK_REASONING = "reasoning"
CHUNK_TEXT_DELTA = "text-delta"
CHUNK_BLOCK_START = "block-start"
CHUNK_BLOCK_END = "block-end"
CHUNK_USAGE = "usage"
CHUNK_FINISH = "finish"

# MVP 必现的四种
CORE_CHUNK_TYPES: frozenset[str] = frozenset(
    {CHUNK_CONTENT, CHUNK_TOOL_CALL, CHUNK_DONE, CHUNK_ERROR}
)

# dsh 兼容的扩展集（adapters 用了不会报错，但 MVP 不强制处理）
EXTENDED_CHUNK_TYPES: frozenset[str] = frozenset(
    {
        CHUNK_REASONING,
        CHUNK_TEXT_DELTA,
        CHUNK_BLOCK_START,
        CHUNK_BLOCK_END,
        CHUNK_USAGE,
        CHUNK_FINISH,
    }
)

ALL_CHUNK_TYPES: frozenset[str] = CORE_CHUNK_TYPES | EXTENDED_CHUNK_TYPES

# Common finish reasons
FINISH_STOP = "stop"
FINISH_TOOL_CALLS = "tool_calls"
FINISH_LENGTH = "length"
FINISH_ERROR = "error"
FINISH_ABORTED = "aborted"


@dataclass
class StreamChunk:
    """One incremental update from a provider stream。

    使用 `@dataclass` 享受 IDE 自动补全和 `__eq__`；自定义 `__init__` 同时
    接受 `id` 和 `tool_call_id` 两套 kwarg，让下游老代码不受影响。
    """

    type: str = ""
    # content
    delta: str = ""
    # tool_call（canonical 字段名是 tool_call_id）
    tool_call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    # error
    error: str = ""
    # parallel tool call index（dsh-llm block index 对齐）
    index: int = 0
    # optional finish metadata
    finish_reason: str = ""
    usage: dict[str, int] | None = None
    # block / reasoning helpers（dsh-llm 类型未在 MVP 处理）
    block_type: str = ""
    block: dict[str, Any] | None = None
    text: str = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Backward-compat shim：把 legacy `id=` kwarg 翻译为 `tool_call_id=`。
        if "id" in kwargs:
            id_value = kwargs.pop("id")
            kwargs.setdefault("tool_call_id", id_value)
        # 调用 dataclass 自动生成的 __init__（被覆盖后改走我们的，再 forward）
        # 由于本类自定义了 __init__，dataclass 不会再生成；手动赋值。
        # 这里用 object.__setattr__ 配合 type hints 顺序，避免 dataclass 误报。
        # 简化版：已知字段集合，按 dataclass 顺序逐个赋值。
        # 真正的 type / defaults 来自本类签名。
        # 用类签名提取字段顺序，避免和 dataclass 自动生成的 __init__ 重复
        # 实现之间的耦合。
        if args:
            raise TypeError("StreamChunk uses keyword-only arguments")
        # 缺省值由 dataclass 字段定义提供；这里直接设置
        self.type = str(kwargs.pop("type", ""))
        self.delta = str(kwargs.pop("delta", ""))
        self.tool_call_id = str(kwargs.pop("tool_call_id", ""))
        self.name = str(kwargs.pop("name", ""))
        raw_args = kwargs.pop("arguments", None)
        self.arguments = dict(raw_args) if raw_args else {}
        self.error = str(kwargs.pop("error", ""))
        self.index = int(kwargs.pop("index", 0) or 0)
        self.finish_reason = str(kwargs.pop("finish_reason", ""))
        self.usage = kwargs.pop("usage", None)
        self.block_type = str(kwargs.pop("block_type", ""))
        self.block = kwargs.pop("block", None)
        self.text = str(kwargs.pop("text", ""))
        if kwargs:
            raise TypeError(f"StreamChunk unexpected kwargs: {sorted(kwargs)}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict.

        输出同时含 `tool_call_id` 和 `id`（互为别名），让下游 agent loop 既能
        `chunk["tool_call_id"]` 也能 `chunk["id"]` 拿到 tool 调用 id。
        """
        out: dict[str, Any] = {"type": self.type}
        if self.delta:
            out["delta"] = self.delta
        if self.tool_call_id:
            out["tool_call_id"] = self.tool_call_id
            out["id"] = self.tool_call_id  # backward-compat alias
        if self.name:
            out["name"] = self.name
        if self.arguments:
            out["arguments"] = dict(self.arguments)
        if self.error:
            out["error"] = self.error
        if self.index:
            out["index"] = self.index
        if self.finish_reason:
            out["finish_reason"] = self.finish_reason
        if self.usage is not None:
            out["usage"] = dict(self.usage)
        if self.block_type:
            out["block_type"] = self.block_type
        if self.block is not None:
            out["block"] = dict(self.block) if isinstance(self.block, dict) else self.block
        if self.text:
            out["text"] = self.text
        return out

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StreamChunk":
        """Deserialize from a dict; `id` / `tool_call_id` 都接受。"""
        tool_call_id = payload.get("tool_call_id")
        if tool_call_id is None:
            tool_call_id = payload.get("id", "")
        return cls(
            type=str(payload.get("type", "")),
            delta=str(payload.get("delta", "")),
            tool_call_id=str(tool_call_id or ""),
            name=str(payload.get("name", "")),
            arguments=dict(payload.get("arguments") or {}),
            error=str(payload.get("error", "")),
            index=int(payload.get("index", 0) or 0),
            finish_reason=str(payload.get("finish_reason", "")),
            usage=payload.get("usage"),
            block_type=str(payload.get("block_type", "")),
            block=payload.get("block"),
            text=str(payload.get("text", "")),
        )

    # ---- convenience constructors / predicates ---------------------------

    @classmethod
    def content(cls, delta: str, **extra: Any) -> "StreamChunk":
        """Build a content delta chunk; `delta` 是这一批的 token / 字符增量。"""
        return cls(type=CHUNK_CONTENT, delta=delta, **extra)

    @classmethod
    def tool_call(
        cls,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any] | str | None = None,
        *,
        index: int = 0,
    ) -> "StreamChunk":
        """Build a finalized tool_call chunk."""
        if isinstance(arguments, str):
            import json as _json

            try:
                parsed = _json.loads(arguments) if arguments.strip() else {}
            except _json.JSONDecodeError:
                parsed = {"_raw": arguments}
        else:
            parsed = dict(arguments or {})
        return cls(
            type=CHUNK_TOOL_CALL,
            tool_call_id=tool_call_id,
            name=name,
            arguments=parsed,
            index=index,
        )

    @classmethod
    def done(cls, *, finish_reason: str = FINISH_STOP) -> "StreamChunk":
        return cls(type=CHUNK_DONE, finish_reason=finish_reason)

    @classmethod
    def error(cls, message: str) -> "StreamChunk":
        return cls(type=CHUNK_ERROR, error=message)

    # ---- predicates ------------------------------------------------------

    def is_content(self) -> bool:
        return self.type == CHUNK_CONTENT

    def is_tool_call(self) -> bool:
        return self.type == CHUNK_TOOL_CALL

    def is_done(self) -> bool:
        return self.type == CHUNK_DONE

    def is_error(self) -> bool:
        return self.type == CHUNK_ERROR

    def is_terminal(self) -> bool:
        """`done` 或 `error` 都是终止信号；agent loop 据此 break。"""
        return self.type in (CHUNK_DONE, CHUNK_ERROR)


__all__ = [
    # chunk type constants
    "CHUNK_CONTENT",
    "CHUNK_TOOL_CALL",
    "CHUNK_DONE",
    "CHUNK_ERROR",
    "CHUNK_REASONING",
    "CHUNK_TEXT_DELTA",
    "CHUNK_BLOCK_START",
    "CHUNK_BLOCK_END",
    "CHUNK_USAGE",
    "CHUNK_FINISH",
    "CORE_CHUNK_TYPES",
    "EXTENDED_CHUNK_TYPES",
    "ALL_CHUNK_TYPES",
    # finish reasons
    "FINISH_STOP",
    "FINISH_TOOL_CALLS",
    "FINISH_LENGTH",
    "FINISH_ERROR",
    "FINISH_ABORTED",
    # main type
    "StreamChunk",
]