"""taiyi-core-agent-loop — 默认 driver（turn/step 循环）。

提供：
  - AgentLoopService（驱动 turn/step 循环）
  - run_turn() 便利函数

turn/step 事件流（对齐 dsh）：
  turn/start
    claim input + queued message
    assemble prompt + tools
    -> agent/pre-step (waterfall)
    step/start
      -> agent/request -> llm/stream -> assistant/chunk* -> assistant/message
      -> tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
    step/end
  turn/end
"""
from __future__ import annotations

import asyncio
import json
import random
import string
from typing import AsyncIterator

from cordis import Context, Service, plugin

from taiyi_core_sessions import Session, SessionsService, SessionEvent, EventType
from taiyi_core_system_prompt import SystemPromptService
from taiyi_core_tools import ToolsService, ToolCall, ToolResult, tools_execute
from taiyi_core_agent import Agent, AgentRegistry, EVENT_PRE_STEP, EVENT_REQUEST
from taiyi_llm import LLMService, StreamChunk, CHUNK_CONTENT, CHUNK_TOOL_CALL, CHUNK_DONE


def _random_id(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


class AgentLoopService(Service):
    """Agent loop 服务。

    用法：
      loop_svc = AgentLoopService(ctx)
      async for ev in loop_svc.run_turn(session, "hi"):
          ...
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)

    async def run_turn(
        self,
        session: Session,
        user_input: str,
        *,
        agent_name: str = "default",
    ) -> AsyncIterator[SessionEvent]:
        """运行一个 turn，yield SessionEvent。

        流程：
          1. turn/start
          2. user/message
          3. agent/pre-step (waterfall)
          4. step 循环：
             - step/start
             - llm.stream() → assistant/chunk* → assistant/message
             - tool/call* → tools_execute → tool/result*
             - step/end
          5. agent/turn-stopping (serial)
          6. turn/end
        """
        ctx = self.ctx
        sessions: SessionsService = ctx.inject("sessions")
        system_prompt: SystemPromptService = ctx.inject("system_prompt")
        tools: ToolsService = ctx.inject("tools")
        agents: AgentRegistry = ctx.inject("agents")
        llm: LLMService = ctx.inject("llm")

        agent = agents.get(agent_name) or agents.default()

        # 1. turn/start
        yield session.append(EventType.TURN_START, {"session_id": session.id})

        # 2. user/message
        yield session.append(EventType.USER_MESSAGE, {"content": user_input})

        # 3. agent/pre-step (waterfall)
        system = system_prompt.assemble()
        messages = [{"role": "system", "content": system}] + session.messages()
        pre_step_payload = {
            "agent": agent,
            "messages": messages,
            "session": session,
        }

        try:
            result = await ctx.emit(EVENT_PRE_STEP, pre_step_payload)
            if isinstance(result, dict):
                messages = result.get("messages", messages)
        except KeyError:
            pass  # 无监听器

        # 4. step 循环
        step_count = 0
        while step_count < agent.max_steps:
            step_count += 1

            # step/start
            yield session.append(EventType.STEP_START, {"step": step_count})

            # llm.stream()
            assistant_text = ""
            tool_calls: list[ToolCall] = []

            try:
                async for chunk in llm.stream(
                    model=agent.model,
                    messages=messages,
                    tools=tools.schemas() if tools.schemas() else None,
                    temperature=agent.temperature,
                ):
                    if chunk.type == CHUNK_CONTENT:
                        assistant_text += chunk.delta
                        yield session.append(
                            EventType.ASSISTANT_CHUNK,
                            {"delta": chunk.delta, "session_id": session.id},
                        )
                    elif chunk.type == CHUNK_TOOL_CALL:
                        tool_calls.append(
                            ToolCall(
                                tool_call_id=chunk.tool_call_id or _random_id(),
                                name=chunk.name,
                                arguments=chunk.arguments,
                            )
                        )
            except Exception as e:
                yield session.append(
                    EventType.STEP_END,
                    {"step": step_count, "error": str(e)},
                )
                break

            # assistant/message
            if assistant_text:
                yield session.append(
                    EventType.ASSISTANT_MESSAGE,
                    {"content": assistant_text},
                )

            # 无 tool calls → 本 step 完成
            if not tool_calls:
                yield session.append(EventType.STEP_END, {"step": step_count})
                break

            # 执行 tool calls
            for call in tool_calls:
                yield session.append(
                    EventType.TOOL_CALL,
                    {
                        "tool_call_id": call.tool_call_id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                )

                result = await tools_execute(ctx, call)

                yield session.append(
                    EventType.TOOL_RESULT,
                    {
                        "tool_call_id": result.tool_call_id,
                        "name": result.name,
                        "content": result.content,
                        "is_error": result.is_error,
                    },
                )

                # 注入 tool result 到下轮 messages
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "content": str(result.content),
                    }
                )

            yield session.append(EventType.STEP_END, {"step": step_count})

        # 5. agent/turn-stopping (serial)
        try:
            await ctx.emit("agent/turn-stopping", {"agent": agent, "session": session})
        except KeyError:
            pass

        # 6. turn/end
        yield session.append(EventType.TURN_END, {"steps": step_count, "session_id": session.id})

    async def dispose(self) -> None:
        pass


async def run_turn(ctx: Context, session_id: str, user_input: str) -> AsyncIterator[SessionEvent]:
    """便利函数：从 ctx 拿 sessions + agent_loop 起一个 turn。"""
    sessions: SessionsService = ctx.inject("sessions")
    loop_svc: AgentLoopService = ctx.inject("agent_loop")
    session = sessions.get(session_id) or sessions.create(session_id)
    async for ev in loop_svc.run_turn(session, user_input):
        yield ev


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 AgentLoopService。"""
    svc = AgentLoopService(ctx)
    ctx.provide("agent_loop", svc)
    ctx.effect(svc, name="agent_loop:service")
