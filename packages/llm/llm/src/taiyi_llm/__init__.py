"""taiyi-llm — LLM capability seam.

提供：
  - Message 类型（system / user / assistant / tool）
  - StreamChunk 流式数据块
  - LLMProvider Protocol（provider 协议）
  - LLMService（provider 注册 + dispatch）
  - LLMError 异常层次
  - RetryPolicy（重试策略）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------


class Message(dict):
    """消息类型（兼容 dict 接口）。

    角色：system / user / assistant / tool
    """

    @staticmethod
    def system(content: str) -> dict:
        return {"role": "system", "content": content}

    @staticmethod
    def user(content: str | list) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
        msg: dict = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg

    @staticmethod
    def tool_result(tool_call_id: str, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }


# ---------------------------------------------------------------------------
# Stream types
# ---------------------------------------------------------------------------

CHUNK_CONTENT = "content"
CHUNK_TOOL_CALL = "tool_call"
CHUNK_DONE = "done"
CHUNK_ERROR = "error"


@dataclass
class StreamChunk:
    """流式数据块。

    type:
      - "content": 文本增量（delta 字段）
      - "tool_call": 工具调用增量（tool_call_id, name, arguments, index）
      - "done": 流结束
      - "error": 错误（error 字段）
    """

    type: str = CHUNK_DONE
    delta: str = ""
    tool_call_id: str = ""
    name: str = ""
    arguments: dict = field(default_factory=dict)
    error: str = ""
    index: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "delta": self.delta,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "arguments": self.arguments,
            "error": self.error,
            "index": self.index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StreamChunk:
        return cls(
            type=d.get("type", CHUNK_DONE),
            delta=d.get("delta", ""),
            tool_call_id=d.get("tool_call_id", ""),
            name=d.get("name", ""),
            arguments=d.get("arguments", {}),
            error=d.get("error", ""),
            index=d.get("index", 0),
        )


# ---------------------------------------------------------------------------
# LLMProvider Protocol
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """LLM provider 协议。

    实现者必须提供：
      - name: str — provider 标识
      - stream(*, model, messages, tools, temperature, max_tokens) -> AsyncIterator[StreamChunk]
    """

    name: str

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncIterator[StreamChunk]: ...


# ---------------------------------------------------------------------------
# LLMError 异常层次
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """LLM 错误基类。"""


class LLMAuthError(LLMError):
    """认证错误（401）。"""


class LLMRateLimitError(LLMError):
    """速率限制（429）。"""


class LLMContextLengthError(LLMError):
    """上下文超长（400）。"""


class LLMNetworkError(LLMError):
    """网络错误。"""


@dataclass
class LLMResponse:
    """LLM 完整响应（非流式）。"""

    content: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict | None = None
    model: str = ""
    finish_reason: str = ""


# ---------------------------------------------------------------------------
# LLMService
# ---------------------------------------------------------------------------


class LLMService:
    """LLM 服务：provider 注册 + dispatch。

    用法：
      llm = LLMService()
      llm.register_provider(DeepSeekProvider(), default=True)
      async for chunk in llm.stream(model="deepseek-chat", messages=[...], ...):
          ...
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str | None = None

    def register_provider(self, provider: LLMProvider, default: bool = False) -> None:
        """注册 provider。default=True 时设为默认。"""
        self._providers[provider.name] = provider
        if default or self._default is None:
            self._default = provider.name

    def provider_for(self, model: str) -> LLMProvider:
        """根据 model 名选择 provider。

        规则：
          - model 以 provider.name 开头 → 该 provider
          - 否则 → default provider
        """
        for name, provider in self._providers.items():
            if model.startswith(name):
                return provider
        if self._default is None:
            raise LLMError("No LLM provider registered")
        return self._providers[self._default]

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式调用。"""
        provider = self.provider_for(model)
        async for chunk in provider.stream(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """非流式调用：累积 content chunks。"""
        out: list[str] = []
        async for chunk in self.stream(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.type == CHUNK_CONTENT:
                out.append(chunk.delta)
        return "".join(out)


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


class RetryPolicy:
    """重试策略。"""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        max_backoff: float = 30.0,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff

    def backoff_for(self, attempt: int) -> float:
        """计算第 attempt 次重试的退避时间（秒）。"""
        import math
        return min(self.backoff_base * math.exp(attempt), self.max_backoff)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "Message",
    "StreamChunk",
    "CHUNK_CONTENT",
    "CHUNK_TOOL_CALL",
    "CHUNK_DONE",
    "CHUNK_ERROR",
    "LLMProvider",
    "LLMService",
    "LLMError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMContextLengthError",
    "LLMNetworkError",
    "LLMResponse",
    "RetryPolicy",
]
