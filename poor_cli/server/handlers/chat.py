# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ChatHandlersMixin:
    def _resolve_core(self, params: Dict[str, Any]) -> PoorCLICore:
        """resolve the PoorCLICore for a request, supporting sessionId."""
        sid = params.get("sessionId")
        return self._session_manager.get_session(sid).core

    def _chat_request_id(params: Dict[str, Any]) -> str:
        """Return a stable request id string for chat logging."""
        request_id = str(params.get("requestId", "")).strip()
        if request_id:
            return request_id
        return f"chat-{uuid.uuid4().hex[:8]}"

    def _chat_context_count(context_files: Any) -> int:
        """Best-effort context file count for chat logging."""
        if isinstance(context_files, list):
            return len(context_files)
        return 0

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize the server with provider configuration.

        Params:
            provider: Optional provider name
            model: Optional model name
            apiKey: Optional API key
            permissionMode: Optional requested approval behavior for this session

        Returns:
            Server capabilities
        """
        try:
            requested_permission_mode = params.get("permissionMode")
            if requested_permission_mode is not None:
                try:
                    self.permission_mode = parse_permission_mode(requested_permission_mode).value
                except ConfigurationError as e:
                    raise InvalidParamsError(
                        "Invalid permissionMode. "
                        "Expected one of: default, acceptEdits, plan, bypassPermissions, "
                        "dontAsk, prompt, auto-safe, danger-full-access."
                    ) from e
            requested_sandbox_preset = params.get("sandboxPreset")
            if requested_sandbox_preset is not None:
                self._sandbox_preset = normalize_preset(
                    requested_sandbox_preset,
                    fallback_permission_mode=self.permission_mode,
                )
                self.permission_mode = permission_mode_from_preset(self._sandbox_preset)

            # Client declares streaming support
            if params.get("streaming"):
                self._client_streaming = True
            self._client_capabilities = self._normalize_client_capabilities(
                params.get("clientCapabilities")
            )

            # wire init progress callback to push notifications to TUI.
            # callback may fire from executor thread (during indexing) or main
            # thread (skip path / animation frames), so we stash messages and
            # flush after initialize() returns.
            _init_progress_queue: list = []
            def _init_progress(msg: str) -> None:
                notification = JsonRpcMessage(
                    method="poor-cli/progress",
                    params={"phase": "repo_index", "message": msg},
                )
                _init_progress_queue.append(notification)
            self.core._init_progress_callback = _init_progress
            await self.core.initialize(
                provider_name=params.get("provider"),
                model_name=params.get("model"),
                api_key=params.get("apiKey"),
            )
            self.core._init_progress_callback = None
            # collect directory tree nodes for the graph overlay
            graph_nodes: list = []
            try:
                import os as _os
                cwd = _os.getcwd()
                skip = {".git", ".poor-cli", "node_modules", "__pycache__",
                        ".venv", "venv", "target", "dist", "build", ".mypy_cache"}
                entries = sorted(_os.listdir(cwd))
                dirs = [e for e in entries if _os.path.isdir(_os.path.join(cwd, e)) and e not in skip and not e.startswith(".")]
                for d in dirs[:12]:
                    sub = []
                    try:
                        sub_entries = sorted(_os.listdir(_os.path.join(cwd, d)))
                        sub = [s for s in sub_entries if not s.startswith(".") and s not in skip][:6]
                    except OSError as e:
                        logger.debug("Repo index: failed to list directory %s: %s", d, e)
                    graph_nodes.append({"name": d, "children": sub})
            except Exception as e:
                logger.debug("Repo index: graph node collection failed: %s", e)
            # inject nodes into the last progress notification
            if graph_nodes:
                _init_progress_queue.append(JsonRpcMessage(
                    method="poor-cli/progress",
                    params={"phase": "repo_index", "message": "graph_nodes", "nodes": graph_nodes},
                ))
            # flush queued progress notifications
            for notification in _init_progress_queue:
                await self.write_message_stdio(notification)
            self.initialized = True
            if self.core.config is not None:
                mode = self.core.config.security.permission_mode
                if isinstance(mode, PermissionMode):
                    self.permission_mode = mode.value
                else:
                    self.permission_mode = str(mode)
                self._sandbox_preset = normalize_preset(
                    getattr(self.core.config.sandbox, "default_preset", self._sandbox_preset),
                    fallback_permission_mode=self.permission_mode,
                )
            if requested_sandbox_preset is not None:
                self._sandbox_preset = normalize_preset(
                    requested_sandbox_preset,
                    fallback_permission_mode=self.permission_mode,
                )
                self.permission_mode = permission_mode_from_preset(self._sandbox_preset)
            await self._sync_provider_tool_visibility()
            provider_info = self.core.get_provider_info()
            self._sandbox_preset = self._current_sandbox_preset()
            set_log_context(provider=provider_info.get("name"))

            # push an initialized notification so clients (nvim onboarding,
            # lualine) don't need to poll. scheduled so the initialize
            # response sends first.
            async def _emit_initialized() -> None:
                try:
                    await self.write_message_stdio(JsonRpcMessage(
                        method="poor-cli/initialized",
                        params={"providerInfo": provider_info},
                    ))
                except Exception as exc:
                    logger.debug("emit initialized notification failed: %s", exc)
            asyncio.create_task(_emit_initialized())

            return {
                "capabilities": {
                    "completionProvider": True,
                    "inlineCompletionProvider": True,
                    "completionStreamingProvider": True,
                    "chatProvider": True,
                    "chatStreamingProvider": True,
                    "fileOperations": True,
                    "permissionMode": self.permission_mode,
                    "sandboxPreset": self._sandbox_preset,
                    "serverLogPath": os.environ.get("POOR_CLI_SERVER_LOG_FILE", ""),
                    "providerInfo": provider_info,
                    "guardedFlow": {
                        "permissionRequests": True,
                        "planReview": True,
                    },
                    "security": {
                        "trustedWorkspaceBoundary": self._trusted_workspace_enabled(),
                        "trustedRoots": [str(root) for root in self._trusted_workspace_roots()],
                    },
                    "repoIndex": self.core._repo_graph.get_stats() if self.core._repo_graph else None,
                }
            }
        except MissingAPIKeyError as e:
            # Soft-init so the onboarding wizard can call testApiKey/setApiKey.
            # Provider-dependent RPCs remain unavailable until setApiKey completes.
            self.initialized = True
            self._needs_provider_init = True
            self._pending_init_params = {
                "provider": params.get("provider"),
                "model": params.get("model"),
            }
            logger.warning("Soft-init: %s", e)
            return {
                "capabilities": {
                    "needsApiKey": True,
                    "message": str(e),
                    "serverLogPath": os.environ.get("POOR_CLI_SERVER_LOG_FILE", ""),
                }
            }
        except ConfigurationError as e:
            # Surface configuration errors (wrong provider, unavailable
            # service, bad env, etc.) as structured JSON-RPC errors with
            # an actionable error_code so the Neovim client can show a
            # meaningful message instead of a raw "exit code 143" crash.
            raise ConfigurationError(f"Initialization failed: {e}") from e
        except Exception as e:
            # Catch-all: unexpected errors during init should never crash
            # the server silently.  Return a JSON-RPC error so the client
            # surfaces the message.
            logger.exception("Unexpected error during initialization")
            raise ConfigurationError(
                f"Initialization failed unexpectedly: {e}"
            ) from e

    async def handle_shutdown(self, params: Dict[str, Any]) -> None:
        """Shutdown the server."""
        del params
        self.logger.info("Shutdown requested")
        # Auto-save session on shutdown for TUI restore
        try:
            await self.handle_save_session({})
        except Exception as e:
            self.logger.debug("Auto-save session on shutdown failed: %s", e)
        self._resolve_pending_review_requests()
        await self._shutdown_background_tasks()
        async with self._get_host_server_lock():
            await self._shutdown_host_server_locked()
        async with self._get_service_lock():
            await self._shutdown_managed_services_locked()
        await self.core.shutdown()
        self._running = False
        return None

    async def handle_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle chat message.

        Params:
            message: The message to send
            contextFiles: Optional list of file paths for context

        Returns:
            content: Response text
            role: "assistant"
        """
        self._ensure_initialized()

        message = params.get("message", "")
        context_files = params.get("contextFiles")
        pinned_context_files = params.get("pinnedContextFiles")
        context_budget_tokens = params.get("contextBudgetTokens")
        request_id = self._chat_request_id(params)
        message_text = str(message)
        context_count = self._chat_context_count(context_files) + self._chat_context_count(
            pinned_context_files
        )
        started_at = time.monotonic()

        self.logger.info(
            "chat_start mode=sync request_id=%s message_chars=%d context_files=%d",
            request_id,
            len(message_text),
            context_count,
        )

        try:
            with log_context(request_id=request_id):
                response_text = await self.core.send_message_sync(
                    message=message,
                    context_files=context_files,
                    pinned_context_files=pinned_context_files,
                    context_budget_tokens=context_budget_tokens,
                )
        except Exception:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            self.logger.exception(
                "chat_error mode=sync request_id=%s duration_ms=%d",
                request_id,
                elapsed_ms,
            )
            raise

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        self.logger.info(
            "chat_complete mode=sync request_id=%s response_chars=%d duration_ms=%d",
            request_id,
            len(response_text),
            elapsed_ms,
        )

        return {"content": response_text, "role": "assistant"}

    async def handle_inline_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle inline code completion.

        Params:
            codeBefore: Code before cursor
            codeAfter: Code after cursor
            instruction: Optional instruction
            filePath: Current file path
            language: Programming language

        Returns:
            completion: Generated code
            isPartial: Whether this is a partial result
        """
        self._ensure_initialized()

        code_before = params.get("codeBefore", "")
        code_after = params.get("codeAfter", "")
        instruction = params.get("instruction", "")
        file_path = params.get("filePath", "")
        language = params.get("language", "")
        request_id = str(params.get("requestId", "")).strip()
        provider_name = params.get("provider")
        model_name = params.get("model")
        stream_partial = bool(params.get("streamPartial", False))

        # Collect all chunks
        chunks = []
        async for chunk in self.core.inline_complete(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language,
            request_id=request_id,
            provider_name=provider_name,
            model_name=model_name,
        ):
            chunks.append(chunk)
            if stream_partial and request_id:
                await self.write_message_stdio(
                    JsonRpcMessage(
                        method="poor-cli/inlineChunk",
                        params={
                            "requestId": request_id,
                            "chunk": chunk,
                            "done": False,
                        },
                    )
                )

        if stream_partial and request_id:
            await self.write_message_stdio(
                JsonRpcMessage(
                    method="poor-cli/inlineChunk",
                    params={
                        "requestId": request_id,
                        "chunk": "",
                        "done": True,
                    },
                )
            )

        return {"completion": "".join(chunks), "isPartial": False}

    async def handle_clear_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clear conversation history.

        Returns:
            success: Always true
        """
        self._ensure_initialized()
        await self.core.clear_history()
        return {"success": True}

    async def handle_cancel_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel an in-flight agentic loop."""
        request_id = str(params.get("requestId", "")).strip()
        self.core.cancel_request(request_id)
        return {"success": True, "requestId": request_id}

@register('initialize')
async def _rpc_0(ctx, params):
    return await ctx.handle_initialize(params)

@register('shutdown')
async def _rpc_1(ctx, params):
    return await ctx.handle_shutdown(params)

@register('chat')
async def _rpc_2(ctx, params):
    return await ctx.handle_chat(params)

@register('poor-cli/chat')
async def _rpc_16(ctx, params):
    return await ctx.handle_chat(params)

@register('poor-cli/inlineComplete')
async def _rpc_17(ctx, params):
    return await ctx.handle_inline_complete(params)

@register('poor-cli/clearHistory')
async def _rpc_31(ctx, params):
    return await ctx.handle_clear_history(params)

@register('poor-cli/cancelRequest')
async def _rpc_98(ctx, params):
    return await ctx.handle_cancel_request(params)
