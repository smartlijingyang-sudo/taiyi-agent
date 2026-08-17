from cordis import plugin


@plugin
async def setup(ctx, config):
    from . import register_routes

    register_routes(ctx)