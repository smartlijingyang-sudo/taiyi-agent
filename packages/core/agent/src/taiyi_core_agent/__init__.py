"""taiyi-core-agent — Agent 接口 + 注册表 + agent/* 事件。

提供：
  - Agent（agent 定义）
  - AgentRegistry（agent 注册表）
  - EVENT_PRE_STEP / EVENT_REQUEST / EVENT_TURN_STOPPING（事件名）
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class Agent:
    """Agent 定义。

    字段：
      - name: agent 名
      - model: 模型名（如 "deepseek-chat"）
      - temperature: 温度
      - max_steps: 单 turn 最大步数
      - system_prompt_override: 系统提示词覆盖
      - tools: 限定工具列表（None = 全部）
      - metadata: 元数据
    """

    name: str = "default"
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_steps: int = 8
    system_prompt_override: str | None = None
    tools: list[str] | None = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class AgentRegistry:
    """Agent 注册表。

    用法：
      registry = AgentRegistry()
      registry.register(Agent(name="coder", model="deepseek-coder"))
      agent = registry.get("coder")
      default = registry.default()
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.name] = agent

    def unregister(self, name: str) -> Agent | None:
        return self._agents.pop(name, None)

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def default(self) -> Agent:
        """返回默认 agent（如不存在则创建 "default"）。"""
        if "default" not in self._agents:
            self._agents["default"] = Agent(name="default")
        return self._agents["default"]

    def list(self) -> list[Agent]:
        return list(self._agents.values())

    def names(self) -> list[str]:
        return list(self._agents.keys())


# ---------------------------------------------------------------------------
# 事件名（agent/*）
# ---------------------------------------------------------------------------

EVENT_PRE_STEP = "agent/pre-step"
EVENT_REQUEST = "agent/request"
EVENT_TURN_STOPPING = "agent/turn-stopping"


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "Agent",
    "AgentRegistry",
    "EVENT_PRE_STEP",
    "EVENT_REQUEST",
    "EVENT_TURN_STOPPING",
]
