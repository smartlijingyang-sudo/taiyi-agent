"""RetryPolicy — 指数退避重试，对齐 dsh-llm/retry-policy.ts 的 MVP 简化版。

可作为 RetryProvider 的策略（`packages/llm/llm-retry`），也可独立作为
`async execute(call_fn)` helper 用在别处。

默认行为：
  - max_retries=2（首次后最多再试 2 次，共 3 次）
  - backoff_base=0.5s, max_backoff=10s
  - retryable_errors = (TimeoutError, ConnectionError, LLMNetworkError,
                       LLMRateLimitError)
  - jitter_ratio=0.1（对称抖动，避免 thundering herd）
"""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

from .errors import LLMError, LLMNetworkError, LLMRateLimitError

T = TypeVar("T")


DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    LLMNetworkError,
    LLMRateLimitError,
)


# Codes that should never trigger a retry even if the wrapping exception
# is in `retryable_errors`. These represent permanent failures.
_NEVER_RETRY_CODES: frozenset[str] = frozenset(
    {
        "CONTEXT_WINDOW_EXCEEDED",
        "INVALID_REQUEST",
        "INVALID_CREDENTIAL",
        "NO_ADAPTER",
        "AUTH",
    }
)


class RetryPolicy:
    """Exponential backoff retry policy with symmetric jitter.

    Args:
      max_retries: 最多重试次数（不含首次 attempt）；0 表示不重试。
      backoff_base: 第一次重试前的延迟（秒）；后续 attempt 翻倍。
      max_backoff: 单次延迟上限（秒），避免网络抖动时等待过久。
      retryable_errors: 触发重试的异常类型 tuple。
      jitter_ratio: 对称抖动比例 [0, 1]；0 关闭抖动。
      sleep: async sleep callable（默认 `asyncio.sleep`），便于测试注入。
      on_retry: 重试前调用的 hook `(attempt, exc, delay) -> None`。
    """

    def __init__(
        self,
        *,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        max_backoff: float = 10.0,
        retryable_errors: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE,
        jitter_ratio: float = 0.1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_retry: Callable[[int, BaseException, float], None] | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        if backoff_base <= 0 or max_backoff <= 0:
            raise ValueError("backoff_base and max_backoff must be > 0")
        if backoff_base > max_backoff:
            raise ValueError("backoff_base must be <= max_backoff")
        if not 0 <= jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be in [0, 1]")

        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff
        self.retryable_errors = tuple(retryable_errors)
        self.jitter_ratio = jitter_ratio
        self._sleep = sleep
        self._on_retry = on_retry

    def is_retryable(self, exc: BaseException) -> bool:
        """Decide if `exc` is worth retrying.

        `LLMError` subclasses with codes in the never-retry set
        (`CONTEXT_WINDOW_EXCEEDED`, `AUTH`, ...) always return False.
        """
        if isinstance(exc, LLMError) and exc.code in _NEVER_RETRY_CODES:
            return False
        return isinstance(exc, self.retryable_errors)

    def compute_backoff(self, attempt: int) -> float:
        """Compute delay before the Nth retry (1-indexed).

        Exponential: `min(base * 2 ** (attempt - 1), max_backoff)`, then
        apply symmetric jitter if `jitter_ratio > 0`.
        """
        if attempt < 1:
            return 0.0
        delay = self.backoff_base * (2 ** (attempt - 1))
        delay = min(delay, self.max_backoff)
        if self.jitter_ratio > 0:
            jitter = delay * self.jitter_ratio
            delay = max(0.0, delay + random.uniform(-jitter, jitter))
        return delay

    async def execute(self, call_fn: Callable[[], Awaitable[T]]) -> T:
        """Run `call_fn` with exponential-backoff retry on retryable errors.

        Returns the awaited result on first success. On exhaustion, raises
        the last caught exception (does NOT wrap in a generic wrapper).

        Args:
          call_fn: zero-arg async callable. Re-invoked on each retry.
        """
        attempt = 0
        last_exc: BaseException | None = None
        while True:
            try:
                return await call_fn()
            except BaseException as exc:  # noqa: BLE001 — explicit policy
                if not self.is_retryable(exc):
                    raise
                last_exc = exc
                attempt += 1
                if attempt > self.max_retries:
                    raise
                delay = self.compute_backoff(attempt)
                if self._on_retry is not None:
                    try:
                        self._on_retry(attempt, exc, delay)
                    except Exception:  # noqa: BLE001 — hook must never break retry
                        pass
                if delay > 0:
                    await self._sleep(delay)

        # Unreachable; loop either returns or raises.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("RetryPolicy.execute exited without result")

    def __repr__(self) -> str:
        return (
            f"RetryPolicy(max_retries={self.max_retries}, "
            f"backoff_base={self.backoff_base}, max_backoff={self.max_backoff}, "
            f"retryable_errors={len(self.retryable_errors)})"
        )


__all__ = ["RetryPolicy", "DEFAULT_RETRYABLE"]