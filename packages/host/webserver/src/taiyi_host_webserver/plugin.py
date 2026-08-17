from cordis import plugin


@plugin
async def setup(ctx, config):
    from . import WebserverService

    cfg = config or {}
    svc = WebserverService(
        ctx,
        host=cfg.get("host", "127.0.0.1"),
        port=cfg.get("port", 3080),
        log_level=cfg.get("log_level", "info"),
    )
    ctx.provide("webserver", svc)
    ctx.provide("webserver_handle", svc.handle)
    ctx.effect(svc, name="webserver:service")
    await svc.start()