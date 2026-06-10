# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ProfilesHandlersMixin:
    async def handle_list_profiles(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..profiles import ProfileManager
        mgr = ProfileManager()
        return {"profiles": [p.to_dict() for p in mgr.list_profiles()]}

    async def handle_apply_profile(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..profiles import ProfileManager
        name = str(params.get("name", "")).strip()
        if not name:
            return {"error": "name required"}
        mgr = ProfileManager()
        session = self._session_manager.get_session(params.get("sessionId"))
        if session.core.config:
            mgr.apply_to_config(session.core.config, name)
            return {"applied": name}
        return {"error": "session not initialized"}

@register('poor-cli/listProfiles')
async def _rpc_148(ctx, params):
    return await ctx.handle_list_profiles(params)

@register('poor-cli/applyProfile')
async def _rpc_149(ctx, params):
    return await ctx.handle_apply_profile(params)
