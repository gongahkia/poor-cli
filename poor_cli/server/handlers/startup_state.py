# ruff: noqa: F403,F405
from __future__ import annotations

from typing import Any, Dict

from poor_cli.server.registry import register
from ..startup_probe import get_startup_state_payload


class StartupStateHandlersMixin:
    async def handle_get_startup_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return configured provider/model before full backend initialization."""
        del params
        return get_startup_state_payload()


@register("getStartupState")
async def _rpc_get_startup_state(ctx, params):
    return await ctx.handle_get_startup_state(params)
