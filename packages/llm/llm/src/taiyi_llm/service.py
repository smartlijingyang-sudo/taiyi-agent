"""LLMService — provider registry + dispatch.

对齐 dsh-llm/index.ts 的 `LlmRuntime`：cordis Service，ctx.llm 入口，
持有 provider 注册表，按 model 名 dispatch 到对应 provider。`stream` 是
agent loop 真正消费的接口；`complete` 是给脚本 / 简单 case 用的便利方法。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from cordis import Context, Service

from .errors import LLMError, LLMNoAdapterError, LLMResponse
from .stream import (
    CHUNK_CONTENT,
    CHUNK_DONE,
    CHUNK_ERROR,
    CHUNK_TOOL_CALL,
    StreamChunk,
)


@runtime_checkable
class LLMProvider(Protocol):
    """Provider protocol — anything with `name` + `async stream(...)` works.

    Concrete providers (e.g. `taiyi-llm-deepseek.DeepSeekProvider`) need NOT
    inherit from this; Python's structural Protocol lets them satisfy it
    implicitly. `register_provider()` will runtime-check via `isinstance`
    so registration gives a clear error for half-implemented providers.
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
    ) -> AsyncIterator[StreamChunk]:
        ...


class LLMService(Service):
    """`ctx.llm` — provider registry + dispatch.

    Providers self-register via `register_provider()` (called from their own
    `@plugin` setup fn). Dispatch is longest-prefix match on the model name:
    `model="deepseek-chat"` → provider registered with `model_prefix="deepseek"`.
    Falls back to the default provider if no prefix matches.

    Example:
        llm = ctx.inject("llm")
        llm.register_provider(DeepSeekProvider(...))
        async for chunk in llm.stream(model="deepseek-chat", messages=...):
            ...
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        # provider.name -> provider
        self._providers: dict[str, Any] = {}
        # ordered list of (prefix, provider_name) for longest-match dispatch
        self._prefixes: list[tuple[str, str]] = []
        # fallback when no prefix matches
        self._default_provider: str | None = None

    # ---- registration --------------------------------------------------

    def register_provider(
        self,
        provider: Any,
        *,
        default: bool = False,
        model_prefix: str | None = None,
    ) -> None:
        """Register a provider.

        Args:
          provider: object with `name: str` and `async def stream(...)`.
          default: also use this as the fallback when no prefix matches.
          model_prefix: prefix used for dispatch; defaults to `provider.name`.

        Raises:
          ValueError: provider has no name, is not a valid LLMProvider, or
                      another provider with the same name is already registered.
        """
        name = getattr(provider, "name", None)
        if not name or not isinstance(name, str):
            raise ValueError(
                f"provider must have a non-empty string `name` attr, got {name!r}"
            )
        if name in self._providers:
            raise ValueError(f"provider {name!r} already registered")
        if not isinstance(provider, LLMProvider):
            # `runtime_checkable` gives clear error for half-implemented providers.
            raise TypeError(
                f"provider {name!r} does not satisfy LLMProvider protocol "
                "(needs `name` and `async def stream(...)`)"
            )
        prefix = model_prefix if model_prefix is not None else name
        if not prefix:
            raise ValueError(f"provider {name!r} model_prefix must be non-empty")

        self._providers[name] = provider
        self._prefixes.append((prefix, name))
        if default or self._default_provider is None:
            self._default_provider = name

    def unregister_provider(self, name: str) -> Any | None:
        """Remove a registered provider; returns the removed instance or None."""
        removed = self._providers.pop(name, None)
        if removed is not None:
            self._prefixes = [(p, n) for p, n in self._prefixes if n != name]
            if self._default_provider == name:
                self._default_provider = next(iter(self._providers), None)
        return removed

    # ---- dispatch ------------------------------------------------------

    def provider_for(self, model: str) -> Any:
        """Resolve the provider for a given model name.

        Strategy: longest registered prefix wins. Tie broken by registration
        order (earliest wins). Falls back to `default` provider when no
        prefix matches.

        Raises:
          LLMNoAdapterError: no provider registered, or none matches.
        """
        if not self._providers:
            raise LLMNoAdapterError(
                "no LLM provider registered; call LLMService.register_provider()"
            )
        best_prefix = ""
        best_name: str | None = None
        for prefix, name in self._prefixes:
            if model.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
                best_name = name
        if best_name is None:
            if self._default_provider is None:
                raise LLMNoAdapterError(
                    f"no LLM provider matches model {model!r}; "
                    f"registered prefixes={[p for p, _ in self._prefixes]}"
                )
            best_name = self._default_provider
        return self._providers[best_name]

    # ---- listing -------------------------------------------------------

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    def list_prefixes(self) -> list[tuple[str, str]]:
        return list(self._prefixes)

    @property
    def default_provider(self) -> str | None:
        return self._default_provider

    # ---- streaming / completion ---------------------------------------

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Dispatch `stream()` to the provider selected by `model`.

        Provider exceptions propagate; the loop is the one place that turns
        transport failures into terminal `error` chunks. Returning a
        StreamChunk generator (not raising) is the normal mode.
        """
        provider = self.provider_for(model)
        async for chunk in provider.stream(
            model=model,
            messages=list(messages),
            tools=list(tools) if tools else None,
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
        """Accumulate `content` chunks into a final string.

        `tool_call` / `done` / `error` chunks are skipped; `error` chunks
        are surfaced as `LLMError` so the caller doesn't silently miss a
        provider failure.

        Returns:
          concatenated `content` deltas. Empty string if the model produced
          no content (e.g. pure tool-call turn).
        """
        chunks: list[str] = []
        async for chunk in self.stream(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.is_content():
                chunks.append(chunk.delta)
            elif chunk.is_error():
                raise LLMError(chunk.error or "provider emitted error chunk")
            elif chunk.is_tool_call():
                # `complete()` aggregates text only — caller wanting
                # tool_calls should consume `stream()` directly.
                continue
        return "".join(chunks)

    async def complete_response(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Like `complete()` but returns an `LLMResponse` with tool_calls + usage."""
        content = ""
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, int] | None = None
        finish_reason = ""
        async for chunk in self.stream(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.is_content():
                content += chunk.delta
            elif chunk.is_tool_call():
                tool_calls.append(
                    {
                        "id": chunk.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": chunk.name,
                            "arguments": chunk.arguments,
                        },
                    }
                )
            elif chunk.is_error():
                raise LLMError(chunk.error or "provider emitted error chunk")
            elif chunk.is_done():
                finish_reason = chunk.finish_reason or finish_reason
            if chunk.usage is not None:
                usage = dict(chunk.usage)
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=model,
            finish_reason=finish_reason or "stop",
        )

    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],
        **kwargs: Any,
    ) -> list[float]:
        """Embedding API — NOT implemented in MVP.

        Providers that support embeddings should expose them directly;
        `LLMService.embed()` exists for forward compatibility and to make
        the absence explicit.
        """
        raise NotImplementedError(
            "LLMService.embed() is not implemented in MVP; "
            "call the provider's embedding API directly"
        )

    # ---- ctx effect / disposal (Service interface) ----------------------

    async def dispose(self) -> None:
        self._providers.clear()
        self._prefixes.clear()
        self._default_provider = None


__all__ = ["LLMProvider", "LLMService"]


# ---- internal helpers (imported by __init__ for type re-export) --------

# Constants re-exposed here so callers can `from taiyi_llm.service import CHUNK_*`.
# Re-imports kept narrow; the canonical home is stream.py.
__all__ += [  # noqa: E501 — list reassignment after function definitions is intentional
    "CHUNK_CONTENT",
    "CHUNK_TOOL_CALL",
    "CHUNK_DONE",
    "CHUNK_ERROR",
]