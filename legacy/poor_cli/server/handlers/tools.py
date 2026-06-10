# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ToolsHandlersMixin:
    def _trusted_workspace_enabled(self) -> bool:
        security_cfg = getattr(getattr(self.core, "config", None), "security", None)
        if security_cfg is None:
            return True
        return bool(getattr(security_cfg, "enforce_trusted_workspace", True))

    def _trusted_workspace_roots(self) -> List[Path]:
        security_cfg = getattr(getattr(self.core, "config", None), "security", None)
        roots: List[Path] = []
        raw_roots = getattr(security_cfg, "trusted_roots", []) if security_cfg is not None else []
        if isinstance(raw_roots, list):
            for raw_root in raw_roots:
                if not isinstance(raw_root, str) or not raw_root.strip():
                    continue
                root_path = Path(raw_root).expanduser()
                if not root_path.is_absolute():
                    root_path = Path.cwd() / root_path
                roots.append(root_path.resolve())
        if not roots:
            roots.append(Path.cwd().resolve())

        deduped: List[Path] = []
        seen = set()
        for root in roots:
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root)
        return deduped

    def _path_is_within_root(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    def _path_is_trusted(self, raw_path: str) -> bool:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        return any(
            self._path_is_within_root(resolved, root)
            for root in self._trusted_workspace_roots()
        )

    def _trusted_workspace_reason(self) -> str:
        roots = ", ".join(str(root) for root in self._trusted_workspace_roots())
        return f"requested mutation falls outside trusted workspace roots ({roots})"

    def _mutation_paths_for_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        preview = preview or {}
        key_map = {
            "write_file": ("file_path",),
            "edit_file": ("file_path",),
            "delete_file": ("file_path",),
            "copy_file": ("source", "destination"),
            "move_file": ("source", "destination"),
            "create_directory": ("path",),
            "json_yaml_edit": ("file_path",),
            "format_and_lint": ("path",),
        }
        if tool_name == "apply_patch_unified":
            preview_paths = preview.get("paths")
            if isinstance(preview_paths, list):
                return [str(path).strip() for path in preview_paths if str(path).strip()]
            base_path = str(tool_args.get("path", "")).strip()
            return [base_path] if base_path else []

        keys = key_map.get(tool_name, ())
        paths: List[str] = []
        for key in keys:
            value = tool_args.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
        return paths

    def _ensure_tool_paths_are_trusted(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._trusted_workspace_enabled():
            return
        for path in self._mutation_paths_for_tool(tool_name, tool_args, preview):
            if not self._path_is_trusted(path):
                raise PermissionDeniedError(
                    tool_name=tool_name,
                    permission_mode=self.permission_mode,
                    reason=self._trusted_workspace_reason(),
                )

    def _tool_capabilities(self, tool_name: str) -> List[str]:
        registry = getattr(self.core, "tool_registry", None)
        if registry is None:
            from .tools_async import DEFAULT_TOOL_CAPABILITIES

            return list(DEFAULT_TOOL_CAPABILITIES.get(tool_name, []))
        try:
            return registry.get_tool_capabilities(tool_name)
        except Exception as e:
            logger.debug("Tool registry lookup failed for %s, using defaults: %s", tool_name, e)
            from .tools_async import DEFAULT_TOOL_CAPABILITIES

            return list(DEFAULT_TOOL_CAPABILITIES.get(tool_name, []))

    def _hidden_tool_names(self) -> Set[str]:
        hidden: Set[str] = set()
        for declaration in self.core.get_available_tools():
            tool_name = str(declaration.get("name") or "").strip().lower()
            if not tool_name:
                continue
            if self._permission_rules.is_tool_blanket_denied(tool_name):
                hidden.add(tool_name)
        return hidden

    def _visible_tool_declarations(self) -> List[Dict[str, Any]]:
        declarations = self.core.get_available_tools()
        hidden = self._hidden_tool_names()
        if not hidden:
            return declarations
        visible: List[Dict[str, Any]] = []
        for declaration in declarations:
            tool_name = str(declaration.get("name") or "").strip().lower()
            if tool_name and tool_name in hidden:
                continue
            visible.append(declaration)
        return visible

    async def _sync_provider_tool_visibility(self) -> None:
        if not self.initialized:
            return
        try:
            await self.core.refresh_provider_tools(self._visible_tool_declarations())
        except Exception as error:
            self.logger.warning("Failed to sync provider tool visibility: %s", error)

    def _evaluate_tool_access(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ):
        rule_match = self._permission_rules.evaluate(tool_name, tool_args)
        if rule_match is not None and rule_match.behavior == "deny":
            capabilities = self._tool_capabilities(tool_name)
            return SandboxDecision(
                allowed=False,
                reason=f"denied by permission rule ({rule_match.rule.source}:{rule_match.rule.rule_content or '*'})",
                requires_approval=False,
                capabilities=capabilities,
            )

        mutation_paths = list(preview.get("paths") or []) if isinstance(preview, dict) else []
        if not mutation_paths:
            mutation_paths = self._mutation_paths_for_tool(tool_name, tool_args, preview)
        decision = evaluate_tool_access(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_capabilities=self._tool_capabilities(tool_name),
            permission_mode=self.permission_mode,
            sandbox_preset=self._current_sandbox_preset(),
            trusted_roots=self._trusted_workspace_roots(),
            mutation_paths=mutation_paths,
            enforce_trusted_workspace=self._trusted_workspace_enabled(),
            safe_process_commands=getattr(
                getattr(getattr(self.core, "config", None), "security", None),
                "safe_commands",
                None,
            ),
        )

        if decision.allowed and rule_match is not None:
            if rule_match.behavior == "allow":
                decision = SandboxDecision(
                    allowed=True,
                    reason=f"allowed by permission rule ({rule_match.rule.source}:{rule_match.rule.rule_content or '*'})",
                    requires_approval=False,
                    capabilities=decision.capabilities,
                )
            elif rule_match.behavior == "ask":
                decision = SandboxDecision(
                    allowed=True,
                    reason=f"requires approval by permission rule ({rule_match.rule.source}:{rule_match.rule.rule_content or '*'})",
                    requires_approval=True,
                    capabilities=decision.capabilities,
                )

        if preview is not None and isinstance(preview, dict):
            preview["capabilities"] = decision.capabilities
            preview["sandboxPreset"] = self._current_sandbox_preset()
            if rule_match is not None:
                preview["permissionRule"] = rule_match.to_dict()
            if not preview.get("message"):
                capability_text = summarize_capabilities(decision.capabilities)
                preview["message"] = (
                    decision.reason
                    if decision.reason
                    else f"Requires {capability_text} under `{self._current_sandbox_preset()}`"
                )
        return decision

    def _auto_safe_bash_allowed(self, tool_args: Dict[str, Any]) -> bool:
        command = str(tool_args.get("command", "")).strip()
        if not command:
            return False
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv:
            return False

        validation = get_command_validator(strict_mode=False).validate(command)
        if validation.risk_level != CommandRisk.SAFE:
            return False

        security_cfg = getattr(getattr(self.core, "config", None), "security", None)
        raw_safe_commands = getattr(security_cfg, "safe_commands", []) if security_cfg is not None else []
        safe_commands = {
            str(entry).strip()
            for entry in raw_safe_commands
            if isinstance(entry, str) and str(entry).strip()
        }
        if argv[0] in safe_commands:
            return True
        if len(argv) >= 2 and " ".join(argv[:2]) in safe_commands:
            return True
        return command in safe_commands

    async def _enforce_server_tool_permission(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> None:
        """Apply configured server permission policy for direct tool handlers."""
        callback = self.core.permission_callback
        if callback is None:
            return

        permission_result = await callback(tool_name, tool_args)
        if isinstance(permission_result, dict):
            permitted = bool(permission_result.get("allowed", False))
        else:
            permitted = bool(permission_result)

        if not permitted:
            raise PermissionDeniedError(tool_name=tool_name, permission_mode=self.permission_mode)

    async def handle_apply_edit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a code edit.

        Params:
            filePath: File to edit
            oldText: Text to replace
            newText: Replacement text

        Returns:
            success: Whether the edit succeeded
            message: Result message
        """
        self._ensure_initialized()

        file_path = params.get("filePath", "")
        old_text = params.get("oldText", "")
        new_text = params.get("newText", "")

        await self._enforce_server_tool_permission(
            "edit_file",
            {
                "file_path": file_path,
                "old_text": old_text,
                "new_text": new_text,
            },
        )

        outcome = await self.core.apply_edit_outcome(
            file_path=file_path, old_text=old_text, new_text=new_text
        )
        payload = outcome.to_dict()
        payload["success"] = outcome.ok
        payload["checkpointId"] = outcome.checkpoint_id
        return payload

    async def handle_read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read a file.

        Params:
            filePath: File to read
            startLine: Optional start line
            endLine: Optional end line

        Returns:
            content: File contents
        """
        self._ensure_initialized()

        file_path = params.get("filePath", "")
        start_line = params.get("startLine")
        end_line = params.get("endLine")

        content = await self.core.read_file(
            file_path=file_path, start_line=start_line, end_line=end_line
        )

        return {"content": content}

    async def handle_execute_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a shell command.

        Params:
            command: Command to execute
            timeout: Optional timeout in seconds (default 60, max 3600)

        Returns:
            output: Command output
            exitCode: Exit code (always 0 for now)
        """
        self._ensure_initialized()

        command = params.get("command", "")
        timeout = params.get("timeout")
        if timeout is not None:
            try:
                timeout = int(timeout)
            except (TypeError, ValueError) as e:
                raise InvalidParamsError("timeout must be an integer") from e
            timeout = max(1, min(timeout, 3600))

        tool_args = {"command": command}
        if timeout is not None:
            tool_args["timeout"] = timeout

        with log_context(tool_name="bash"):
            await self._enforce_server_tool_permission("bash", tool_args)
            result = await self.core.execute_tool("bash", tool_args)

        return {"output": result, "exitCode": 0}

    async def handle_get_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get available tools.

        Returns:
            tools: List of tool declarations
        """
        self._ensure_initialized()
        del params

        hidden = sorted(self._hidden_tool_names())
        return {
            "tools": self._visible_tool_declarations(),
            "hiddenTools": hidden,
        }

    async def handle_tool_full_output(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        call_id = str(params.get("callId", "") or "").strip()
        if not call_id:
            raise InvalidParamsError("callId is required")
        payload = self.core.get_tool_full_output(call_id)
        if not payload:
            return {"callId": call_id, "output": "", "found": False}
        payload["found"] = True
        return payload

    async def handle_exec(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run a headless chat request via the shared core engine."""
        self._ensure_initialized()

        prompt = str(params.get("prompt", "") or "")
        if not prompt.strip():
            raise InvalidParamsError("prompt is required")

        output_format = str(params.get("outputFormat", "text") or "text").strip().lower()
        if output_format not in {"text", "json"}:
            raise InvalidParamsError("outputFormat must be one of: text, json")

        context_files = params.get("contextFiles")
        if not isinstance(context_files, list):
            context_files = None
        pinned_context_files = params.get("pinnedContextFiles")
        if not isinstance(pinned_context_files, list):
            pinned_context_files = None
        context_budget_tokens = params.get("contextBudgetTokens")
        if context_budget_tokens is not None:
            try:
                context_budget_tokens = int(context_budget_tokens)
            except (TypeError, ValueError) as e:
                raise InvalidParamsError("contextBudgetTokens must be an integer") from e

        routing_mode = str(params.get("routingMode", "") or "").strip()
        if routing_mode:
            self.core.set_routing_mode(routing_mode)

        response_text = await self.core.send_message_sync(
            message=prompt,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            source_kind="exec",
            source_id="rpc-exec",
            run_metadata={"rpcMethod": "poor-cli/exec"},
        )
        if output_format == "json":
            return {
                "content": response_text,
                "provider": self.core.get_provider_info(),
                "outputFormat": output_format,
                "cost": self.core.get_session_cost_summary(),
                "statusView": self._status_view_payload(),
            }
        return {"content": response_text, "outputFormat": output_format}

    async def handle_get_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..completion import CompletionEngine, CompletionRequest
        engine = CompletionEngine()
        req = CompletionRequest(
            file_path=str(params.get("filePath", "")),
            line=int(params.get("line", 0)),
            column=int(params.get("column", 0)),
            prefix=str(params.get("prefix", "")),
            suffix=str(params.get("suffix", "")),
            language=str(params.get("language", "")),
        )
        session = self._session_manager.get_session(params.get("sessionId"))
        provider = session.core.provider if session.core._initialized else None
        result = await engine.complete(req, provider=provider)
        return {"completion": result.to_dict()}

@register('poor-cli/applyEdit')
async def _rpc_18(ctx, params):
    return await ctx.handle_apply_edit(params)

@register('poor-cli/readFile')
async def _rpc_19(ctx, params):
    return await ctx.handle_read_file(params)

@register('poor-cli/executeCommand')
async def _rpc_20(ctx, params):
    return await ctx.handle_execute_command(params)

@register('poor-cli/getTools')
async def _rpc_21(ctx, params):
    return await ctx.handle_get_tools(params)

@register('poor-cli/toolFullOutput')
async def _rpc_tool_full_output(ctx, params):
    return await ctx.handle_tool_full_output(params)

@register('poor-cli/exec')
async def _rpc_36(ctx, params):
    return await ctx.handle_exec(params)

@register('poor-cli/getCompletion')
async def _rpc_134(ctx, params):
    return await ctx.handle_get_completion(params)
