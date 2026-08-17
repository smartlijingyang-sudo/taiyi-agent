"""taiyi-bundle-base — base bundle。

对齐 dsh-base：mount core + llm + deepseek + retry。
"""
from __future__ import annotations


def get_plugin_paths() -> list[tuple[str, dict]]:
    """返回 (import:attr, config) 列表。

    与 dsh-base 的 rows 形态一致。
    """
    return [
        ("taiyi_core_sessions.plugin:setup", {}),
        ("taiyi_core_system_prompt.plugin:setup", {}),
        ("taiyi_core_tools.plugin:setup", {}),
        ("taiyi_core_agent.plugin:setup", {}),
        ("taiyi_core_agent_loop.plugin:setup", {}),
        ("taiyi_llm.plugin:setup", {}),
        ("taiyi_llm_deepseek.plugin:setup", {}),
        ("taiyi_llm_retry.plugin:setup", {"wrap": ["deepseek"], "max_retries": 3, "backoff": 1.0}),
    ]