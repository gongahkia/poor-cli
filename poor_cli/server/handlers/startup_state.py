# ruff: noqa: F403,F405
from __future__ import annotations

from typing import Any, Dict

from ...config_fast import load_runtime_model_settings
from poor_cli.server.registry import register


class StartupStateHandlersMixin:
    async def handle_get_startup_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return configured provider/model before full backend initialization."""
        del params
        settings = load_runtime_model_settings()
        return {
            "provider": str(settings.get("provider", "openai")),
            "model": str(settings.get("model", "")),
        }


@register("getStartupState")
async def _rpc_get_startup_state(ctx, params):
    return await ctx.handle_get_startup_state(params)
