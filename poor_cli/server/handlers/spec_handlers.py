# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class SpecHandlersMixin:
    def _spec_mode(self):
        from poor_cli.spec_mode import SpecMode
        return SpecMode(Path.cwd(), checkpoint_manager=getattr(self.core, "checkpoint_manager", None))

    async def handle_spec_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        path = str(params.get("path", "") or "").strip()
        if not path:
            raise InvalidParamsError("path is required")
        return {"spec": self._spec_mode().run(Path(path)).to_dict()}

    async def handle_spec_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        spec_id = str(params.get("specId", "") or "").strip()
        if not spec_id:
            raise InvalidParamsError("specId is required")
        return {"spec": self._spec_mode().status(spec_id).to_dict()}

    async def handle_spec_abort(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        spec_id = str(params.get("specId", "") or "").strip()
        if not spec_id:
            raise InvalidParamsError("specId is required")
        return {"spec": self._spec_mode().abort(spec_id).to_dict()}


@register("poor-cli/specRun")
async def _rpc_spec_run(ctx, params):
    return await ctx.handle_spec_run(params)


@register("poor-cli/specStatus")
async def _rpc_spec_status(ctx, params):
    return await ctx.handle_spec_status(params)


@register("poor-cli/specAbort")
async def _rpc_spec_abort(ctx, params):
    return await ctx.handle_spec_abort(params)
