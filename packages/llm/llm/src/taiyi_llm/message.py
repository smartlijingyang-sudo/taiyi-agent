"""Message — provider-neutral conversation message vocabulary.

对齐 deepseek-harness dsh-llm/message.ts：Message 是 dict-shaped 值，role 是
provider-neutral 字符串（system | user | assistant | tool）。辅助 tool 调用
的 assistant 消息携带 `tool_calls`，tool 结果消息携带 `tool_call_id`。

本包不引入 Pydantic / dataclass，只用 plain dict 子类，方便下游 agent loop
直接 `msg.get("role")`、`msg["tool_call_id"]` 这样使用。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Canonical role vocabulary。Merged from dsh-llm/message.ts：dsh 只暴露
# system | user | assistant；taiyi 在 MVP 增加 `tool`（用于 OpenAI 兼容的
# tool 结果消息）。
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"

VALID_ROLES: tuple[str, ...] = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT, ROLE_TOOL)


class Message(dict):
    """Provider-neutral conversation message。

    底层就是 dict；继承 dict 让 consumer 直接用 `msg["role"]` / `msg.get("tool_call_id")` /
    `json.dumps` 等 dict 接口，无需先 `.to_dict()`。构造走工厂方法（见下方 static
    methods），不要直接 `Message(role=...)` —— 工厂会帮你选正确的字段集合。
    """

    # ---- factories ------------------------------------------------------

    @staticmethod
    def system(text: str) -> Message:
        """System instruction message; 出现在 messages 列表最前。"""
        return Message({"role": ROLE_SYSTEM, "content": text})

    @staticmethod
    def user(text: str | list[Any]) -> Message:
        """User turn；`text` 可为字符串或 content block 列表。"""
        return Message({"role": ROLE_USER, "content": text})

    @staticmethod
    def assistant(text: str | None) -> Message:
        """纯文本 assistant reply；如要携带 tool_calls 请用 `assistant_tool_calls`。"""
        return Message({"role": ROLE_ASSISTANT, "content": text})

    @staticmethod
    def assistant_tool_calls(
        tool_calls: list[dict],
        content: str | None = None,
    ) -> Message:
        """Assistant turn 携带 tool calls。

        每项形如 `{"id": "call_xxx", "type": "function",
        "function": {"name": "...", "arguments": "...json..."}}`。
        `content` 通常为 None（OpenAI 规范）；agent loop 会按 dsh-llm 的 tool
        调用协议把这些 tool_call 块下发到 tools pipeline。
        """
        if not tool_calls:
            raise ValueError("assistant_tool_calls requires at least one tool_call")
        return Message(
            {
                "role": ROLE_ASSISTANT,
                "content": content,
                "tool_calls": list(tool_calls),
            }
        )

    @staticmethod
    def tool_result(tool_call_id: str, text: str) -> Message:
        """Tool execution result，对应之前 assistant turn 中的某个 tool_call_id。

        把结果以 `role: "tool"` 形式塞回 messages，模型在下一轮可看到。
        """
        if not tool_call_id:
            raise ValueError("tool_result requires a non-empty tool_call_id")
        return Message(
            {
                "role": ROLE_TOOL,
                "tool_call_id": tool_call_id,
                "content": text,
            }
        )

    # ---- introspection --------------------------------------------------

    def is_tool_message(self) -> bool:
        return self.get("role") == ROLE_TOOL

    def is_assistant_with_tool_calls(self) -> bool:
        return self.get("role") == ROLE_ASSISTANT and bool(self.get("tool_calls"))

    def has_content(self) -> bool:
        c = self.get("content")
        if c is None:
            return False
        if isinstance(c, str):
            return bool(c)
        if isinstance(c, (list, tuple)):
            return len(c) > 0
        return True

    # ---- constructors kept internal ----------------------------------

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # 兼容 `Message({"role": ..., ...})` dict literal 风格；其他构造都走工厂。
        super().__init__(*args, **kwargs)
        role = self.get("role")
        if role is not None and role not in VALID_ROLES:
            raise ValueError(
                f"unknown role {role!r}; expected one of {VALID_ROLES}"
            )

    def __repr__(self) -> str:
        return f"Message({dict.__repr__(self)})"


def normalize_messages(messages: Iterable[Any]) -> list[dict]:
    """把任意 messages iterable 归一为 list[dict]，保留 Message 子类身份。

    agent loop 在拼装 prompt 时调用：上游可能是 Message 也可能是 dict literal，
    这里统一成 list[dict]，下游按 dict 操作。
    """
    return [m if isinstance(m, dict) else dict(m) for m in messages]


__all__ = [
    "Message",
    "ROLE_SYSTEM",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_TOOL",
    "VALID_ROLES",
    "normalize_messages",
]