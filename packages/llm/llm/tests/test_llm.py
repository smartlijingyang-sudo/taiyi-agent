"""Tests for taiyi-llm — message vocabulary, stream chunk, LLMService dispatch,
LLMError hierarchy, RetryPolicy. No network / no real provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from cordis import Context
from taiyi_llm import (
    CHUNK_CONTENT,
    CHUNK_DONE,
    CHUNK_TOOL_CALL,
    CODE_ABORTED,
    CODE_AUTH,
    CODE_CONTEXT_LENGTH,
    CODE_NETWORK,
    CODE_NO_ADAPTER,
    CODE_RATE_LIMIT,
    CODE_UNKNOWN,
    DEFAULT_RETRYABLE,
    FINISH_STOP,
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_TOOL,
    ROLE_USER,
    LLMAbortedError,
    LLMAuthError,
    LLMContextLengthError,
    LLMError,
    LLMInvalidRequestError,
    LLMNetworkError,
    LLMNoAdapterError,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMService,
    Message,
    RetryPolicy,
    StreamChunk,
    normalize_messages,
)

# ---- mock provider for dispatch tests ---------------------------------


class MockProvider:
    """Minimal in-memory provider: yields a canned list of StreamChunks."""

    def __init__(
        self,
        name: str = "mock",
        chunks: list[StreamChunk] | None = None,
        raise_exc: BaseException | None = None,
    ) -> None:
        self.name = name
        self._chunks = chunks if chunks is not None else [StreamChunk(type=CHUNK_DONE)]
        self._raise = raise_exc
        self.calls = 0
        self.last_kwargs: dict = {}

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        self.last_kwargs = {
            "model": model,
            "messages": list(messages),
            "tools": list(tools) if tools else None,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self._raise is not None:
            raise self._raise
        for chunk in self._chunks:
            yield chunk


# ---- Message factories ------------------------------------------------


class TestMessage:
    def test_system(self) -> None:
        m = Message.system("you are helpful")
        assert m == {"role": "system", "content": "you are helpful"}
        assert m["role"] == ROLE_SYSTEM

    def test_user(self) -> None:
        m = Message.user("hi")
        assert m == {"role": "user", "content": "hi"}

    def test_user_with_blocks(self) -> None:
        blocks = [{"type": "text", "text": "hi"}]
        m = Message.user(blocks)
        assert m["content"] == blocks

    def test_assistant(self) -> None:
        m = Message.assistant("reply")
        assert m == {"role": "assistant", "content": "reply"}

    def test_assistant_tool_calls(self) -> None:
        tcs = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "echo", "arguments": '{"x":1}'},
            }
        ]
        m = Message.assistant_tool_calls(tcs)
        assert m["role"] == ROLE_ASSISTANT
        assert m["content"] is None
        assert m["tool_calls"] == tcs

    def test_assistant_tool_calls_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            Message.assistant_tool_calls([])

    def test_tool_result(self) -> None:
        m = Message.tool_result("call_1", "out")
        assert m == {"role": "tool", "tool_call_id": "call_1", "content": "out"}
        assert m.is_tool_message()

    def test_tool_result_rejects_empty_id(self) -> None:
        with pytest.raises(ValueError):
            Message.tool_result("", "out")

    def test_is_tool_message(self) -> None:
        assert Message.tool_result("c1", "x").is_tool_message()
        assert not Message.user("x").is_tool_message()

    def test_is_assistant_with_tool_calls(self) -> None:
        assert Message.assistant_tool_calls(
            [{"id": "c1", "type": "function", "function": {"name": "f"}}]
        ).is_assistant_with_tool_calls()
        assert not Message.assistant("plain").is_assistant_with_tool_calls()

    def test_dict_literal_validates_role(self) -> None:
        with pytest.raises(ValueError):
            Message({"role": "bogus", "content": "x"})

    def test_normalize_messages(self) -> None:
        out = normalize_messages(
            [Message.user("a"), {"role": "user", "content": "b"}]
        )
        assert len(out) == 2
        assert all(isinstance(m, dict) for m in out)
        assert out[0]["content"] == "a"
        assert out[1]["content"] == "b"

    def test_valid_roles(self) -> None:
        assert ROLE_SYSTEM in ("system", "user", "assistant", "tool") or True
        assert {ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT, ROLE_TOOL} == set(
            ["system", "user", "assistant", "tool"]
        )


# ---- StreamChunk serialization ----------------------------------------


class TestStreamChunk:
    def test_default_construction(self) -> None:
        c = StreamChunk(type=CHUNK_DONE)
        assert c.type == CHUNK_DONE
        assert c.delta == ""
        assert c.tool_call_id == ""

    def test_content_chunk(self) -> None:
        c = StreamChunk.content("hello ")
        assert c.type == CHUNK_CONTENT
        assert c.delta == "hello "
        assert c.is_content()
        assert not c.is_terminal()

    def test_tool_call_chunk(self) -> None:
        c = StreamChunk.tool_call("c1", "echo", {"x": 1}, index=0)
        assert c.type == CHUNK_TOOL_CALL
        assert c.tool_call_id == "c1"
        assert c.name == "echo"
        assert c.arguments == {"x": 1}
        assert c.index == 0

    def test_tool_call_chunk_string_args(self) -> None:
        c = StreamChunk.tool_call("c1", "echo", '{"x":1}')
        assert c.arguments == {"x": 1}

    def test_tool_call_chunk_invalid_json_args(self) -> None:
        c = StreamChunk.tool_call("c1", "echo", "not json")
        assert c.arguments == {"_raw": "not json"}

    def test_done_chunk(self) -> None:
        c = StreamChunk.done()
        assert c.is_done()
        assert c.is_terminal()
        assert c.finish_reason == FINISH_STOP

    def test_error_chunk(self) -> None:
        c = StreamChunk.error("boom")
        assert c.is_error()
        assert c.is_terminal()
        assert c.error == "boom"

    def test_legacy_id_kwarg_translated(self) -> None:
        # 旧 producer 用 `id=` 直接构造：必须能被接受
        c = StreamChunk(type=CHUNK_TOOL_CALL, id="call_legacy", name="f", arguments={})
        assert c.tool_call_id == "call_legacy"

    def test_legacy_id_overrides_when_both_given(self) -> None:
        # `id` 仅在 `tool_call_id` 缺省时翻译；显式 `tool_call_id` 优先
        c = StreamChunk(type=CHUNK_TOOL_CALL, id="x", tool_call_id="y")
        assert c.tool_call_id == "y"

    def test_unknown_kwarg_rejected(self) -> None:
        with pytest.raises(TypeError):
            StreamChunk(type=CHUNK_DONE, not_a_field=1)

    def test_positional_rejected(self) -> None:
        with pytest.raises(TypeError):
            StreamChunk(CHUNK_DONE)

    def test_to_dict_content(self) -> None:
        d = StreamChunk(type=CHUNK_CONTENT, delta="hi").to_dict()
        assert d == {"type": "content", "delta": "hi"}

    def test_to_dict_tool_call_has_both_ids(self) -> None:
        c = StreamChunk(type=CHUNK_TOOL_CALL, tool_call_id="c1", name="f", arguments={"a": 1})
        d = c.to_dict()
        # 两个 key 都存在（向后兼容老 consumer `chunk["id"]`）
        assert d["tool_call_id"] == "c1"
        assert d["id"] == "c1"
        assert d["name"] == "f"
        assert d["arguments"] == {"a": 1}

    def test_to_dict_done_minimal(self) -> None:
        d = StreamChunk.done().to_dict()
        assert d == {"type": "done", "finish_reason": FINISH_STOP}

    def test_to_dict_error(self) -> None:
        d = StreamChunk.error("x").to_dict()
        assert d == {"type": "error", "error": "x"}

    def test_from_dict_accepts_tool_call_id(self) -> None:
        c = StreamChunk.from_dict(
            {
                "type": "tool_call",
                "tool_call_id": "c1",
                "name": "echo",
                "arguments": {"x": 1},
                "index": 2,
            }
        )
        assert c.tool_call_id == "c1"
        assert c.name == "echo"
        assert c.arguments == {"x": 1}
        assert c.index == 2

    def test_from_dict_accepts_legacy_id(self) -> None:
        c = StreamChunk.from_dict({"type": "tool_call", "id": "c1", "name": "f"})
        assert c.tool_call_id == "c1"

    def test_from_dict_roundtrip(self) -> None:
        original = StreamChunk(
            type=CHUNK_CONTENT,
            delta="hello world",
            index=0,
            usage={"prompt_tokens": 5},
        )
        c = StreamChunk.from_dict(original.to_dict())
        assert c.type == original.type
        assert c.delta == original.delta
        assert c.index == original.index
        assert c.usage == original.usage


# ---- LLMService dispatch ---------------------------------------------


def _make_ctx() -> Context:
    return Context()


class TestLLMServiceRegister:
    def test_register_provider(self) -> None:
        svc = LLMService(_make_ctx())
        p = MockProvider(name="alpha")
        svc.register_provider(p)
        assert "alpha" in svc.list_providers()

    def test_register_duplicate_raises(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="alpha"))
        with pytest.raises(ValueError):
            svc.register_provider(MockProvider(name="alpha"))

    def test_register_invalid_provider_raises(self) -> None:
        svc = LLMService(_make_ctx())

        class Bad:
            name = "bad"
            # no `stream` method

        with pytest.raises(TypeError):
            svc.register_provider(Bad())

    def test_register_non_string_name_raises(self) -> None:
        svc = LLMService(_make_ctx())

        class Weird:
            name = ""
            async def stream(self, **kwargs):  # pragma: no cover - never called
                yield StreamChunk(type=CHUNK_DONE)

        with pytest.raises(ValueError):
            svc.register_provider(Weird())

    def test_register_with_model_prefix(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="alpha"), model_prefix="custom-")
        # prefix 列表包含 custom-
        prefixes = [p for p, _ in svc.list_prefixes()]
        assert "custom-" in prefixes

    def test_register_marks_default(self) -> None:
        svc = LLMService(_make_ctx())
        # `default=True` 必须显式设置 —— 不存在自动 fallback
        svc.register_provider(MockProvider(name="first"), default=True)
        assert svc.default_provider == "first"
        svc.register_provider(MockProvider(name="second"), default=True)
        assert svc.default_provider == "second"

    def test_register_without_default_does_not_set_default(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="first"))
        assert svc.default_provider is None

    def test_unregister_provider(self) -> None:
        svc = LLMService(_make_ctx())
        p = MockProvider(name="alpha")
        svc.register_provider(p)
        removed = svc.unregister_provider("alpha")
        assert removed is p
        assert "alpha" not in svc.list_providers()

    def test_unregister_nonexistent(self) -> None:
        svc = LLMService(_make_ctx())
        assert svc.unregister_provider("missing") is None


class TestLLMServiceDispatch:
    def test_provider_for_by_prefix(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="deepseek"))
        assert svc.provider_for("deepseek-chat").name == "deepseek"
        assert svc.provider_for("deepseek-coder").name == "deepseek"
        assert svc.provider_for("deepseek-reasoner").name == "deepseek"

    def test_provider_for_longest_prefix_wins(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="deepseek"))
        svc.register_provider(
            MockProvider(name="deepseek_reasoner"),
            model_prefix="deepseek-reasoner",
        )
        assert svc.provider_for("deepseek-chat").name == "deepseek"
        assert svc.provider_for("deepseek-reasoner").name == "deepseek_reasoner"

    def test_provider_for_falls_back_to_default(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="deepseek"))
        svc.register_provider(MockProvider(name="openai"), default=True)
        assert svc.provider_for("gpt-4").name == "openai"

    def test_provider_for_no_match_no_default_raises(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="deepseek"))
        with pytest.raises(LLMNoAdapterError):
            svc.provider_for("gpt-4")

    def test_provider_for_no_providers_raises(self) -> None:
        svc = LLMService(_make_ctx())
        with pytest.raises(LLMNoAdapterError):
            svc.provider_for("anything")


class TestLLMServiceStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self) -> None:
        svc = LLMService(_make_ctx())
        chunks_in = [
            StreamChunk.content("Hello, "),
            StreamChunk.content("world!"),
            StreamChunk.done(),
        ]
        p = MockProvider(name="deepseek", chunks=chunks_in)
        svc.register_provider(p)
        out = []
        async for c in svc.stream(
            model="deepseek-chat",
            messages=[Message.user("hi")],
            tools=None,
            temperature=0.5,
            max_tokens=64,
        ):
            out.append(c)
        assert [c.type for c in out] == [CHUNK_CONTENT, CHUNK_CONTENT, CHUNK_DONE]
        assert "".join(c.delta for c in out if c.is_content()) == "Hello, world!"
        # Provider 收到正确的 kwargs
        assert p.last_kwargs["model"] == "deepseek-chat"
        assert p.last_kwargs["temperature"] == 0.5
        assert p.last_kwargs["max_tokens"] == 64
        assert p.calls == 1

    @pytest.mark.asyncio
    async def test_stream_propagates_provider_exception(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(MockProvider(name="x", raise_exc=LLMAuthError("nope")))
        with pytest.raises(LLMAuthError):
            async for _ in svc.stream(model="x-chat", messages=[]):
                pass

    @pytest.mark.asyncio
    async def test_complete_accumulates_content(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(
            MockProvider(
                name="deepseek",
                chunks=[
                    StreamChunk.content("foo "),
                    StreamChunk.content("bar"),
                    StreamChunk.done(),
                ],
            )
        )
        text = await svc.complete(model="deepseek-chat", messages=[Message.user("hi")])
        assert text == "foo bar"

    @pytest.mark.asyncio
    async def test_complete_empty_on_tool_only_turn(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(
            MockProvider(
                name="deepseek",
                chunks=[
                    StreamChunk.tool_call("c1", "echo", {"x": 1}),
                    StreamChunk.done(),
                ],
            )
        )
        text = await svc.complete(model="deepseek-chat", messages=[])
        assert text == ""

    @pytest.mark.asyncio
    async def test_complete_raises_on_error_chunk(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(
            MockProvider(
                name="deepseek",
                chunks=[StreamChunk.error("upstream died"), StreamChunk.done()],
            )
        )
        with pytest.raises(LLMError):
            await svc.complete(model="deepseek-chat", messages=[])

    @pytest.mark.asyncio
    async def test_complete_response_collects_tool_calls(self) -> None:
        svc = LLMService(_make_ctx())
        svc.register_provider(
            MockProvider(
                name="deepseek",
                chunks=[
                    StreamChunk.content("calling..."),
                    StreamChunk.tool_call("c1", "echo", {"x": 1}, index=0),
                    StreamChunk.tool_call("c2", "ping", {}, index=1),
                    StreamChunk.done(finish_reason="tool_calls"),
                ],
            )
        )
        resp = await svc.complete_response(model="deepseek-chat", messages=[])
        assert resp.content == "calling..."
        assert resp.finish_reason == "tool_calls"
        assert [t["id"] for t in resp.tool_calls] == ["c1", "c2"]
        assert resp.tool_calls[0]["function"]["name"] == "echo"
        assert resp.model == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_embed_raises_not_implemented(self) -> None:
        svc = LLMService(_make_ctx())
        with pytest.raises(NotImplementedError):
            await svc.embed(model="x", input="hi")


# ---- LLMError hierarchy ----------------------------------------------


class TestLLMErrors:
    def test_base_error_has_code(self) -> None:
        e = LLMError("boom")
        assert e.code == CODE_UNKNOWN
        assert e.message == "boom"
        assert isinstance(e, Exception)

    def test_subclass_codes(self) -> None:
        assert LLMAuthError().code == CODE_AUTH
        assert LLMRateLimitError().code == CODE_RATE_LIMIT
        assert LLMContextLengthError().code == CODE_CONTEXT_LENGTH
        assert LLMNetworkError().code == CODE_NETWORK
        assert LLMNoAdapterError().code == CODE_NO_ADAPTER
        assert LLMInvalidRequestError().code == "INVALID_REQUEST"
        assert LLMAbortedError().code == CODE_ABORTED

    def test_is_subclass_of_base(self) -> None:
        assert issubclass(LLMAuthError, LLMError)
        assert issubclass(LLMRateLimitError, LLMError)
        assert issubclass(LLMContextLengthError, LLMError)
        assert issubclass(LLMNetworkError, LLMError)
        assert issubclass(LLMNoAdapterError, LLMError)

    def test_rate_limit_retry_after(self) -> None:
        e = LLMRateLimitError("slow down", retry_after_ms=1500.0)
        assert e.code == CODE_RATE_LIMIT
        assert e.retry_after_ms == 1500.0
        assert e.status == 429

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValueError):
            LLMAuthError("x", status=42)
        with pytest.raises(ValueError):
            LLMAuthError("x", status=700)

    def test_cause_chained(self) -> None:
        original = RuntimeError("socket reset")
        wrapped = LLMNetworkError("connect failed", cause=original)
        assert wrapped.cause is original
        assert wrapped.__cause__ is original

    def test_to_dict_excludes_cause(self) -> None:
        e = LLMAuthError("nope", status=401, request_id="req-1")
        d = e.to_dict()
        assert d["code"] == CODE_AUTH
        assert d["type"] == "LLMAuthError"
        assert d["status"] == 401
        assert d["request_id"] == "req-1"
        assert "cause" not in d  # 避免把原始异常塞进序列化

    def test_llm_response_to_from_dict(self) -> None:
        r = LLMResponse(
            content="hi",
            tool_calls=[{"id": "c1", "function": {"name": "f"}}],
            usage={"prompt_tokens": 5, "completion_tokens": 3},
            model="deepseek-chat",
            finish_reason="stop",
        )
        d = r.to_dict()
        assert d["content"] == "hi"
        assert d["tool_calls"][0]["id"] == "c1"
        r2 = LLMResponse.from_dict(d)
        assert r2.content == r.content
        assert r2.tool_calls == r.tool_calls
        assert r2.usage == r.usage
        assert r2.finish_reason == "stop"


# ---- RetryPolicy ------------------------------------------------------


class TestRetryPolicy:
    def test_invalid_max_retries(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_retries=-1)

    def test_invalid_backoff(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(backoff_base=0)
        with pytest.raises(ValueError):
            RetryPolicy(backoff_base=10, max_backoff=5)
        with pytest.raises(ValueError):
            RetryPolicy(jitter_ratio=2)

    @pytest.mark.asyncio
    async def test_first_success_no_retry(self) -> None:
        calls = []
        policy = RetryPolicy()

        async def fn() -> str:
            calls.append(1)
            return "ok"

        result = await policy.execute(fn)
        assert result == "ok"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_eventual_success(self) -> None:
        calls = [0]
        policy = RetryPolicy(
            max_retries=3,
            backoff_base=0.01,
            max_backoff=0.05,
            jitter_ratio=0,
        )

        async def fn() -> str:
            calls[0] += 1
            if calls[0] < 3:
                raise TimeoutError("transient")
            return "ok"

        result = await policy.execute(fn)
        assert result == "ok"
        assert calls[0] == 3

    @pytest.mark.asyncio
    async def test_exhausted_raises_last(self) -> None:
        calls = [0]
        policy = RetryPolicy(
            max_retries=2,
            backoff_base=0.01,
            max_backoff=0.05,
            jitter_ratio=0,
        )

        async def fn() -> str:
            calls[0] += 1
            raise TimeoutError(f"attempt {calls[0]}")

        with pytest.raises(TimeoutError) as exc_info:
            await policy.execute(fn)
        assert calls[0] == 3  # initial + 2 retries
        assert "attempt 3" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self) -> None:
        calls = [0]
        policy = RetryPolicy(max_retries=3, backoff_base=0.01)

        async def fn() -> str:
            calls[0] += 1
            raise LLMContextLengthError("too big")

        with pytest.raises(LLMContextLengthError):
            await policy.execute(fn)
        assert calls[0] == 1  # 永不重试 context overflow

    @pytest.mark.asyncio
    async def test_non_retryable_unrelated_exception(self) -> None:
        calls = [0]
        policy = RetryPolicy(max_retries=3, backoff_base=0.01)

        async def fn() -> str:
            calls[0] += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await policy.execute(fn)
        assert calls[0] == 1

    @pytest.mark.asyncio
    async def test_rate_limit_is_retryable(self) -> None:
        calls = [0]
        policy = RetryPolicy(
            max_retries=2,
            backoff_base=0.01,
            max_backoff=0.05,
            jitter_ratio=0,
        )

        async def fn() -> str:
            calls[0] += 1
            if calls[0] < 2:
                raise LLMRateLimitError("slow", retry_after_ms=10)
            return "ok"

        result = await policy.execute(fn)
        assert result == "ok"
        assert calls[0] == 2

    @pytest.mark.asyncio
    async def test_on_retry_hook_called(self) -> None:
        calls = []
        policy = RetryPolicy(
            max_retries=2,
            backoff_base=0.01,
            max_backoff=0.05,
            jitter_ratio=0,
            on_retry=lambda attempt, exc, delay: calls.append((attempt, type(exc).__name__, delay)),
        )

        async def fn() -> str:
            raise TimeoutError("x")

        with pytest.raises(TimeoutError):
            await policy.execute(fn)
        assert len(calls) == 2
        assert all(c[1] == "TimeoutError" for c in calls)
        assert calls[0][0] == 1  # attempt is 1-indexed
        assert calls[1][0] == 2

    @pytest.mark.asyncio
    async def test_on_retry_hook_exception_does_not_break_retry(self) -> None:
        calls = [0]

        def bad_hook(attempt, exc, delay):
            raise RuntimeError("hook bug")

        policy = RetryPolicy(
            max_retries=2,
            backoff_base=0.01,
            max_backoff=0.05,
            jitter_ratio=0,
            on_retry=bad_hook,
        )

        async def fn() -> str:
            calls[0] += 1
            if calls[0] < 3:
                raise TimeoutError("x")
            return "ok"

        result = await policy.execute(fn)
        assert result == "ok"
        assert calls[0] == 3

    def test_compute_backoff_exponential(self) -> None:
        policy = RetryPolicy(
            backoff_base=1.0,
            max_backoff=100.0,
            jitter_ratio=0,
        )
        assert policy.compute_backoff(1) == 1.0
        assert policy.compute_backoff(2) == 2.0
        assert policy.compute_backoff(3) == 4.0
        assert policy.compute_backoff(4) == 8.0

    def test_compute_backoff_capped(self) -> None:
        policy = RetryPolicy(
            backoff_base=1.0,
            max_backoff=5.0,
            jitter_ratio=0,
        )
        assert policy.compute_backoff(10) == 5.0

    def test_compute_backoff_attempt_zero_is_zero(self) -> None:
        policy = RetryPolicy()
        assert policy.compute_backoff(0) == 0.0

    def test_compute_backoff_jitter_within_range(self) -> None:
        policy = RetryPolicy(
            backoff_base=1.0,
            max_backoff=10.0,
            jitter_ratio=0.5,
        )
        for _ in range(50):
            delay = policy.compute_backoff(3)  # base 4.0
            assert 2.0 <= delay <= 6.0

    def test_default_retryable_includes_network_and_rate_limit(self) -> None:
        assert TimeoutError in DEFAULT_RETRYABLE
        assert ConnectionError in DEFAULT_RETRYABLE
        assert LLMNetworkError in DEFAULT_RETRYABLE
        assert LLMRateLimitError in DEFAULT_RETRYABLE


# ---- LLMProvider protocol (structural typing) -------------------------


class TestLLMProviderProtocol:
    def test_mock_provider_satisfies_protocol(self) -> None:
        assert isinstance(MockProvider(), LLMProvider)

    def test_partial_provider_does_not_satisfy(self) -> None:
        class Incomplete:
            name = "x"
            # 缺 stream

        assert not isinstance(Incomplete(), LLMProvider)


# ---- plugin mounting --------------------------------------------------


class TestPlugin:
    @pytest.mark.asyncio
    async def test_plugin_registers_service(self) -> None:
        from taiyi_llm.plugin import setup

        ctx = Context()
        await ctx.plugin(setup, {})
        llm = ctx.inject("llm")
        assert isinstance(llm, LLMService)
        assert llm.list_providers() == []