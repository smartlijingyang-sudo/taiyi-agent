"""taiyi-bundle-base — base bundle。

注意：base 的所有 plugin 配置都在 cordis.patch.yml 中定义。
CLI 会从 cordis.patch.yml 加载，不会调用 get_plugin_paths()。
"""
from __future__ import annotations


def get_plugin_paths() -> list[tuple[str, dict]]:
    """保留接口以兼容旧代码，实际不被 CLI 调用。

    真正的插件配置在 packages/bundle/base/cordis.patch.yml。
    """
    return []