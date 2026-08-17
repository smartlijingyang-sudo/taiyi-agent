"""Profile 解析：CLI 只问「跑哪个 profile」，plugins 自己负责启动。"""
from __future__ import annotations

from typing import NamedTuple

from cordis.loader import Bundle, PluginRow


class Profile(NamedTuple):
    name: str
    bundles: list[Bundle]


def _bundle_from(name: str, paths: list[tuple[str, dict]]) -> Bundle:
    return Bundle(
        name=name,
        rows=[PluginRow(plugin=p, config=c or {}) for p, c in paths],
    )


def resolve_profile(name: str) -> Profile:
    """根据名字解析 profile = bundles 列表。

    CLI 不知道任何具体的 plugin / bundle —— 它只问「跑哪个 profile」。
    """
    if name == "base":
        from taiyi_bundle_base import get_plugin_paths
        return Profile(name="base", bundles=[_bundle_from("taiyi-base", get_plugin_paths())])

    if name in ("web-app", "webapp", "web"):
        from taiyi_bundle_base import get_plugin_paths
        from taiyi_bundle_web_app import get_plugin_paths as web_paths
        return Profile(
            name="web-app",
            bundles=[
                _bundle_from("taiyi-base", get_plugin_paths()),
                _bundle_from("taiyi-web-app", web_paths()),
            ],
        )

    # 未知 profile：返回空 bundles（CLI 友好提示）
    raise SystemExit(
        f"unknown profile: {name!r}. "
        f"Available: base, web-app. "
        f"Define new ones in taiyi_agent.profiles."
    )


def list_profiles() -> list[str]:
    return ["base", "web-app"]