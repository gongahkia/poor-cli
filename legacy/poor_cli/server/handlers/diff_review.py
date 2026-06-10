# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class DiffReviewHandlersMixin:
    def _edit_stage(self):
        self._ensure_initialized()
        registry = getattr(self.core, "tool_registry", None)
        stage = getattr(registry, "edit_stage", None)
        if stage is None:
            raise PoorCLIError("Diff review store not available")
        return stage

    async def _emit_edit_committed(self, payload: Dict[str, Any]) -> None:
        try:
            await self.write_message_stdio(JsonRpcMessage(
                method="poor-cli/editCommitted",
                params=payload,
            ))
        except Exception as e:
            logger.debug("emit editCommitted failed: %s", e)

    async def handle_diff_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"edits": self._edit_stage().list_pending()}

    async def handle_diff_preview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        return self._edit_stage().preview_edit(edit_id)

    async def handle_diff_stage(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = str(params.get("path") or "").strip()
        if not path:
            raise InvalidParamsError("path is required")
        edit = self._edit_stage().stage(
            path=path,
            original=str(params.get("original") or ""),
            proposed=str(params.get("proposed") or ""),
            tool_call_id=str(params.get("toolCallId") or params.get("tool_call_id") or ""),
            prompt=str(params.get("prompt") or "chat fenced code block"),
        ).to_dict()
        try:
            await self.write_message_stdio(JsonRpcMessage(
                method="poor-cli/editStaged",
                params=edit,
            ))
            await self.write_message_stdio(JsonRpcMessage(
                method="poor-cli/stageEvent",
                params=edit,
            ))
        except Exception as e:
            logger.debug("emit stageEvent failed: %s", e)
        return edit

    async def handle_edit_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        return await self.handle_diff_list({})

    async def handle_edit_approve(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        result = self._edit_stage().commit_or_reject(
            edit_id,
            "approve",
            checkpoint_manager=self.core.checkpoint_manager,
        )
        await self._emit_edit_committed(result)
        return result

    async def handle_edit_reject(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        result = self._edit_stage().commit_or_reject(edit_id, "reject")
        await self._emit_edit_committed(result)
        return result

    async def handle_diff_accept(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        stage = self._edit_stage()
        if hunk_id:
            return stage.accept_hunk(edit_id, hunk_id)
        result = stage.accept_all(edit_id, checkpoint_manager=self.core.checkpoint_manager)
        await self._emit_edit_committed(result)
        return result

    async def handle_diff_reject(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        stage = self._edit_stage()
        if hunk_id:
            return stage.reject_hunk(edit_id, hunk_id)
        result = stage.reject_all(edit_id)
        await self._emit_edit_committed(result)
        return result

    async def handle_diff_regen(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        new_content = str(params.get("newContent") or params.get("new_content") or "")
        if not edit_id or not hunk_id:
            raise InvalidParamsError("editId and hunkId are required")
        return self._edit_stage().regenerate_hunk(edit_id, hunk_id, new_content)


@register("diff.list")
@register("poor-cli/listPendingEdits")
async def _rpc_diff_list(ctx, params):
    return await ctx.handle_diff_list(params)


@register("diff.preview")
@register("poor-cli/previewEdit")
async def _rpc_diff_preview(ctx, params):
    return await ctx.handle_diff_preview(params)


@register("diff.stage")
@register("poor-cli/stageEdit")
async def _rpc_diff_stage(ctx, params):
    return await ctx.handle_diff_stage(params)


@register("diff.accept")
@register("poor-cli/acceptHunk")
@register("poor-cli/acceptAll")
async def _rpc_diff_accept(ctx, params):
    return await ctx.handle_diff_accept(params)


@register("diff.reject")
@register("poor-cli/rejectHunk")
@register("poor-cli/rejectAll")
async def _rpc_diff_reject(ctx, params):
    return await ctx.handle_diff_reject(params)


@register("diff.regen")
@register("poor-cli/regenerateHunk")
async def _rpc_diff_regen(ctx, params):
    return await ctx.handle_diff_regen(params)


@register("poor-cli/editList")
async def _rpc_edit_list(ctx, params):
    return await ctx.handle_edit_list(params)


@register("poor-cli/editApprove")
async def _rpc_edit_approve(ctx, params):
    return await ctx.handle_edit_approve(params)


@register("poor-cli/editReject")
async def _rpc_edit_reject(ctx, params):
    return await ctx.handle_edit_reject(params)
