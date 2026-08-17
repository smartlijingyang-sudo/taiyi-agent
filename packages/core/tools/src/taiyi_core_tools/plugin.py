from cordis import Context, Service, plugin


class ToolsServiceAdapter(Service):
    """ToolsService 的 cordis Service 包装。"""

    def __init__(self, ctx: Context) -> None:
        from taiyi_core_tools import ToolsService
        super().__init__(ctx)
        self._service = ToolsService()

    @property
    def service(self) -> "ToolsService":
        return self._service

    def register(self, tool):
        return self._service.register(tool)

    def get(self, name):
        return self._service.get(name)

    def schemas(self):
        return self._service.schemas()

    async def dispose(self) -> None:
        pass


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 ToolsService。"""
    svc = ToolsServiceAdapter(ctx)
    ctx.provide("tools", svc)
    ctx.effect(svc, name="tools:service")
