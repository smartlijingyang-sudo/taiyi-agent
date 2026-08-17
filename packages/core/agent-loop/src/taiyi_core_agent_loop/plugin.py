from cordis import plugin


@plugin
async def setup(ctx, config):
    from . import AgentLoopService

    svc = AgentLoopService(ctx)
    ctx.provide("agent_loop", svc)
    ctx.effect(svc, name="agent_loop:service")