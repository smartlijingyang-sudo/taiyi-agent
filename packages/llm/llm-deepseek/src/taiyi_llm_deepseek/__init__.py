"""taiyi-llm-deepseek — DeepSeek provider（OpenAI-compatible）。

提供：
  - DeepSeekProvider（实现 LLMProvider Protocol）
  - DEFAULT_BASE_URL = "https://api.deepseek.com"

支持：
  - 流式输出（SSE）
  - 工具调用（tool_calls）
  - 未配置 API key 时自动 mock
"""
from __future__ import annotations

import json
import os
from typing import AsyncIterator

import httpx

from taiyi_llm import (
    StreamChunk,
    LLMProvider,
    CHUNK_CONTENT,
    CHUNK_TOOL_CALL,
    CHUNK_DONE,
    CHUNK_ERROR,
)

DEFAULT_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    """DeepSeek provider。

    用法：
      provider = DeepSeekProvider()  # 读环境变量 DEEPSEEK_API_KEY
      async for chunk in provider.stream(model="deepseek-chat", messages=[...], ...):
          ...
    """

    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("TAIYI_DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncIterator[StreamChunk]:
        """流式调用。"""
        if not self.is_configured():
            # 未配置 key：mock 流式响应
            async for chunk in _mock_stream(messages):
                yield chunk
            return

        # 构造请求
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=body,
                    headers=self._headers(),
                ) as resp:
                    resp.raise_for_status()

                    # 解析 SSE
                    tool_buf: dict[int, dict] = {}

                    async for raw in resp.aiter_lines():
                        if not raw or not raw.startswith("data:"):
                            continue
                        payload = raw.removeprefix("data:").strip()
                        if payload == "[DONE]":
                            # flush pending tool calls
                            for idx in sorted(tool_buf):
                                slot = tool_buf[idx]
                                yield StreamChunk(
                                    type=CHUNK_TOOL_CALL,
                                    tool_call_id=slot.get("id", ""),
                                    name=slot.get("name", ""),
                                    arguments=slot.get("arguments", {}),
                                    index=idx,
                                )
                            yield StreamChunk(type=CHUNK_DONE)
                            return

                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        for choice in obj.get("choices") or []:
                            delta = choice.get("delta") or {}

                            # 文本内容
                            content = delta.get("content")
                            if content:
                                yield StreamChunk(type=CHUNK_CONTENT, delta=content)

                            # 工具调用（增量）
                            for tc in delta.get("tool_calls") or []:
                                idx = tc.get("index", 0)
                                slot = tool_buf.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] = fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments"] = (slot.get("arguments") or "") + fn["arguments"]

        except httpx.HTTPError as e:
            yield StreamChunk(type=CHUNK_ERROR, error=f"{type(e).__name__}: {e}")


async def _mock_stream(messages: list[dict]) -> AsyncIterator[StreamChunk]:
    """未配置 API key 时的 mock 流式响应。"""
    last_user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    user_text = last_user.get("content", "")
    reply = (
        f"（mock · 未配置 DEEPSEEK_API_KEY）我已收到：{user_text[:60]}\n\n"
        "请设置环境变量 DEEPSEEK_API_KEY 以使用真实模型。\n"
        "获取：https://platform.deepseek.com/api_keys"
    )
    for char in reply:
        yield StreamChunk(type=CHUNK_CONTENT, delta=char)
    yield StreamChunk(type=CHUNK_DONE)


__all__ = [
    "DeepSeekProvider",
    "DEFAULT_BASE_URL",
]
