# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.multiplayer_voting import HunkVoteNotApprovedError, VoteStatus
from poor_cli.server.registry import register


class DiffReviewHandlersMixin:
    def _edit_stage(self):
        self._ensure_initialized()
        registry = getattr(self.core, "tool_registry", None)
        stage = getattr(registry, "edit_stage", None)
        if stage is None:
            raise PoorCLIError("Diff review store not available")
        return stage

    def _diff_vote_room(self):
        room = getattr(self, "_multiplayer_room", None)
        if room is None or not room.session.diff_voting_enabled():
            return None
        return room

    def _diff_vote_ledger(self, edit_id: str, *, create: bool = False):
        room = self._diff_vote_room()
        if room is None:
            return None
        if create:
            return room.session.ensure_vote_ledger(edit_id)
        return room.session.get_vote_ledger(edit_id)

    def _decorate_vote_payload(self, edit: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(edit.get("editId") or edit.get("edit_id") or "").strip()
        ledger = self._diff_vote_ledger(edit_id)
        if ledger is None:
            return edit
        for hunk in edit.get("hunks", []):
            if not isinstance(hunk, dict):
                continue
            hunk_id = str(hunk.get("hunkId") or hunk.get("hunk_id") or "").strip()
            if not hunk_id:
                continue
            payload = ledger.payload_for(hunk_id)
            hunk["votes"] = payload["votes"]
            hunk["voteStatus"] = payload["status"]
            hunk["voteThreshold"] = payload["threshold"]
        return edit

    def _require_hunk_vote_approved(self, edit_id: str, hunk_id: str) -> None:
        room = self._diff_vote_room()
        if room is None or room.session.diff_voting_threshold() == "owner_only":
            return
        ledger = room.session.get_vote_ledger(edit_id)
        if ledger is None or ledger.status(hunk_id) != VoteStatus.APPROVED:
            raise HunkVoteNotApprovedError("HunkVoteNotApproved")

    async def _emit_edit_committed(self, payload: Dict[str, Any]) -> None:
        try:
            await self.write_message_stdio(JsonRpcMessage(
                method="poor-cli/editCommitted",
                params=payload,
            ))
        except Exception as e:
            logger.debug("emit editCommitted failed: %s", e)

    async def handle_diff_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"edits": [self._decorate_vote_payload(edit) for edit in self._edit_stage().list_pending()]}

    async def handle_diff_preview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        return self._decorate_vote_payload(self._edit_stage().preview_edit(edit_id))

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
        edit_id = str(edit.get("editId") or edit.get("edit_id") or "").strip()
        if self._diff_vote_room() is not None:
            self._diff_vote_ledger(edit_id, create=True)
            edit = self._decorate_vote_payload(edit)
        try:
            await self.write_message_stdio(JsonRpcMessage(
                method="poor-cli/stageEvent",
                params=edit,
            ))
        except Exception as e:
            logger.debug("emit stageEvent failed: %s", e)
        return edit

    async def handle_diff_accept(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        stage = self._edit_stage()
        if hunk_id:
            self._require_hunk_vote_approved(edit_id, hunk_id)
            return self._decorate_vote_payload(stage.accept_hunk(edit_id, hunk_id))
        room = self._diff_vote_room()
        if room is not None and room.session.diff_voting_threshold() != "owner_only":
            edit = stage.preview_edit(edit_id)
            ledger = room.session.get_vote_ledger(edit_id)
            for hunk in edit.get("hunks", []):
                if not isinstance(hunk, dict):
                    continue
                candidate_hunk_id = str(hunk.get("hunkId") or hunk.get("hunk_id") or "").strip()
                if candidate_hunk_id and ledger is not None and ledger.status(candidate_hunk_id) == VoteStatus.APPROVED:
                    stage.accept_hunk(edit_id, candidate_hunk_id)
            result = stage.finalize(edit_id, checkpoint_manager=self.core.checkpoint_manager)
        else:
            result = stage.accept_all(edit_id, checkpoint_manager=self.core.checkpoint_manager)
        result = self._decorate_vote_payload(result)
        await self._emit_edit_committed(result)
        return result

    async def handle_diff_reject(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        if not edit_id:
            raise InvalidParamsError("editId is required")
        stage = self._edit_stage()
        if hunk_id:
            return self._decorate_vote_payload(stage.reject_hunk(edit_id, hunk_id))
        result = stage.reject_all(edit_id)
        result = self._decorate_vote_payload(result)
        await self._emit_edit_committed(result)
        return result

    async def handle_diff_regen(self, params: Dict[str, Any]) -> Dict[str, Any]:
        edit_id = str(params.get("editId") or params.get("edit_id") or "").strip()
        hunk_id = str(params.get("hunkId") or params.get("hunk_id") or "").strip()
        new_content = str(params.get("newContent") or params.get("new_content") or "")
        if not edit_id or not hunk_id:
            raise InvalidParamsError("editId and hunkId are required")
        return self._decorate_vote_payload(self._edit_stage().regenerate_hunk(edit_id, hunk_id, new_content))


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
