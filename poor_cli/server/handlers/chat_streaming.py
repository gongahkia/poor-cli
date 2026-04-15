# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register
from poor_cli.multiplayer_attribution import (
    attribution_explicitly_disabled,
    current_author_tag,
)


class ChatStreamingHandlersMixin:
    def _chat_author_fields(self) -> Dict[str, str]:
        if (
            not getattr(self, "_embedded_multiplayer_room", False)
            and attribution_explicitly_disabled(getattr(self, "_client_capabilities", {}))
        ):
            return {}
        return current_author_tag()

    def _with_chat_author(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tagged = dict(params)
        tagged.update(self._chat_author_fields())
        return tagged

    def _restore_edit_parent(self, params: Dict[str, Any]) -> None:
        turn_id = str(params.get("editTurnId") or params.get("edit_turn_id") or "").strip()
        if not turn_id:
            return
        store = self._branch_store()
        store.sync_from_history(self._branch_history())
        node = store.nodes.get(turn_id)
        if node is None:
            raise InvalidParamsError("edit turn not found")
        parent_id = node.parent_id
        parent = store.nodes.get(parent_id or "")
        snapshot = copy.deepcopy(parent.snapshot) if parent else []
        provider = getattr(self.core, "provider", None)
        if provider is None or not hasattr(provider, "set_history"):
            raise PoorCLIError("Provider history restore is not available")
        provider.set_history(snapshot)
        store.active_id = parent_id
        history_adapter = getattr(self.core, "history_adapter", None)
        if history_adapter is not None and hasattr(history_adapter, "set_active_leaf"):
            history_adapter.set_active_leaf(parent_id)

    async def _streaming_permission_callback(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Interactive permission callback used during streaming chat.
        Sends permissionReq notification and waits for permissionRes."""
        decision = self._evaluate_tool_access(tool_name, tool_args, preview)
        if not decision.allowed:
            if "outside trusted workspace roots" in decision.reason:
                raise_for_denial(tool_name, self.permission_mode, decision)
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if not decision.requires_approval:
            return {"allowed": True, "approvedPaths": [], "approvedChunks": []}

        if not self._client_supports("reviewFlows", "permissionRequests", default=True):
            self.logger.warning(
                "Client does not support interactive permission review; denying %s",
                tool_name,
            )
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        prompt_id = str(uuid.uuid4())
        preview = preview or {}
        notification = JsonRpcMessage(
            method="poor-cli/permissionReq",
            params=self._with_chat_author({
                "requestId": str(preview.get("requestId", "")),
                "toolName": tool_name,
                "toolArgs": tool_args,
                "promptId": prompt_id,
                "operation": str(preview.get("operation", tool_name)),
                "paths": preview.get("paths") or [],
                "diff": str(preview.get("diff", "")),
                "checkpointId": preview.get("checkpointId"),
                "changed": preview.get("changed"),
                "message": str(preview.get("message", "")),
                "capabilities": preview.get("capabilities") or decision.capabilities,
                "sandboxPreset": preview.get("sandboxPreset") or self._current_sandbox_preset(),
            }),
        )
        await self.write_message_stdio(notification)
        loop = asyncio.get_event_loop()
        future: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self._pending_permissions[prompt_id] = future
        try:
            return await asyncio.wait_for(future, timeout=300)  # 5 min timeout
        except asyncio.TimeoutError:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        finally:
            self._pending_permissions.pop(prompt_id, None)

    async def _streaming_plan_callback(self, payload: Dict[str, Any]) -> bool:
        """Interactive plan review callback used during streaming chat."""
        if not self._client_supports("reviewFlows", "planReview", default=True):
            self.logger.warning("Client does not support interactive plan review; rejecting plan")
            return False
        if hasattr(self, "_plan_board_store"):
            try:
                self._plan_board_store().seed(
                    str(payload.get("planId", "")),
                    str(payload.get("summary", "")),
                    str(payload.get("originalRequest", "")),
                    payload.get("steps") or [],
                )
            except Exception:
                self.logger.debug("plan board seed failed", exc_info=True)
        prompt_id = str(uuid.uuid4())
        notification = JsonRpcMessage(
            method="poor-cli/planReq",
            params=self._with_chat_author({
                "requestId": str(payload.get("requestId", "")),
                "promptId": prompt_id,
                "planId": str(payload.get("planId", "")),
                "summary": str(payload.get("summary", "")),
                "originalRequest": str(payload.get("originalRequest", "")),
                "steps": payload.get("steps") or [],
            }),
        )
        await self.write_message_stdio(notification)
        loop = asyncio.get_event_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending_plans[prompt_id] = future
        try:
            return await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_plans.pop(prompt_id, None)

    async def _handle_notification(self, message: JsonRpcMessage) -> None:
        """Handle incoming JSON-RPC notifications (no id)."""
        if message.method == "poor-cli/permissionRes":
            params = message.params or {}
            prompt_id = params.get("promptId", "")
            allowed = params.get("allowed", False)
            approved_paths = params.get("approvedPaths") or []
            if not isinstance(approved_paths, list):
                approved_paths = []
            approved_chunks = params.get("approvedChunks") or []
            if not isinstance(approved_chunks, list):
                approved_chunks = []
            decision = {
                "allowed": bool(allowed),
                "approvedPaths": [
                    str(path)
                    for path in approved_paths
                    if isinstance(path, str) and path
                ],
                "approvedChunks": [
                    chunk
                    for chunk in approved_chunks
                    if isinstance(chunk, dict)
                ],
            }
            future = self._pending_permissions.get(prompt_id)
            if future and not future.done():
                future.set_result(decision)
            elif not prompt_id and self._pending_permissions:
                # fallback: resolve the first pending permission
                for _pid, fut in list(self._pending_permissions.items()):
                    if not fut.done():
                        fut.set_result(decision)
                        break
        if message.method == "poor-cli/planRes":
            params = message.params or {}
            prompt_id = str(params.get("promptId", "")).strip()
            allowed = bool(params.get("allowed", False))
            future = self._pending_plans.get(prompt_id)
            if future and not future.done():
                future.set_result(allowed)
            elif not prompt_id and self._pending_plans:
                for _pid, fut in list(self._pending_plans.items()):
                    if not fut.done():
                        fut.set_result(allowed)
                        break
        if message.method == "poor-cli/toolStreamAck":
            params = message.params or {}
            session = getattr(self, "_tool_stream_session", None)
            if session is not None:
                await session.ack(
                    str(params.get("eventId", "")),
                    int(params.get("chunksProcessed", 0) or 0),
                )

    async def handle_chat_streaming(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle chat with structured CoreEvent streaming.

        Sends JSON-RPC notifications for each CoreEvent, then returns a
        final RPC result with the accumulated text.

        Permission requests are handled via the streaming permission callback
        which sends a permissionReq notification and awaits a permissionRes.
        """
        self._ensure_initialized()
        self._apply_timeline_dismissals()

        message = params.get("message", "")
        context_files = params.get("contextFiles")
        pinned_context_files = params.get("pinnedContextFiles")
        context_files, pinned_context_files = self._context_apply_pins_and_drops(
            context_files or (),
            pinned_context_files or (),
        )
        context_budget_tokens = params.get("contextBudgetTokens")
        max_response_tokens = params.get("maxResponseTokens")
        request_id = self._chat_request_id(params)
        message_text = str(message)
        context_count = self._chat_context_count(context_files) + self._chat_context_count(
            pinned_context_files
        )
        started_at = time.monotonic()
        self._restore_edit_parent(params)

        self.logger.info(
            "chat_start mode=stream request_id=%s message_chars=%d context_files=%d",
            request_id,
            len(message_text),
            context_count,
        )

        # Install interactive permission callback for this streaming session
        prev_callback = self.core.permission_callback
        prev_plan_callback = self.core.plan_callback
        self.core.permission_callback = self._streaming_permission_callback
        self.core.plan_callback = self._streaming_plan_callback
        from poor_cli.tool_stream import (
            ToolStreamSession,
            reset_tool_stream_session,
            set_tool_stream_session,
        )

        async def send_tool_chunk(payload: Dict[str, Any]) -> None:
            payload = self._with_chat_author(payload)
            event = self._timeline_store().append_chunk(
                event_id=str(payload.get("eventId", "")),
                turn_id=str(payload.get("requestId", "")),
                tool_call_id=str(payload.get("toolCallId", "")),
                tool_name=str(payload.get("toolName", "")),
                chunk=str(payload.get("chunk", "")),
            )
            await self._notify_timeline_event(event)
            await self.write_message_stdio(JsonRpcMessage(method="tool.chunk", params=payload))

        tool_stream_session = ToolStreamSession(send_tool_chunk)
        self._tool_stream_session = tool_stream_session
        stream_token = set_tool_stream_session(tool_stream_session)

        try:
            accumulated_text = ""
            with log_context(request_id=request_id):
                async for event in self.core.send_message_events(
                    message=message,
                    context_files=context_files,
                    pinned_context_files=pinned_context_files,
                    context_budget_tokens=context_budget_tokens,
                    request_id=request_id,
                    max_response_tokens=int(max_response_tokens) if max_response_tokens else None,
                ):
                    if event.type == "thinking_chunk":
                        notification = JsonRpcMessage(
                            method="poor-cli/thinkingChunk",
                            params=self._with_chat_author({
                                "requestId": request_id,
                                "chunk": event.data.get("chunk", ""),
                            }),
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "text_chunk":
                        notification = JsonRpcMessage(
                            method="poor-cli/streamChunk",
                            params=self._with_chat_author({
                                "requestId": request_id,
                                "chunk": event.data.get("chunk", ""),
                                "done": False,
                            }),
                        )
                        await self.write_message_stdio(notification)
                        accumulated_text += event.data.get("chunk", "")
                    elif event.type in ("tool_call_start", "tool_result"):
                        event_type = event.type
                        timeline_event = self._timeline_store().record_core_event(
                            request_id=request_id,
                            event_type=event_type,
                            data=event.data,
                        )
                        if timeline_event is not None:
                            await self._notify_timeline_event(timeline_event)
                        notification = JsonRpcMessage(
                            method="poor-cli/toolEvent",
                            params=self._with_chat_author({
                                "requestId": request_id,
                                "eventType": event_type,
                                "toolName": event.data.get("toolName", ""),
                                "toolArgs": event.data.get("toolArgs", {}),
                                "toolResult": event.data.get("toolResult", ""),
                                "callId": event.data.get("callId", ""),
                                "diff": event.data.get("diff", ""),
                                "paths": event.data.get("paths", []),
                                "checkpointId": event.data.get("checkpointId"),
                                "changed": event.data.get("changed"),
                                "message": event.data.get("message", ""),
                                "outputFilter": event.data.get("outputFilter", {}),
                                "originalSize": event.data.get("originalSize", 0),
                                "filteredSize": event.data.get("filteredSize", 0),
                                "iterationIndex": event.data.get("iterationIndex", 0),
                                "iterationCap": event.data.get("iterationCap", 25),
                            }),
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "permission_request":
                        pass  # handled by _streaming_permission_callback already
                    elif event.type == "plan_request":
                        pass  # handled by _streaming_plan_callback already
                    elif event.type == "cost_update":
                        cost_params = {
                            "requestId": request_id,
                            "inputTokens": event.data.get("inputTokens", 0),
                            "outputTokens": event.data.get("outputTokens", 0),
                            "estimatedCost": event.data.get("estimatedCost", 0.0),
                        }
                        for _k in ("cumulativeInputTokens", "cumulativeOutputTokens",
                                   "cacheCreationInputTokens", "cacheReadInputTokens",
                                   "systemTokens", "historyTokens", "toolResultTokens", "isEstimate",
                                   "confidencePercent", "confidenceCategory"):
                            if event.data.get(_k):
                                cost_params[_k] = event.data[_k]
                        notification = JsonRpcMessage(
                            method="poor-cli/costUpdate",
                            params=self._with_chat_author(cost_params),
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "context_pressure":
                        notification = JsonRpcMessage(
                            method="poor-cli/contextPressure",
                            params=self._with_chat_author({"requestId": request_id, **event.data}),
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "economy_turn_report":
                        notification = JsonRpcMessage(
                            method="poor-cli/economyTurnReport",
                            params=self._with_chat_author({"requestId": request_id, **event.data}),
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "progress":
                        notification = JsonRpcMessage(
                            method="poor-cli/progress",
                            params=self._with_chat_author({
                                "requestId": request_id,
                                "phase": event.data.get("phase", ""),
                                "message": event.data.get("message", ""),
                                "iterationIndex": event.data.get("iterationIndex", 0),
                                "iterationCap": event.data.get("iterationCap", 25),
                            }),
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "done":
                        done_notification = JsonRpcMessage(
                            method="poor-cli/streamChunk",
                            params=self._with_chat_author({
                                "requestId": request_id,
                                "chunk": "",
                                "done": True,
                                "reason": event.data.get("reason", "complete"),
                            }),
                        )
                        await self.write_message_stdio(done_notification)
        except Exception:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            self.logger.exception(
                "chat_error mode=stream request_id=%s duration_ms=%d",
                request_id,
                elapsed_ms,
            )
            raise
        finally:
            self.core.permission_callback = prev_callback
            self.core.plan_callback = prev_plan_callback
            reset_tool_stream_session(stream_token)
            self._tool_stream_session = None
            await tool_stream_session.close()

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        self.logger.info(
            "chat_complete mode=stream request_id=%s response_chars=%d duration_ms=%d",
            request_id,
            len(accumulated_text),
            elapsed_ms,
        )

        return {"content": accumulated_text, "role": "assistant"}

    async def handle_tool_stream_ack(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = getattr(self, "_tool_stream_session", None)
        if session is not None:
            await session.ack(
                str(params.get("eventId", "")),
                int(params.get("chunksProcessed", 0) or 0),
            )
        return {"ok": True}

    async def handle_cancel_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        event_id = str(params.get("eventId", ""))
        session = getattr(self, "_tool_stream_session", None)
        if session is None:
            cancelled = self._timeline_store().cancel(event_id)
            event = self._timeline_store().get(event_id)
            if event is not None:
                await self._notify_timeline_event(event)
            return {"cancelled": bool(cancelled)}
        cancelled = await session.cancel(event_id)
        self._timeline_store().cancel(event_id)
        event = self._timeline_store().get(event_id)
        if event is not None:
            await self._notify_timeline_event(event)
        return {"cancelled": bool(cancelled)}

@register('poor-cli/chatStreaming')
async def _rpc_99(ctx, params):
    return await ctx.handle_chat_streaming(params)


@register('poor-cli/toolStreamAck')
async def _rpc_tool_stream_ack(ctx, params):
    return await ctx.handle_tool_stream_ack(params)


@register('poor-cli/cancelTool')
async def _rpc_cancel_tool(ctx, params):
    return await ctx.handle_cancel_tool(params)
