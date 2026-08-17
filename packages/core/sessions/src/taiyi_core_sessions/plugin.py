from cordis import Context, Service, plugin


class SessionsServiceAdapter(Service):
    """SessionsService 的 cordis Service 包装。"""

    def __init__(self, ctx: Context) -> None:
        from taiyi_core_sessions import SessionsService
        super().__init__(ctx)
        self._service = SessionsService()

    @property
    def service(self) -> "SessionsService":
        return self._service

    def create(self, session_id: str | None = None):
        return self._service.create(session_id)

    def get(self, session_id: str):
        return self._service.get(session_id)

    def list(self):
        return self._service.list()

    async def dispose(self) -> None:
        pass


@plugin
async def setup(ctx: Context, config: dict | None) -> None:
    """注册 SessionsService。"""
    svc = SessionsServiceAdapter(ctx)
    ctx.provide("sessions", svc)
    ctx.effect(svc, name="sessions:service")
