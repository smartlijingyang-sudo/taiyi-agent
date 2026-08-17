"""Smoke 测试：mount 整个 base bundle 并跑一轮 turn。"""
from __future__ import annotations

import asyncio

import pytest

from cordis import Context
from cordis.loader import Bundle, PluginRow, mount

from taiyi_bundle_base import get_plugin_paths


@pytest.mark.asyncio
async def test_base_bundle_mount():
    ctx = Context()
    rows = [PluginRow(plugin=p, config=c) for p, c in get_plugin_paths()]
    bundle = Bundle(name="base", rows=rows)
    d = await mount(ctx, [bundle])
    # 关键 services 都注册了
    assert ctx.inject("sessions") is not None
    assert ctx.inject("system_prompt") is not None
    assert ctx.inject("tools") is not None
    assert ctx.inject("agents") is not None
    assert ctx.inject("agent_loop") is not None
    assert ctx.inject("llm") is not None
    await d.dispose()


@pytest.mark.asyncio
async def test_run_turn_emits_chunks():
    ctx = Context()
    rows = [PluginRow(plugin=p, config=c) for p, c in get_plugin_paths()]
    bundle = Bundle(name="base", rows=rows)
    await mount(ctx, [bundle])

    sessions = ctx.inject("sessions")
    loop_svc = ctx.inject("agent_loop")
    session = sessions.create()
    events = []
    async for ev in loop_svc.run_turn(session, "hello"):
        events.append(ev)
    # 至少要看到 turn/start + assistant/chunk* + turn/end
    types = [e["event"] for e in events]
    assert "turn/start" in types
    assert "turn/end" in types
    # 有内容
    has_chunk = any(e["event"] == "assistant/chunk" for e in events)
    has_message = any(e["event"] == "assistant/message" for e in events)
    assert has_chunk or has_message


def test_dump_config_runs():
    """CLI --dump-config 应打印 plugin 树。"""
    from click.testing import CliRunner
    # 用 subprocess 替代 click 测试
    import subprocess
    r = subprocess.run(
        [".venv/bin/taiyi", "--dump-config"],
        capture_output=True,
        text=True,
        cwd="/home/lichao/taiyi-agent",
    )
    assert r.returncode == 0
    assert "taiyi-base" in r.stdout
    assert "taiyi-web-app" in r.stdout