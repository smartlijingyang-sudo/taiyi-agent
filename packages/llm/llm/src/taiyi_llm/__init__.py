"""taiyi-llm — LLM capability seam for the agent loop.

公开 surface（对应 dsh-llm MVP 子集）：

  Message             — provider-neutral conversation message（dict-shaped）
  StreamChunk         — provider stream chunk vocabulary + to_dict / from_dict
  LLMProvider         — Protocol for any provider implementation
  LLMService          — ctx.llm entry; provider registry + dispatch + stream/complete

  LLMError            — base + 子类（Auth / RateLimit / ContextLength / Network / ...）
  LLMResponse         — 非流式调用的结果容器

  RetryPolicy         — 指数退避 retry 策略；async execute(call_fn) 入口

  Constants:          CHUNK_CONTENT / CHUNK_TOOL_CALL / CHUNK_DONE / CHUNK_ERROR,
                      ROLE_SYSTEM / USER / ASSISTANT / TOOL

本包**不** import 其他 taiyi_* 包；providers（taiyi-llm-deepseek 等）反向依赖这里。
"""

from __future__ import annotations

from .errors import (
    CODE_ABORTED,
    CODE_AUTH,
    CODE_CONTEXT_LENGTH,
    CODE_INVALID_CREDENTIAL,
    CODE_INVALID_REQUEST,
    CODE_NETWORK,
    CODE_NO_ADAPTER,
    CODE_RATE_LIMIT,
    CODE_UNKNOWN,
    LLMAbortedError,
    LLMAuthError,
    LLMContextLengthError,
    LLMError,
    LLMInvalidRequestError,
    LLMNetworkError,
    LLMNoAdapterError,
    LLMRateLimitError,
    LLMResponse,
)
from .message import (
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_TOOL,
    ROLE_USER,
    VALID_ROLES,
    Message,
    normalize_messages,
)
from .retry import DEFAULT_RETRYABLE, RetryPolicy
from .service import LLMProvider, LLMService
from .stream import (
    ALL_CHUNK_TYPES,
    CHUNK_BLOCK_END,
    CHUNK_BLOCK_START,
    CHUNK_CONTENT,
    CHUNK_DONE,
    CHUNK_ERROR,
    CHUNK_FINISH,
    CHUNK_REASONING,
    CHUNK_TEXT_DELTA,
    CHUNK_TOOL_CALL,
    CHUNK_USAGE,
    CORE_CHUNK_TYPES,
    EXTENDED_CHUNK_TYPES,
    FINISH_ABORTED,
    FINISH_ERROR,
    FINISH_LENGTH,
    FINISH_STOP,
    FINISH_TOOL_CALLS,
    StreamChunk,
)

__all__ = [
    # message
    "Message",
    "ROLE_SYSTEM",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_TOOL",
    "VALID_ROLES",
    "normalize_messages",
    # stream
    "StreamChunk",
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
    "FINISH_STOP",
    "FINISH_TOOL_CALLS",
    "FINISH_LENGTH",
    "FINISH_ERROR",
    "FINISH_ABORTED",
    # provider / service
    "LLMProvider",
    "LLMService",
    # errors
    "LLMError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMContextLengthError",
    "LLMNetworkError",
    "LLMInvalidRequestError",
    "LLMNoAdapterError",
    "LLMAbortedError",
    "LLMResponse",
    "CODE_AUTH",
    "CODE_RATE_LIMIT",
    "CODE_CONTEXT_LENGTH",
    "CODE_NETWORK",
    "CODE_INVALID_REQUEST",
    "CODE_NO_ADAPTER",
    "CODE_UNKNOWN",
    "CODE_INVALID_CREDENTIAL",
    "CODE_ABORTED",
    # retry
    "RetryPolicy",
    "DEFAULT_RETRYABLE",
]