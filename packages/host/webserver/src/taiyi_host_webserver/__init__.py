"""taiyi-host-webserver — FastAPI host plugin。

plugin 行为：
  setup() — 创建 FastAPI app，**自动起 uvicorn 后台任务**
  无需 CLI 关心 uvicorn / 端口 / 日志 —— CLI 只 mount + wait

对外暴露：
  ctx.webserver.app      — FastAPI app（其它 plugin 挂 routes 用）
  ctx.webserver.handle   — {app, host, port, log_level}
  ctx.webserver.wait()   — block until shutdown signal
"""
from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass

import uvicorn
from cordis import Context, Service
from fastapi import FastAPI

__all__ = ["WebserverService", "WebserverHandle"]


@dataclass
class WebserverHandle:
    app: FastAPI
    host: str = "127.0.0.1"
    port: int = 3080
    log_level: str = "info"


class WebserverService(Service):
    """host service — 启动 uvicorn 后阻塞等待 SIGINT/SIGTERM。"""

    def __init__(
        self,
        ctx: Context,
        *,
        host: str = "127.0.0.1",
        port: int = 3080,
        log_level: str = "info",
    ) -> None:
        super().__init__(ctx)
        self.handle = WebserverHandle(
            app=FastAPI(title="Taiyi Agent", version="0.1.0"),
            host=host,
            port=port,
            log_level=log_level,
        )
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        """plugin setup 末调用：起 uvicorn。"""
        cfg = uvicorn.Config(
            self.handle.app,
            host=self.handle.host,
            port=self.handle.port,
            log_level=self.handle.log_level,
            lifespan="on",
        )
        self._server = uvicorn.Server(cfg)

        async def _serve() -> None:
            assert self._server is not None
            await self._server.serve()
            self._stopped.set()

        self._task = asyncio.create_task(_serve())

        # 等 server 真正 ready（uvicorn has started_startup / started）
        for _ in range(200):  # 最多等 10s
            await asyncio.sleep(0.05)
            if self._server.started:
                break

        print(
            f"\n🌐 太一 (Taiyi) 已启动\n"
            f"   Web UI:  http://{self.handle.host}:{self.handle.port}/chat\n"
            f"   API:     http://{self.handle.host}:{self.handle.port}/v1/chat\n"
            f"   Health:  http://{self.handle.host}:{self.handle.port}/v1/healthz\n"
            f"   按 Ctrl+C 退出\n",
            flush=True,
        )

    async def wait(self) -> None:
        """CLI 调用：阻塞直到收到 SIGINT/SIGTERM 或 server 异常退出。"""
        if self._task is None:
            return
        try:
            loop = asyncio.get_running_loop()
            stop = asyncio.Event()

            def _on_signal() -> None:
                stop.set()
                if self._server is not None:
                    self._server.should_exit = True

            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _on_signal)
                except NotImplementedError:
                    pass

            # 等：信号 OR uvicorn 自行结束
            done, _ = await asyncio.wait(
                [asyncio.create_task(stop.wait()), self._task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # 让 uvicorn 真正停
            if self._server is not None:
                self._server.should_exit = True
                if not self._task.done():
                    try:
                        await asyncio.wait_for(self._task, timeout=5.0)
                    except asyncio.TimeoutError:
                        self._task.cancel()
        finally:
            self._stopped.set()

    async def dispose(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()