from __future__ import annotations

from poor_cli.server.registry import register
from poor_cli.server.services_state import ServicesStateMixin


class ServicesHandlersMixin(ServicesStateMixin):
    pass


@register('startService')
async def _rpc_12(ctx, params):
    return await ctx.handle_start_service(params)

@register('stopService')
async def _rpc_13(ctx, params):
    return await ctx.handle_stop_service(params)

@register('getServiceStatus')
async def _rpc_14(ctx, params):
    return await ctx.handle_get_service_status(params)

@register('getServiceLogs')
async def _rpc_15(ctx, params):
    return await ctx.handle_get_service_logs(params)

@register('poor-cli/startService')
async def _rpc_94(ctx, params):
    return await ctx.handle_start_service(params)

@register('poor-cli/stopService')
async def _rpc_95(ctx, params):
    return await ctx.handle_stop_service(params)

@register('poor-cli/getServiceStatus')
async def _rpc_96(ctx, params):
    return await ctx.handle_get_service_status(params)

@register('poor-cli/getServiceLogs')
async def _rpc_97(ctx, params):
    return await ctx.handle_get_service_logs(params)
