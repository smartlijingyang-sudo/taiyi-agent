"""taiyi-llm plugin — registers LLMService with no providers.

Providers (deepseek, openai, ...) self-register from their own `@plugin`
setup fn. This plugin only provides the `ctx.llm` seam.
"""

from __future__ import annotations

from cordis import plugin

from .service import LLMService


@plugin
async def setup(ctx, config):
    """Mount the LLMService under `ctx.llm`.

    Providers register themselves later in the load order (typically after
    this plugin); dispatch falls back to `default_provider` until then.
    """
    svc = LLMService(ctx)
    ctx.provide("llm", svc)
    ctx.effect(svc, name="llm:service")


__all__ = ["setup"]