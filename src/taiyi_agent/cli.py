"""taiyi CLI — 完全对齐 dsh 的 profile/bundle 加载机制。

CLI 职责：
  1. 解析 profile 名称
  2. 读取 profile 的 package.json 获取 bundles 列表
  3. 加载每个 bundle 的 cordis.patch.yml
  4. 组合所有 patches
  5. 根据配置加载插件
  6. 等待插件启动完成
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path

import yaml
from cordis import Context
from cordis.loader import Bundle, PluginRow

from .profiles import load_profile, compose_profile_patches

NAME = "taiyi"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=NAME,
        description="太一 (Taiyi) — deepseek-harness 的 Python 复刻",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        default="web",
        help="profile 名（默认 web；可选: web, base）",
    )
    parser.add_argument(
        "--dump-config",
        action="store_true",
        help="打印组合后的插件树后退出",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="列出可用 profiles",
    )

    args = parser.parse_args(argv)

    if args.list_profiles:
        profiles_dir = Path(__file__).parent.parent.parent / "profiles"
        if profiles_dir.exists():
            for p in sorted(profiles_dir.iterdir()):
                if p.is_dir():
                    print(p.name)
        return 0

    if args.dump_config:
        return _cmd_dump_config(args.profile)

    # 启动 profile
    return asyncio.run(_run_profile(args.profile))


async def _run_profile(profile_name: str) -> int:
    """加载并启动 profile。"""
    # 1. 加载 profile
    profile = load_profile(NAME, profile_name)
    if profile is None:
        print(f"Error: profile {profile_name!r} not found", file=sys.stderr)
        return 1

    # 2. 组合 patches
    patches = compose_profile_patches(profile)

    # 3. 创建 context 并加载插件
    ctx = Context()

    for patch in patches:
        if isinstance(patch, dict) and "insert" in patch:
            for entry in patch["insert"]:
                plugin_name = entry.get("name")
                config = entry.get("config", {})
                if plugin_name:
                    try:
                        # 动态导入插件
                        module_path, attr = plugin_name.rsplit(":", 1)
                        import importlib
                        mod = importlib.import_module(module_path)
                        plugin_fn = getattr(mod, attr)
                        await ctx.plugin(plugin_fn, config)
                    except Exception as e:
                        print(f"Error loading plugin {plugin_name}: {e}", file=sys.stderr)

    # 4. 等待信号或插件完成
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass

    print(f"\n🌐 太一 (Taiyi) profile {profile_name!r} 已启动")
    print(f"   按 Ctrl+C 退出\n")

    await stop.wait()
    await ctx.dispose()
    return 0


def _cmd_dump_config(profile_name: str) -> int:
    """打印组合后的插件树。"""
    profile = load_profile(NAME, profile_name)
    if profile is None:
        print(f"Error: profile {profile_name!r} not found", file=sys.stderr)
        return 1

    patches = compose_profile_patches(profile)

    print(f"# Profile: {profile_name}")
    print(f"# Bundles: {len(profile.bundles)}")
    print()

    for patch in patches:
        if isinstance(patch, dict) and "insert" in patch:
            for entry in patch["insert"]:
                plugin_name = entry.get("name", "")
                config = entry.get("config", {})
                print(f"  - plugin: {plugin_name}")
                if config:
                    print(f"    config: {config}")

    return 0
