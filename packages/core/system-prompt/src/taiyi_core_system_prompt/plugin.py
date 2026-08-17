from cordis import Context, Service, plugin


class SystemPromptServiceAdapter(Service):
    """SystemPromptService 的 cordis Service 包装。"""

    def __init__(self, ctx: Context) -> None:
        from taiyi_core_system_prompt import SystemPromptService
        super().__init__(ctx)
        self._service = SystemPromptService()

    @property
    def service(self) -> "SystemPromptService":
        return self._service

    def add(self, section):
        return self._service.add(section)

    def assemble(self) -> str:
        return self._service.assemble()

    async def dispose(self) -> None:
        pass


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 SystemPromptService。"""
    svc = SystemPromptServiceAdapter(ctx)
    ctx.provide("system_prompt", svc)
    ctx.effect(svc, name="system_prompt:service")
