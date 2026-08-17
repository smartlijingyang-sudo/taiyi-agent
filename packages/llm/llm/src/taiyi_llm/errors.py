"""LLM error hierarchy + LLMResponse result container。

对齐 dsh-llm/error.ts 的 HarnessError / LlmError 分类；taiyi MVP 简化为四类
常见错误 + 一个结果容器。`code` 字段是稳定的机器路由标识（不依赖 message
字符串）；retry policy 用它判断是否值得重试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---- canonical error codes (route on these, never on message) ---------

CODE_AUTH = "AUTH"
CODE_RATE_LIMIT = "RATE_LIMIT"
CODE_CONTEXT_LENGTH = "CONTEXT_WINDOW_EXCEEDED"
CODE_NETWORK = "NETWORK"
CODE_INVALID_REQUEST = "INVALID_REQUEST"
CODE_NO_ADAPTER = "NO_ADAPTER"
CODE_UNKNOWN = "UNKNOWN"

# Mirrors dsh-llm/error.ts
CODE_QUOTA_EXCEEDED = "QUOTA"
CODE_EMPTY_RESPONSE = "EMPTY_RESPONSE"
CODE_INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
CODE_INVARIANT = "INVARIANT"
CODE_SERVER = "SERVER"
CODE_TIMEOUT = "TIMEOUT"
CODE_TRANSPORT = "TRANSPORT"
CODE_ABORTED = "ABORTED"


class LLMError(Exception):
    """Base class for all LLM errors。

    Carries a stable `code` (machine-routable, e.g. `"AUTH"`, `"RATE_LIMIT"`)
    distinct from the human-readable message. Retry policy routes on `code`,
    never on the message string.

    Optional `status` (HTTP code), `request_id` (provider diagnostics), and
    `cause` (the original wrapped exception) are exposed as attributes.
    """

    code: str = CODE_UNKNOWN

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        status: int | None = None,
        request_id: str | None = None,
        retry_after_ms: float | None = None,
        cause: BaseException | None = None,
    ) -> None:
        if not message:
            message = self.__class__.__name__
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None and (not isinstance(status, int) or status < 100 or status > 599):
            raise ValueError(f"status must be an HTTP integer 100-599, got {status!r}")
        self.status = status
        self.request_id = request_id
        self.retry_after_ms = retry_after_ms
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        """Serializable payload — never includes the wrapped `cause` (may be huge)."""
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "type": self.__class__.__name__,
        }
        if self.status is not None:
            out["status"] = self.status
        if self.request_id is not None:
            out["request_id"] = self.request_id
        if self.retry_after_ms is not None:
            out["retry_after_ms"] = self.retry_after_ms
        return out

    def __repr__(self) -> str:
        parts = [f"code={self.code!r}", f"message={self.message!r}"]
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.request_id is not None:
            parts.append(f"request_id={self.request_id!r}")
        return f"{self.__class__.__name__}({', '.join(parts)})"


class LLMAuthError(LLMError):
    """Authentication / authorization failure (HTTP 401/403)."""

    code = CODE_AUTH


class LLMRateLimitError(LLMError):
    """Transient rate-limit failure (HTTP 429).

    `retry_after_ms` carries provider-requested delay when the provider
    surfaces it; otherwise retry policy falls back to exponential backoff.
    """

    code = CODE_RATE_LIMIT

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_ms: float | None = None,
        status: int | None = 429,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            retry_after_ms=retry_after_ms,
            status=status,
            **kwargs,
        )


class LLMContextLengthError(LLMError):
    """Request exceeds model's context window.

    Retry policy never retries this — the next attempt needs fewer tokens.
    """

    code = CODE_CONTEXT_LENGTH


class LLMNetworkError(LLMError):
    """Transport-level failure (DNS, connect, read timeout, TLS).

    Default retryable; pairs with `TimeoutError` / `ConnectionError` in
    RetryPolicy's default `retryable_errors`.
    """

    code = CODE_NETWORK


class LLMInvalidRequestError(LLMError):
    """Caller passed invalid arguments (malformed schema, bad model id)."""

    code = CODE_INVALID_REQUEST


class LLMNoAdapterError(LLMError):
    """Requested provider / model has no registered adapter."""

    code = CODE_NO_ADAPTER


class LLMAbortedError(LLMError):
    """Request was cancelled via signal or ctx disposal."""

    code = CODE_ABORTED


# ---- result container --------------------------------------------------

@dataclass
class LLMResponse:
    """Aggregated result of a non-streaming model call (`complete()`).

    For streaming callers, the chunks themselves are the API; LLMResponse is
    only meaningful for the convenience `complete()` helper.
    """

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] | None = None
    model: str = ""
    finish_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "content": self.content,
            "tool_calls": [dict(tc) for tc in self.tool_calls],
            "model": self.model,
            "finish_reason": self.finish_reason,
        }
        if self.usage is not None:
            out["usage"] = dict(self.usage)
        return out

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LLMResponse":
        return cls(
            content=str(payload.get("content", "")),
            tool_calls=list(payload.get("tool_calls") or []),
            usage=payload.get("usage"),
            model=str(payload.get("model", "")),
            finish_reason=str(payload.get("finish_reason", "")),
        )

    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


__all__ = [
    # codes
    "CODE_AUTH",
    "CODE_RATE_LIMIT",
    "CODE_CONTEXT_LENGTH",
    "CODE_NETWORK",
    "CODE_INVALID_REQUEST",
    "CODE_NO_ADAPTER",
    "CODE_UNKNOWN",
    "CODE_QUOTA_EXCEEDED",
    "CODE_EMPTY_RESPONSE",
    "CODE_INVALID_CREDENTIAL",
    "CODE_INVARIANT",
    "CODE_SERVER",
    "CODE_TIMEOUT",
    "CODE_TRANSPORT",
    "CODE_ABORTED",
    # errors
    "LLMError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMContextLengthError",
    "LLMNetworkError",
    "LLMInvalidRequestError",
    "LLMNoAdapterError",
    "LLMAbortedError",
    # result
    "LLMResponse",
]