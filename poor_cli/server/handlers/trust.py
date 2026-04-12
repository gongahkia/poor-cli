# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class TrustHandlersMixin:
    async def handle_get_trust_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..trust import TrustManager
        mgr = TrustManager()
        return mgr.to_dict()

    async def handle_trust_repo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..trust import TrustManager
        mgr = TrustManager()
        path = params.get("path") or None
        canonical = mgr.trust(path)
        return {"trusted": True, "path": canonical}

    async def handle_untrust_repo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..trust import TrustManager
        mgr = TrustManager()
        path = params.get("path") or None
        removed = mgr.untrust(path)
        return {"untrusted": removed, "path": str(Path.cwd().resolve())}

@register('poor-cli/getTrustStatus')
async def _rpc_150(ctx, params):
    return await ctx.handle_get_trust_status(params)

@register('poor-cli/trustRepo')
async def _rpc_151(ctx, params):
    return await ctx.handle_trust_repo(params)

@register('poor-cli/untrustRepo')
async def _rpc_152(ctx, params):
    return await ctx.handle_untrust_repo(params)
