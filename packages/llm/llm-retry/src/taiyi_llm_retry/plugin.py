from cordis import plugin


@plugin
async def setup(ctx, config):
    """retry plugin — 把 config.wrap 列表里的 provider 用 RetryProvider 装饰。

    用法：
        config:
          wrap: ["deepseek"]
          max_retries: 3
          backoff_base: 1.0
          max_backoff: 30.0
    """
    from taiyi_llm_retry import RetryProvider, RetryPolicy
    from taiyi_llm import LLMService

    llm: LLMService = ctx.inject("llm")
    cfg = config or {}
    policy = RetryPolicy(
        max_retries=cfg.get("max_retries", 3),
        backoff_base=cfg.get("backoff_base", 1.0),
        max_backoff=cfg.get("max_backoff", 30.0),
    )
    for name in cfg.get("wrap") or []:
        base = llm._providers.get(name)
        if base is None:
            continue
        retry = RetryProvider(base, policy=policy)
        retry.name = name  # 让 provider_for() 仍按原名查找
        llm._providers[name] = retry