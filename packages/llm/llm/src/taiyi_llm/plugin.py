from cordis import Context, Service, plugin


class LLMServiceAdapter(Service):
    """LLMService 的 cordis Service 包装。"""

    def __init__(self, ctx: Context) -> None:
        from taiyi_llm import LLMService
        super().__init__(ctx)
        self._service = LLMService()

    @property
    def _providers(self):
        """暴露底层 service 的 _providers（供 llm-retry 等插件使用）。"""
        return self._service._providers

    @property
    def service(self) -> "LLMService":
        return self._service

    def register_provider(self, provider, default: bool = False) -> None:
        self._service.register_provider(provider, default=default)

    async def stream(self, **kwargs):
        async for chunk in self._service.stream(**kwargs):
            yield chunk

    async def complete(self, **kwargs) -> str:
        return await self._service.complete(**kwargs)

    async def dispose(self) -> None:
        pass


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 LLMService。"""
    svc = LLMServiceAdapter(ctx)
    ctx.provide("llm", svc)
    ctx.effect(svc, name="llm:service")
