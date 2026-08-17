"""`taiyi_core_system_prompt.plugin` — cordis plugin entry.

1:1 port of `@deepseek-ai/dsh-system-prompt`'s default export. Installs the
:class:`SystemPrompt` registry Service under ``ctx.system_prompt``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cordis import Context, plugin

from taiyi_core_system_prompt.service import SystemPrompt
from taiyi_core_system_prompt.types import Config

__all__ = ["setup"]


@plugin(name="system-prompt")
async def setup(ctx: Context, config: Any = None) -> Callable[[], None]:
    """Install the system-prompt registry under ``ctx.system_prompt``."""
    normalized = _normalize_config(config)
    svc = SystemPrompt(ctx, config=normalized)
    return ctx.reflect.provide("system_prompt", svc)  # type: ignore[attr-defined]


def _normalize_config(config: Any) -> dict[str, Any] | Config:
    """Accept ``None`` / :class:`Config` / ``dict`` as the plugin config."""
    if config is None:
        return Config().to_upstream_kwargs()
    if isinstance(config, Config):
        return config.to_upstream_kwargs()
    if isinstance(config, dict):
        return Config(**config).to_upstream_kwargs()
    raise TypeError(
        f"unsupported system-prompt config type: {type(config).__name__}"
    )
