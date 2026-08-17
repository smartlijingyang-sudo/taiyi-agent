from cordis import Context, plugin


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 DeepSeekProvider 到 LLMService。"""
    from taiyi_llm_deepseek import DeepSeekProvider

    provider = DeepSeekProvider(
        api_key=(config or {}).get("api_key"),
        base_url=(config or {}).get("base_url"),
    )

    llm = ctx.inject("llm")
    llm.register_provider(provider, default=True)
