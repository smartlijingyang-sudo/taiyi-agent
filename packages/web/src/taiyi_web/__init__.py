"""taiyi-web — chat UI plugin。

把 chat.html 作为 FastAPI 静态路由挂在 ctx.webserver.app 上。
"""
from __future__ import annotations

import os

from cordis import Context
from fastapi.responses import HTMLResponse, RedirectResponse

__all__ = ["register_routes"]

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_CHAT_HTML = os.path.join(_STATIC_DIR, "chat.html")


def register_routes(ctx: Context) -> None:
    handle = ctx.inject("webserver")
    app = handle.app

    with open(_CHAT_HTML, "r", encoding="utf-8") as f:
        chat_html = f.read()

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/chat")

    @app.get("/chat", include_in_schema=False)
    async def chat_page():
        return HTMLResponse(chat_html)