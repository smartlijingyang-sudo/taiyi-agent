"""taiyi CLI — 完全插件化启动。

CLI 心智模型（对齐 dsh）：
  - CLI 只做三件事：解析 profile / mount plugins / 等 plugins 启动 host
  - host 是否要跑 uvicorn / 监听哪个端口 / 打印 banner —— 全部由 plugin 自己决定
  - 不知道 web / api / uvicorn 的存在

用法：
  taiyi                          # 跑默认 profile = web-app
  taiyi <profile>                # 跑指定 profile
  taiyi --dump-config <profile>  # 打印插件树
  taiyi chat "msg"               # headless 单轮（profile=base）
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys

from cordis import Context
from cordis.loader import dump_config, mount

from .profiles import list_profiles, resolve_profile


async def _run_profile(profile_name: str) -> int:
    """挂载 profile，plugins 自己起 host；CLI 只 wait。"""
    profile = resolve_profile(profile_name)
    ctx = Context()
    await mount(ctx, profile.bundles)

    # 如果 webserver plugin 在场，让它 wait；否则 idle
    webserver = ctx.inject("webserver", default=None) if ctx.has("webserver") else None
    if webserver is not None:
        await webserver.wait()
    else:
        # 无 host 的 profile（batch）：等 SIGINT
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _on_signal() -> None:
            stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except NotImplementedError:
                pass
        await stop.wait()

    await ctx.dispose()
    return 0


async def _run_headless(profile_name: str, message: str) -> int:
    """单轮 turn。profile 通常是 base。"""
    from taiyi_core_agent_loop import AgentLoopService
    from taiyi_core_sessions import SessionsService

    profile = resolve_profile(profile_name)
    ctx = Context()
    await mount(ctx, profile.bundles)

    sessions: SessionsService = ctx.inject("sessions")
    loop: AgentLoopService = ctx.inject("agent_loop")
    session = sessions.create()

    rc = 0
    async for ev in loop.run_turn(session, message):
        if ev.type == "assistant/chunk":
            sys.stdout.write(ev.payload.get("delta", ""))
            sys.stdout.flush()
        elif ev.type == "assistant/message":
            sys.stdout.write(ev.payload.get("content", ""))
            sys.stdout.flush()
        elif ev.payload.get("error"):
            sys.stderr.write(f"\n[error] {ev.payload['error']}\n")
            rc = 1
    sys.stdout.write("\n")
    await ctx.dispose()
    return rc


def _cmd_dump_config(profile_name: str) -> int:
    profile = resolve_profile(profile_name)
    ctx = Context()
    # Mount to get the actual plugin tree
    import asyncio
    asyncio.run(mount(ctx, profile.bundles))
    print(f"# Profile: {profile_name}")
    print(f"# Services registered: {list(ctx.services().keys())}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="taiyi",
        description="太一 (Taiyi) — deepseek-harness 的 Python MVP",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        default="web-app",
        help=f"profile 名（默认 web-app；可选: {', '.join(list_profiles())}）",
    )
    parser.add_argument(
        "--dump-config",
        action="store_true",
        help="打印插件树后退出（对齐 dsh --dump-config）",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="列出可用 profile",
    )
    parser.add_argument(
        "--chat",
        metavar="MESSAGE",
        help="headless 单轮（profile=base），后面跟消息",
    )

    args = parser.parse_args(argv)

    if args.list_profiles:
        print("available profiles:", ", ".join(list_profiles()))
        return 0

    if args.dump_config:
        return _cmd_dump_config(args.profile)

    if args.chat:
        return asyncio.run(_run_headless("base", args.chat))

    # 默认：起 profile（让 plugins 自己决定怎么 run）
    return asyncio.run(_run_profile(args.profile))


if __name__ == "__main__":
    raise SystemExit(main())