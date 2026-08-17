"""taiyi-api — gateway / BFF plugin。

把 agent loop 暴露为 HTTP endpoint：
  POST /v1/chat      — NDJSON 流式输出（每个事件一行 JSON）
  GET  /v1/healthz   — 健康检查
  GET  /v1/sessions  — 列出当前 session
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from cordis import Context, Service
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from taiyi_core_sessions import SessionsService
from taiyi_core_agent_loop import run_turn

__all__ = ["register_routes"]


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    agent: str = "default"


def register_routes(ctx: Context) -> None:
    """注册 FastAPI 路由到 ctx.webserver.app。"""
    handle = ctx.inject("webserver")
    app = handle.app

    @app.post("/v1/chat")
    async def chat(req: ChatRequest, request: Request):
        sessions: SessionsService = ctx.inject("sessions")
        session = sessions.get(req.session_id) if req.session_id else None
        if session is None:
            session = sessions.create(req.session_id)

        async def ndjson() -> AsyncIterator[bytes]:
            try:
                yield (json.dumps({"event": "session/start", "session_id": session.id}, ensure_ascii=False) + "\n").encode()
                async for ev in run_turn(ctx, session.id, req.message):
                    yield (json.dumps(ev, ensure_ascii=False) + "\n").encode()
                yield (json.dumps({"event": "session/end", "session_id": session.id}, ensure_ascii=False) + "\n").encode()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                yield (json.dumps({"event": "error", "error": str(e)}, ensure_ascii=False) + "\n").encode()

        return StreamingResponse(
            ndjson(),
            media_type="application/x-ndjson",
            headers={"X-Session-Id": session.id},
        )

    @app.get("/v1/healthz")
    async def healthz():
        return JSONResponse({"status": "ok", "service": "taiyi"})

    @app.get("/v1/sessions")
    async def list_sessions():
        sessions: SessionsService = ctx.inject("sessions")
        return JSONResponse(
            {
                "sessions": [
                    {
                        "id": s.id,
                        "events": len(s.events),
                    }
                    for s in sessions.list()
                ]
            }
        )

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str):
        sessions: SessionsService = ctx.inject("sessions")
        s = sessions.get(session_id)
        if s is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(
            {
                "id": s.id,
                "events": [ev.to_dict() for ev in s.events],
            }
        )


import asyncio  # noqa: E402