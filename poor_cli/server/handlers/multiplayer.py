# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class MultiplayerHandlersMixin:
    def _multiplayer_store(self) -> MultiplayerStore:
        store = getattr(self, "_multiplayer_store", None)
        if store is None:
            store = MultiplayerStore(Path.cwd())
            self._multiplayer_store = store
        return store

    def _multiplayer_snapshot(self) -> Dict[str, Any]:
        store = self._multiplayer_store()
        return {
            "participants": [
                participant.to_dict()
                for participant in store.list_participants()
            ],
            "queue": [
                item.to_dict()
                for item in store.list_queue(statuses=["queued", "running"])
            ],
            "threads": [
                thread.to_dict()
                for thread in store.list_threads()
            ],
            "approvalTemplates": [
                template.to_dict()
                for template in store.list_approval_templates()
            ],
        }

    async def handle_multiplayer_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        return self._multiplayer_snapshot()

    async def handle_multiplayer_host(self, params: Dict[str, Any]) -> Dict[str, Any]:
        participant = self._multiplayer_store().host_session(
            str(params.get("displayName") or params.get("display_name") or "Host")
        )
        return {"participant": participant.to_dict()}

    async def handle_multiplayer_join(self, params: Dict[str, Any]) -> Dict[str, Any]:
        participant = self._multiplayer_store().join_session(
            str(params.get("displayName") or params.get("display_name") or "Peer")
        )
        return {"participant": participant.to_dict()}

    async def handle_multiplayer_list_participants(self, params: Dict[str, Any]) -> Dict[str, Any]:
        participants = self._multiplayer_store().list_participants(
            include_removed=bool(params.get("includeRemoved", False))
        )
        return {"participants": [participant.to_dict() for participant in participants]}

    async def handle_multiplayer_remove_participant(self, params: Dict[str, Any]) -> Dict[str, Any]:
        participant = self._multiplayer_store().remove_participant(
            str(params.get("actorId") or params.get("actor_id") or ""),
            str(params.get("participantId") or params.get("participant_id") or ""),
        )
        return {"participant": participant.to_dict()}

    async def handle_multiplayer_enqueue_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        item = self._multiplayer_store().enqueue_prompt(
            str(params.get("authorId") or params.get("author_id") or ""),
            str(params.get("prompt") or ""),
        )
        return {"item": item.to_dict()}

    async def handle_multiplayer_list_queue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        statuses = params.get("statuses")
        if statuses is not None and not isinstance(statuses, list):
            raise InvalidParamsError("statuses must be an array")
        items = self._multiplayer_store().list_queue(
            statuses=[str(status) for status in statuses] if statuses else None
        )
        return {"items": [item.to_dict() for item in items]}

    async def handle_multiplayer_update_queued_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        item = self._multiplayer_store().update_queued_prompt(
            str(params.get("actorId") or params.get("actor_id") or ""),
            str(params.get("itemId") or params.get("item_id") or ""),
            str(params.get("prompt") or ""),
        )
        return {"item": item.to_dict()}

    async def handle_multiplayer_move_queue_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        item = self._multiplayer_store().move_queue_item(
            str(params.get("actorId") or params.get("actor_id") or ""),
            str(params.get("itemId") or params.get("item_id") or ""),
            str(params.get("direction") or ""),
        )
        return {"item": item.to_dict()}

    async def handle_multiplayer_cancel_queue_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        item = self._multiplayer_store().cancel_queue_item(
            str(params.get("actorId") or params.get("actor_id") or ""),
            str(params.get("itemId") or params.get("item_id") or ""),
        )
        return {"item": item.to_dict()}

    async def handle_multiplayer_create_thread(self, params: Dict[str, Any]) -> Dict[str, Any]:
        metadata = params.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise InvalidParamsError("metadata must be an object")
        thread = self._multiplayer_store().create_thread(
            str(params.get("creatorId") or params.get("creator_id") or ""),
            str(params.get("title") or ""),
            str(params.get("description") or ""),
            metadata=metadata,
        )
        return {"thread": thread.to_dict()}

    async def handle_multiplayer_list_threads(self, params: Dict[str, Any]) -> Dict[str, Any]:
        statuses = params.get("statuses")
        if statuses is not None and not isinstance(statuses, list):
            raise InvalidParamsError("statuses must be an array")
        threads = self._multiplayer_store().list_threads(
            statuses=[str(status) for status in statuses] if statuses else None
        )
        return {"threads": [thread.to_dict() for thread in threads]}

    async def handle_multiplayer_add_thread_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        metadata = params.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise InvalidParamsError("metadata must be an object")
        event = self._multiplayer_store().add_thread_event(
            str(params.get("threadId") or params.get("thread_id") or ""),
            str(params.get("authorId") or params.get("author_id") or ""),
            str(params.get("eventType") or params.get("event_type") or "comment"),
            str(params.get("content") or ""),
            metadata=metadata,
        )
        return {"event": event}

    async def handle_multiplayer_create_merge_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        merge = self._multiplayer_store().create_merge_request(
            str(params.get("threadId") or params.get("thread_id") or ""),
            str(params.get("authorId") or params.get("author_id") or ""),
            str(params.get("summary") or ""),
            context_summary=str(params.get("contextSummary") or params.get("context_summary") or ""),
            workspace_diff=str(params.get("workspaceDiff") or params.get("workspace_diff") or ""),
            template_id=str(params.get("templateId") or params.get("template_id") or ""),
        )
        return {"merge": merge.to_dict()}

    async def handle_multiplayer_merge_thread(self, params: Dict[str, Any]) -> Dict[str, Any]:
        merge = self._multiplayer_store().merge_thread(
            str(params.get("actorId") or params.get("actor_id") or ""),
            str(params.get("mergeId") or params.get("merge_id") or ""),
        )
        return {"merge": merge.to_dict()}

    async def handle_multiplayer_set_approval_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        applies_to = params.get("appliesTo") or params.get("applies_to")
        required_people = params.get("requiredPeople") or params.get("required_people") or []
        if not isinstance(applies_to, list):
            raise InvalidParamsError("appliesTo must be an array")
        if not isinstance(required_people, list):
            raise InvalidParamsError("requiredPeople must be an array")
        template = self._multiplayer_store().upsert_approval_template(
            str(params.get("actorId") or params.get("actor_id") or ""),
            str(params.get("name") or ""),
            [str(item) for item in applies_to],
            required_count=int(params.get("requiredCount") or params.get("required_count") or 1),
            required_people=[str(item) for item in required_people],
            template_id=str(params.get("templateId") or params.get("template_id") or ""),
        )
        return {"template": template.to_dict()}

    async def handle_multiplayer_list_approval_templates(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        templates = self._multiplayer_store().list_approval_templates()
        return {"templates": [template.to_dict() for template in templates]}

    async def handle_multiplayer_record_approval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        approval = self._multiplayer_store().record_approval(
            str(params.get("participantId") or params.get("participant_id") or ""),
            str(params.get("targetType") or params.get("target_type") or ""),
            str(params.get("targetId") or params.get("target_id") or ""),
            str(params.get("templateId") or params.get("template_id") or ""),
            decision=str(params.get("decision") or "approved"),
        )
        return {"approval": approval}

    async def handle_multiplayer_approval_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._multiplayer_store().approval_status(
            str(params.get("targetType") or params.get("target_type") or ""),
            str(params.get("targetId") or params.get("target_id") or ""),
            str(params.get("templateId") or params.get("template_id") or ""),
        )


@register("multiplayer.host")
async def _rpc_multiplayer_host(ctx, params):
    return await ctx.handle_multiplayer_host(params)


@register("multiplayer.snapshot")
async def _rpc_multiplayer_snapshot(ctx, params):
    return await ctx.handle_multiplayer_snapshot(params)


@register("multiplayer.join")
async def _rpc_multiplayer_join(ctx, params):
    return await ctx.handle_multiplayer_join(params)


@register("multiplayer.participants")
async def _rpc_multiplayer_participants(ctx, params):
    return await ctx.handle_multiplayer_list_participants(params)


@register("multiplayer.removeParticipant")
async def _rpc_multiplayer_remove_participant(ctx, params):
    return await ctx.handle_multiplayer_remove_participant(params)


@register("multiplayer.queue.enqueue")
async def _rpc_multiplayer_queue_enqueue(ctx, params):
    return await ctx.handle_multiplayer_enqueue_prompt(params)


@register("multiplayer.queue.list")
async def _rpc_multiplayer_queue_list(ctx, params):
    return await ctx.handle_multiplayer_list_queue(params)


@register("multiplayer.queue.update")
async def _rpc_multiplayer_queue_update(ctx, params):
    return await ctx.handle_multiplayer_update_queued_prompt(params)


@register("multiplayer.queue.move")
async def _rpc_multiplayer_queue_move(ctx, params):
    return await ctx.handle_multiplayer_move_queue_item(params)


@register("multiplayer.queue.cancel")
async def _rpc_multiplayer_queue_cancel(ctx, params):
    return await ctx.handle_multiplayer_cancel_queue_item(params)


@register("multiplayer.thread.create")
async def _rpc_multiplayer_thread_create(ctx, params):
    return await ctx.handle_multiplayer_create_thread(params)


@register("multiplayer.thread.list")
async def _rpc_multiplayer_thread_list(ctx, params):
    return await ctx.handle_multiplayer_list_threads(params)


@register("multiplayer.thread.event")
async def _rpc_multiplayer_thread_event(ctx, params):
    return await ctx.handle_multiplayer_add_thread_event(params)


@register("multiplayer.merge.create")
async def _rpc_multiplayer_merge_create(ctx, params):
    return await ctx.handle_multiplayer_create_merge_request(params)


@register("multiplayer.merge.apply")
async def _rpc_multiplayer_merge_apply(ctx, params):
    return await ctx.handle_multiplayer_merge_thread(params)


@register("multiplayer.template.set")
async def _rpc_multiplayer_template_set(ctx, params):
    return await ctx.handle_multiplayer_set_approval_template(params)


@register("multiplayer.template.list")
async def _rpc_multiplayer_template_list(ctx, params):
    return await ctx.handle_multiplayer_list_approval_templates(params)


@register("multiplayer.approval.record")
async def _rpc_multiplayer_approval_record(ctx, params):
    return await ctx.handle_multiplayer_record_approval(params)


@register("multiplayer.approval.status")
async def _rpc_multiplayer_approval_status(ctx, params):
    return await ctx.handle_multiplayer_approval_status(params)
