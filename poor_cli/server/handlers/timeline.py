# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register
from poor_cli.tool_events import TimelineStore, strip_dismissed_results_from_history


class TimelineHandlersMixin:
    def _timeline_store(self) -> TimelineStore:
        store = getattr(self, "_tool_events", None)
        if store is None:
            store = TimelineStore()
            self._tool_events = store
        return store

    async def _notify_timeline_event(self, event: Any) -> None:
        try:
            await self.write_message_stdio(
                JsonRpcMessage(
                    method="poor-cli/timelineEvent",
                    params=event.to_dict(include_full=True),
                )
            )
        except Exception:
            self.logger.debug("timeline notify failed", exc_info=True)

    async def handle_timeline_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        turn_id = params.get("turnId") or params.get("turn_id")
        limit = int(params.get("limit", 200) or 200)
        events = self._timeline_store().list(turn_id=str(turn_id) if turn_id else None, limit=limit)
        return {"events": [event.to_dict(include_full=True) for event in events]}

    async def handle_timeline_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        event_id = str(params.get("eventId") or params.get("event_id") or "")
        cancelled = False
        session = getattr(self, "_tool_stream_session", None)
        if session is not None:
            cancelled = bool(await session.cancel(event_id))
        cancelled = self._timeline_store().cancel(event_id) or cancelled
        event = self._timeline_store().get(event_id)
        if event is not None:
            await self._notify_timeline_event(event)
        return {"cancelled": bool(cancelled)}

    async def handle_timeline_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        event_id = str(params.get("eventId") or params.get("event_id") or "")
        event = self._timeline_store().get(event_id)
        if event is None:
            return {"newEventId": "", "ok": False, "error": "event not found"}
        new_event = self._timeline_store().running(
            turn_id=event.turn_id,
            tool_name=event.tool_name,
            args=dict(event.args_full),
            tool_call_id=str(uuid.uuid4()),
        )
        await self._notify_timeline_event(new_event)
        try:
            result = await self.core.execute_tool_raw(event.tool_name, dict(event.args_full))
            result_text = self.core._tool_result_text(result)
            new_event.finish("done", result_text)
        except Exception as exc:
            new_event.finish("failed", "", str(exc))
        await self._notify_timeline_event(new_event)
        return {"newEventId": new_event.event_id, "ok": new_event.status == "done"}

    async def handle_timeline_dismiss(self, params: Dict[str, Any]) -> Dict[str, Any]:
        event_id = str(params.get("eventId") or params.get("event_id") or "")
        ok = self._timeline_store().dismiss(event_id)
        self._apply_timeline_dismissals()
        event = self._timeline_store().get(event_id)
        if event is not None:
            await self._notify_timeline_event(event)
        return {"ok": bool(ok)}

    def _apply_timeline_dismissals(self) -> None:
        provider = getattr(self.core, "provider", None)
        if provider is None or not hasattr(provider, "get_history") or not hasattr(provider, "set_history"):
            return
        history = provider.get_history()
        cleaned = strip_dismissed_results_from_history(history, self._timeline_store().dismissed_events())
        provider.set_history(cleaned)


@register("timeline.list")
async def _rpc_timeline_list(ctx, params):
    return await ctx.handle_timeline_list(params)


@register("timeline.cancel")
async def _rpc_timeline_cancel(ctx, params):
    return await ctx.handle_timeline_cancel(params)


@register("timeline.retry")
async def _rpc_timeline_retry(ctx, params):
    return await ctx.handle_timeline_retry(params)


@register("timeline.dismiss")
async def _rpc_timeline_dismiss(ctx, params):
    return await ctx.handle_timeline_dismiss(params)
