"""taiyi-core-tools — 工具注册 + 执行管线。

提供：
  - Tool（工具定义）
  - ToolCall（模型发起的工具调用）
  - ToolResult（工具执行结果）
  - ToolsService（工具注册表）
  - @tool 装饰器
  - tools_execute（执行管线，走 cordis waterfall）
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

# ---------------------------------------------------------------------------
# 事件名
# ---------------------------------------------------------------------------

EVENT_PRE_EXECUTE = "tools/pre-execute"
EVENT_EXECUTE = "tools/execute"
EVENT_POST_EXECUTE = "tools/post-execute"


# ---------------------------------------------------------------------------
# Tool 类型
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    """工具定义。

    字段：
      - name: 工具名
      - description: 描述
      - parameters: JSON Schema（参数定义）
      - handler: async callable
    """

    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[Any]]

    def schema(self) -> dict:
        """返回 OpenAI function tool schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    """模型发起的工具调用。

    字段：
      - tool_call_id: 调用 ID
      - name: 工具名
      - arguments: 参数（dict）
    """

    tool_call_id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    """工具执行结果。

    字段：
      - tool_call_id: 对应调用 ID
      - name: 工具名
      - content: 结果内容
      - is_error: 是否错误
    """

    tool_call_id: str
    name: str
    content: Any
    is_error: bool = False


# ---------------------------------------------------------------------------
# ToolsService
# ---------------------------------------------------------------------------


class ToolsService:
    """工具注册表。

    用法：
      tools = ToolsService()
      tools.register(Tool("echo", "...", {...}, handler))
      tool = tools.get("echo")
      schemas = tools.schemas()  # OpenAI function schemas
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> Tool | None:
        return self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        """返回 OpenAI function tool schemas。"""
        return [t.schema() for t in self._tools.values()]


# ---------------------------------------------------------------------------
# @tool 装饰器
# ---------------------------------------------------------------------------


def tool(
    name: str = "",
    description: str = "",
    parameters: dict | None = None,
) -> Callable:
    """装饰器：标记 async 函数为 tool。

    用法：
      @tool(name="echo", description="回显输入", parameters={"type": "object", ...})
      async def echo(args: dict) -> dict:
          return {"echo": args}
    """

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable:
        t = Tool(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip(),
            parameters=parameters or {"type": "object", "properties": {}},
            handler=fn,
        )
        fn.__taiyi_tool__ = t  # type: ignore[attr-defined]
        return fn

    return deco


# ---------------------------------------------------------------------------
# 执行管线
# ---------------------------------------------------------------------------


async def tools_execute(ctx, call: ToolCall) -> ToolResult:
    """执行工具调用（走 cordis waterfall）。

    流程：
      1. tools/pre-execute (waterfall) — 可拦截 / 修改 call
      2. tools/execute (waterfall) — 实际执行
      3. tools/post-execute (waterfall) — 后处理

    默认行为（无监听器）：查找 handler，执行，返回结果。
    """
    from cordis import Context as Ctx

    # 1. pre-execute (waterfall)
    try:
        result = await ctx.emit(EVENT_PRE_EXECUTE, call)
        if isinstance(result, ToolCall):
            call = result
    except KeyError:
        pass  # 无监听器

    # 2. execute (waterfall)
    tools: ToolsService = ctx.inject("tools")
    t = tools.get(call.name)
    if t is None:
        return ToolResult(
            tool_call_id=call.tool_call_id,
            name=call.name,
            content=f"tool {call.name!r} not found",
            is_error=True,
        )

    try:
        # 调用 handler
        result = t.handler(call.arguments)
        if inspect.iscoroutine(result):
            result = await result
        # 转为字符串
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return ToolResult(
            tool_call_id=call.tool_call_id,
            name=call.name,
            content=f"{type(e).__name__}: {e}",
            is_error=True,
        )

    tool_result = ToolResult(
        tool_call_id=call.tool_call_id,
        name=call.name,
        content=content,
    )

    # 3. post-execute (waterfall)
    try:
        result = await ctx.emit(EVENT_POST_EXECUTE, tool_result)
        if isinstance(result, ToolResult):
            tool_result = result
    except KeyError:
        pass  # 无监听器

    return tool_result


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "Tool",
    "ToolCall",
    "ToolResult",
    "ToolsService",
    "tool",
    "tools_execute",
    "EVENT_PRE_EXECUTE",
    "EVENT_EXECUTE",
    "EVENT_POST_EXECUTE",
]
