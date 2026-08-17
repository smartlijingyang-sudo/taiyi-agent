from cordis import Context, Service, plugin


class AgentRegistryAdapter(Service):
    """AgentRegistry 的 cordis Service 包装。"""

    def __init__(self, ctx: Context) -> None:
        from taiyi_core_agent import AgentRegistry, Agent
        super().__init__(ctx)
        self._service = AgentRegistry()
        # 注册默认 agent
        self._service.register(Agent(name="default", model="deepseek-chat"))

    @property
    def service(self) -> "AgentRegistry":
        return self._service

    def register(self, agent):
        return self._service.register(agent)

    def get(self, name):
        return self._service.get(name)

    def default(self):
        return self._service.default()

    async def dispose(self) -> None:
        pass


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 AgentRegistry。"""
    svc = AgentRegistryAdapter(ctx)
    ctx.provide("agents", svc)
    ctx.effect(svc, name="agents:service")
