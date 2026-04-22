# ruff: noqa: F403,F405
from __future__ import annotations
from poor_cli.server.chat_handler_deps import *
class ChatHandlersMixin:
    def _resolve_core(self, params: Dict[str, Any]) -> "PoorCLICore":
        """resolve the PoorCLICore for a request, supporting sessionId."""
        sid = params.get("sessionId")
        return self._session_manager.get_session(sid).core

    def _chat_request_id(self, params: Dict[str, Any]) -> str:
        """Return a stable request id string for chat logging."""
        request_id = str(params.get("requestId", "")).strip()
        if request_id:
            return request_id
        return f"chat-{uuid.uuid4().hex[:8]}"

    def _chat_context_count(self, context_files: Any) -> int:
        """Best-effort context file count for chat logging."""
        if isinstance(context_files, list):
            return len(context_files)
        return 0

    def _inline_completions_count(self, params: Dict[str, Any]) -> int:
        raw = params.get("completions_count", params.get("completionsCount", params.get("n", 1)))
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 1

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

            # wire init progress callback to push notifications to CLI.
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
            loop = asyncio.get_running_loop()
            def _stage_event(payload: Dict[str, Any]) -> None:
                async def _emit() -> None:
                    await self.write_message_stdio(JsonRpcMessage(
                        method="poor-cli/stageEvent",
                        params=payload,
                    ))
                loop.call_soon_threadsafe(lambda: asyncio.create_task(_emit()))
            self.core._diff_stage_event_callback = _stage_event
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
            await sync_provider_tool_visibility(
                core=self.core,
                initialized=self.initialized,
                permission_rules=self._permission_rules,
                logger=self.logger,
            )
            provider_info = self.core.get_provider_info()
            self._sandbox_preset = self._current_sandbox_preset()
            set_log_context(provider=provider_info.get("name"))

            # push an initialized notification so clients don't need to poll. scheduled so the initialize
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

            validate_api_key = params.get("validateApiKey", True)
            key_validity = await self._validate_api_key_async(provider_info) if validate_api_key else {
                "provider": str((provider_info or {}).get("name") or "unknown"),
                "status": "unknown",
                "reason": "skipped by client",
            }

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
                        "trustedWorkspaceBoundary": trusted_workspace_enabled(self.core),
                        "trustedRoots": [str(root) for root in trusted_workspace_roots(self.core)],
                    },
                    "repoIndex": self.core._repo_graph.get_stats() if self.core._repo_graph else None,
                    "apiKeyValidity": key_validity,
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
            # an actionable error_code so clients can show a
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

    async def _validate_api_key_async(self, provider_info: Dict[str, Any]) -> Dict[str, Any]:
        """Probe the live provider endpoint for key validity; non-blocking.

        Runs in the default executor since urllib is synchronous. Caps the
        total time via the validator's own 2s per-request timeout. Returns
        a dict like ``{"provider": "anthropic", "status": "valid", "reason": ""}``
        so the client can decide whether to prompt for re-auth.

        Auto-heal behavior: if the active key (which came from the keyring
        via the keyring→env→config lookup chain) validates as INVALID, and
        the provider's env var is set to a DIFFERENT value, we overwrite
        the keyring with the env value and re-validate once. This fixes
        the "I exported a fresh key but the stale keyring entry still wins"
        surprise without changing the lookup precedence.
        """
        try:
            from poor_cli.api_key_validator import validate, INVALID
            provider_name = str((provider_info or {}).get("name") or "").strip()
            if not provider_name:
                return {"provider": "unknown", "status": "unknown", "reason": "no provider"}
            config_manager = getattr(self.core, "_config_manager", None) or getattr(self.core, "config_manager", None)
            if config_manager is None:
                return {"provider": provider_name, "status": "unknown", "reason": "no config manager"}
            key_info = config_manager.get_api_key_info(provider_name)
            api_key = str(key_info.get("key") or "")
            if not api_key:
                # Local/keyless providers have no concept of validity;
                # mark unknown rather than invalid so the client doesn't
                # nag on ollama/vllm/hf_local.
                return {"provider": provider_name, "status": "unknown", "reason": "no key configured"}
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, validate, provider_name, api_key)
            if result.status != INVALID:
                return result.to_dict()
            # Key came up INVALID — try env-var auto-sync before giving up.
            synced = await loop.run_in_executor(None, self._try_env_keyring_sync, provider_name, api_key)
            if not synced:
                return result.to_dict()
            # Env had a different value and we wrote it to the keyring;
            # re-probe once to see if the fresh value is valid.
            retry_info = config_manager.get_api_key_info(provider_name)
            retry_key = str(retry_info.get("key") or "")
            if not retry_key or retry_key == api_key:
                return result.to_dict()
            retry_result = await loop.run_in_executor(None, validate, provider_name, retry_key)
            logger.info(
                "auto-synced %s key from env to keyring after invalid probe; new status=%s",
                provider_name, retry_result.status,
            )
            return retry_result.to_dict()
        except Exception as exc:
            logger.debug("api key validity probe failed: %s", exc)
            return {"provider": "unknown", "status": "unknown", "reason": f"probe error: {exc}"}

    def _try_env_keyring_sync(self, provider_name: str, current_key: str) -> bool:
        """Overwrite keyring with env-var value if they differ. Returns True
        if a write happened. Delegates to CredentialStore.sync_env_to_keyring.
        """
        try:
            from ...credentials import get_credential_store
            _, config = self._ensure_config_loaded()
            provider_cfg = config.model.providers.get(provider_name)
            if provider_cfg is None:
                return False
            synced = get_credential_store().sync_env_to_keyring(
                provider_name, provider_cfg.api_key_env_var, current_key,
            )
            if synced:
                config.api_keys[provider_name] = os.environ.get(provider_cfg.api_key_env_var, "")
            return synced
        except Exception as exc:
            logger.debug("env→keyring auto-sync failed: %s", exc)
            return False

    async def handle_shutdown(self, params: Dict[str, Any]) -> None:
        """Shutdown the server."""
        del params
        self.logger.info("Shutdown requested")
        # Auto-save session on shutdown for CLI restore
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
        context_files, pinned_context_files = self._context_apply_pins_and_drops(
            context_files or (),
            pinned_context_files or (),
        )
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
        completions_count = self._inline_completions_count(params)

        completions: List[str] = []
        for index in range(completions_count):
            chunks = []
            candidate_request_id = request_id if not request_id or index == 0 else f"{request_id}:{index + 1}"
            async for chunk in self.core.inline_complete(
                code_before=code_before,
                code_after=code_after,
                instruction=instruction,
                file_path=file_path,
                language=language,
                request_id=candidate_request_id,
                provider_name=provider_name,
                model_name=model_name,
            ):
                chunks.append(chunk)
                if stream_partial and completions_count == 1 and request_id:
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
            completions.append("".join(chunks))

        if stream_partial and completions_count == 1 and request_id:
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

        completion = completions[0] if completions else ""
        if completions_count == 1:
            return {"completion": completion, "isPartial": False}
        return {"completion": completion, "completions": completions, "isPartial": False}

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
