# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class DeploymentHandlersMixin:
    async def handle_deploy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import deploy
        result = await deploy(target=params.get("target"), prod=params.get("prod", False))
        return result.to_dict()

    async def handle_deploy_targets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import detect_deploy_targets
        targets = detect_deploy_targets()
        return {"targets": [t.to_dict() for t in targets]}

    async def handle_deploy_validate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import validate_pre_deploy
        return validate_pre_deploy()

    async def handle_deploy_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import get_deploy_history
        return {"history": get_deploy_history(limit=params.get("limit", 20))}

@register('poor-cli/deploy')
async def _rpc_162(ctx, params):
    return await ctx.handle_deploy(params)

@register('poor-cli/deployTargets')
async def _rpc_163(ctx, params):
    return await ctx.handle_deploy_targets(params)

@register('poor-cli/deployValidate')
async def _rpc_164(ctx, params):
    return await ctx.handle_deploy_validate(params)

@register('poor-cli/deployHistory')
async def _rpc_165(ctx, params):
    return await ctx.handle_deploy_history(params)
