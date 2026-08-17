"""taiyi-core-system-prompt — 系统提示词装配。

提供：
  - PromptSection（带优先级的提示片段）
  - SystemPromptService（section 注册 + 装配）
  - DEFAULT_SECTIONS（默认提示词片段）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptSection:
    """提示词片段。

    字段：
      - name: 唯一标识
      - content: 提示词文本
      - priority: 优先级（越高越靠前）
    """

    name: str
    content: str
    priority: int = 0


DEFAULT_SECTIONS: list[PromptSection] = [
    PromptSection(
        name="identity",
        content="你是 太一 (Taiyi)，由 DeepSeek 训练的大型语言助手。",
        priority=100,
    ),
    PromptSection(
        name="style",
        content="回答应当简洁、准确、结构化；遇到不确定时主动说明。",
        priority=80,
    ),
    PromptSection(
        name="capabilities",
        content="你可以：进行多轮对话、解释代码、撰写文案、推理数学与逻辑。",
        priority=60,
    ),
]


class SystemPromptService:
    """系统提示词服务。

    用法：
      svc = SystemPromptService()
      svc.add(PromptSection("custom", "额外指令", priority=50))
      prompt = svc.assemble()
    """

    def __init__(self, base_sections: list[PromptSection] | None = None) -> None:
        self._sections: dict[str, PromptSection] = {}
        for section in (base_sections or DEFAULT_SECTIONS):
            self._sections[section.name] = section

    def add(self, section: PromptSection) -> None:
        self._sections[section.name] = section

    def remove(self, name: str) -> None:
        self._sections.pop(name, None)

    def get(self, name: str) -> PromptSection | None:
        return self._sections.get(name)

    def list(self) -> list[PromptSection]:
        return sorted(self._sections.values(), key=lambda s: -s.priority)

    def replace(self, name: str, content: str) -> None:
        """替换已有 section 的内容。"""
        if name in self._sections:
            self._sections[name] = PromptSection(
                name=name,
                content=content,
                priority=self._sections[name].priority,
            )

    def clear(self) -> None:
        self._sections.clear()

    def assemble(self) -> str:
        """装配最终提示词：按优先级降序拼接，用 \\n\\n 分隔。"""
        sections = self.list()
        return "\n\n".join(s.content for s in sections)


__all__ = [
    "PromptSection",
    "SystemPromptService",
    "DEFAULT_SECTIONS",
]
