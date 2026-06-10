# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class TasksAsyncHandlersMixin:
    async def handle_task_run_detached(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        prompt = str(params.get("prompt", "") or "").strip()
        if not prompt:
            raise InvalidParamsError("Missing prompt")
        task = self._task_manager_instance().spawn_detached(
            prompt=prompt,
            title=str(params.get("title", "") or ""),
            sandbox_preset=normalize_preset(params.get("sandboxPreset") or "read-only"),
            provider=str(params.get("provider", "") or ""),
            model=str(params.get("model", "") or ""),
            config_path=str(params.get("configPath", "") or ""),
            auto_approve_edits=bool(params.get("autoApproveEdits", False)),
        )
        return {"task": task.to_dict()}

    async def handle_task_watch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        task_id = str(params.get("taskId", "") or "").strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        limit = self._clamp_count(params.get("limit"), default=200, min_value=1, max_value=1000)
        return {"taskId": task_id, "events": list(self._task_manager_instance().attach_to(task_id, limit=limit))}

    async def handle_task_cancel_detached(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        task_id = str(params.get("taskId", "") or "").strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().cancel(task_id)
        return {"task": task.to_dict()}


@register("poor-cli/taskRunDetached")
async def _rpc_task_run_detached(ctx, params):
    return await ctx.handle_task_run_detached(params)


@register("poor-cli/taskWatch")
async def _rpc_task_watch(ctx, params):
    return await ctx.handle_task_watch(params)


@register("poor-cli/taskCancel")
async def _rpc_task_cancel(ctx, params):
    return await ctx.handle_task_cancel_detached(params)
