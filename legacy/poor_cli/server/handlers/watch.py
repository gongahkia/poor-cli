# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class WatchHandlersMixin:
    async def handle_watch_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.file_watcher import collect_watch_status

        params = params or {}
        try:
            limit = int(params.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        payload = collect_watch_status(root=params.get("root") or os.getcwd(), action_limit=limit)
        config = getattr(getattr(self, "core", None), "config", None)
        if config is None:
            try:
                _, config = self._ensure_config_loaded()
            except Exception:
                config = None
        agentic = getattr(config, "agentic", None)
        payload["qa_enabled"] = bool(agentic and getattr(agentic, "auto_lint", False))
        return payload


@register("watch.status")
async def _rpc_watch_status(ctx, params):
    return await ctx.handle_watch_status(params)
