"""taiyi-llm-retry — 指数退避重试 provider 装饰器。

任何 LLMProvider 可被 RetryProvider 包装；遇 transient 错误按指数退避重试。
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import httpx

from taiyi_llm import StreamChunk

__all__ = ["RetryProvider", "RetryPolicy"]


class RetryPolicy:
    """重试策略。

    字段：
      - max_retries: 最多重试次数（不含首次）
      - backoff_base: 退避基数（秒）
      - max_backoff: 单次最大退避（秒）
      - retryable_exceptions: 触发重试的异常 tuple
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        max_backoff: float = 30.0,
        retryable_exceptions: tuple[type[BaseException], ...] = (
            httpx.HTTPError,
            TimeoutError,
            ConnectionError,
        ),
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff
        self.retryable_exceptions = retryable_exceptions

    def backoff(self, attempt: int) -> float:
        """计算第 attempt 次重试前的等待秒数（指数退避 + 上限）。"""
        return min(self.backoff_base * (2 ** (attempt - 1)), self.max_backoff)


class RetryProvider:
    """包装任意 LLMProvider；遇 transient error 指数退避重试。

    字段：
      - name: 透传 inner.name
      - inner: 被包装的 provider
      - policy: RetryPolicy
    """

    def __init__(self, inner, *, policy: RetryPolicy | None = None):
        self.inner = inner
        self.policy = policy or RetryPolicy()
        self.name = getattr(inner, "name", "wrapped")

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncIterator[StreamChunk]:
        attempt = 0
        while True:
            try:
                async for chunk in self.inner.stream(
                    model=model,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk
                return
            except self.policy.retryable_exceptions as e:
                attempt += 1
                if attempt > self.policy.max_retries:
                    yield StreamChunk(type="error", error=f"{type(e).__name__}: {e}")
                    return
                wait = self.policy.backoff(attempt)
                await asyncio.sleep(wait)