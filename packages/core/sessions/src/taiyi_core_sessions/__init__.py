"""taiyi-core-sessions — Session event log + store.

提供：
  - SessionEvent 类型（turn/step/user/assistant/tool 事件）
  - Session（事件日志 + projection）
  - SessionsService（session 注册表）
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

# ---------------------------------------------------------------------------
# EventType
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Session 事件类型。"""

    # Turn lifecycle
    TURN_START = "turn/start"
    TURN_END = "turn/end"

    # Step lifecycle
    STEP_START = "step/start"
    STEP_END = "step/end"

    # Messages
    USER_MESSAGE = "user/message"
    ASSISTANT_CHUNK = "assistant/chunk"
    ASSISTANT_MESSAGE = "assistant/message"

    # Tool calls
    TOOL_CALL = "tool/call"
    TOOL_RESULT = "tool/result"


# ---------------------------------------------------------------------------
# SessionEvent
# ---------------------------------------------------------------------------


@dataclass
class SessionEvent:
    """不可变 session 事件。

    字段：
      - type: 事件类型（EventType 枚举值）
      - payload: 事件数据（dict）
      - session_id: 所属 session
      - seq: 序列号（单调递增）
      - ts_ms: 时间戳（毫秒）
    """

    type: str
    payload: dict = field(default_factory=dict)
    session_id: str = ""
    seq: int = 0
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": self.payload,
            "session_id": self.session_id,
            "seq": self.seq,
            "ts_ms": self.ts_ms,
        }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class Session:
    """Session：事件日志 + projection。

    用法：
      session = Session("session_id")
      session.append(EventType.USER_MESSAGE, {"content": "hi"})
      events = session.events  # 所有事件
      messages = session.messages()  # model-visible messages
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.id = session_id or str(uuid.uuid4())
        self._events: list[SessionEvent] = []
        self._seq = 0
        self._lock = asyncio.Lock()

    @property
    def events(self) -> list[SessionEvent]:
        return list(self._events)

    def append(self, event_type: str, payload: dict) -> SessionEvent:
        """追加事件。"""
        self._seq += 1
        ev = SessionEvent(
            type=event_type,
            payload=payload,
            session_id=self.id,
            seq=self._seq,
        )
        self._events.append(ev)
        return ev

    def messages(self) -> list[dict]:
        """投影出 model-visible messages。

        从事件日志重建对话历史：
          - user/message → {"role": "user", "content": ...}
          - assistant/message → {"role": "assistant", "content": ...}
          - tool/call → {"role": "assistant", "tool_calls": [...]}
          - tool/result → {"role": "tool", "tool_call_id": ..., "content": ...}
        """
        msgs: list[dict] = []
        for ev in self._events:
            if ev.type == EventType.USER_MESSAGE:
                msgs.append({"role": "user", "content": ev.payload.get("content", "")})
            elif ev.type == EventType.ASSISTANT_MESSAGE:
                msgs.append({"role": "assistant", "content": ev.payload.get("content", "")})
            elif ev.type == EventType.TOOL_CALL:
                tool_calls = ev.payload.get("tool_calls", [])
                if tool_calls:
                    msgs.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
            elif ev.type == EventType.TOOL_RESULT:
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": ev.payload.get("tool_call_id"),
                        "content": ev.payload.get("content", ""),
                    }
                )
        return msgs

    def fork(self) -> Session:
        """分支：创建新 session，复制事件。"""
        new_session = Session()
        new_session._events = list(self._events)
        new_session._seq = self._seq
        return new_session


# ---------------------------------------------------------------------------
# SessionsService
# ---------------------------------------------------------------------------


class SessionsService:
    """Session 注册表。

    用法：
      sessions = SessionsService()
      session = sessions.create()
      session2 = sessions.get(session_id)
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, session_id: str | None = None) -> Session:
        """创建新 session。"""
        sid = session_id or str(uuid.uuid4())
        if sid in self._sessions:
            return self._sessions[sid]
        session = Session(sid)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session | None:
        """获取 session。"""
        return self._sessions.get(session_id)

    def list(self) -> list[Session]:
        """列出所有 session。"""
        return list(self._sessions.values())

    def delete(self, session_id: str) -> bool:
        """删除 session。"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "SessionEvent",
    "Session",
    "SessionsService",
    "EventType",
]
