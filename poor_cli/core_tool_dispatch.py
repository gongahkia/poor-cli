"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine used by the PoorCLI terminal client and
the Neovim plugin.
"""

import asyncio
import difflib
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .audit_log import AuditEventType, AuditSeverity
from .providers.base import ProviderResponse, FunctionCall
from .providers.capability import ProviderCapability, provider_has_capability
from .tools_async import FilteredToolResult, ToolOutcome
from .enhanced_tools import CORE_TOOL_GROUP, MCP_GROUP_PREFIX, EnhancedToolRegistry
from .core_events import CoreEvent
from .instructions import InstructionManager, InstructionSnapshot
from .mcp_client import MCPManager
from .economy import (
    resolve_output_verbosity,
)
from .skills import InstructionSkillContext, SkillLoadPlan
from .exceptions import (
    PoorCLIError,
    setup_logger,
)

logger = setup_logger(__name__)

_DEFAULT_CONFIDENCE_PERCENT = 50
_CONFIDENCE_PERCENT_RE = re.compile(r"confidence[^\n\r]*?(\d{1,3})\s*%", re.IGNORECASE)
_CONFIDENCE_LINE_RE = re.compile(r"^confidence\b[^\n\r]*$", re.IGNORECASE)
_CONFIDENCE_BANDS: Tuple[Tuple[int, str], ...] = (
    (20, "Very Low"),
    (40, "Low"),
    (60, "Moderate"),
    (80, "High"),
    (100, "Very High"),
)
_MUTATING_TOOLS = {
    "write_file",
    "edit_file",
    "delete_file",
    "apply_patch_unified",
    "json_yaml_edit",
}
_MAX_RUN_TRANSITIONS = 160
_MAX_RUN_TURN_SUMMARIES = 80


# ── CoreEvent: structured events yielded by the agentic loop ─────────





class ToolDispatcher:
    def _mcp_server_names(self) -> List[str]:
        if self._mcp_manager is None or not hasattr(self._mcp_manager, "get_server_names"):
            return []
        return self._mcp_manager.get_server_names()

    def _register_mcp_tool_declarations(self, declarations: List[Dict[str, Any]]) -> None:
        if not declarations or not self.tool_registry or not self._mcp_manager:
            return
        for declaration in declarations:
            tool_name = declaration.get("name")
            if not tool_name:
                continue

            async def _call_mcp_tool(
                _tool_name: str = str(tool_name),
                **kwargs: Any,
            ) -> str:
                if not self._mcp_manager:
                    raise PoorCLIError("MCP manager not initialized")
                return await self._mcp_manager.execute_tool(_tool_name, kwargs)

            self.tool_registry.register_external_tool(
                str(tool_name),
                _call_mcp_tool,
                declaration,
            )

    async def _resolve_tool_declarations_for_groups(
        self,
        groups: List[str],
    ) -> List[Dict[str, Any]]:
        if not isinstance(self.tool_registry, EnhancedToolRegistry):
            return self.tool_registry.get_tool_declarations() if self.tool_registry else []

        builtin = self.tool_registry.get_tool_declarations_for_groups(
            groups,
            mcp_server_names=self._mcp_server_names(),
        )
        declarations: List[Dict[str, Any]] = list(builtin)

        mcp_groups = [
            group_name.split(":", 1)[1]
            for group_name in groups
            if group_name.startswith(MCP_GROUP_PREFIX)
        ]
        if self._mcp_manager and mcp_groups:
            mcp_declarations = await self._mcp_manager.load_server_tools(mcp_groups)
            self._register_mcp_tool_declarations(mcp_declarations)
            declarations.extend(mcp_declarations)

        return sorted(
            declarations,
            key=lambda declaration: str(declaration.get("name", "")),
        )

    async def _activate_tool_groups(
        self,
        groups: List[str],
        *,
        refresh_provider: bool,
    ) -> bool:
        normalized_groups = []
        for group_name in groups:
            group = str(group_name or "").strip()
            if not group:
                continue
            if group not in normalized_groups:
                normalized_groups.append(group)
        if CORE_TOOL_GROUP not in normalized_groups:
            normalized_groups.insert(0, CORE_TOOL_GROUP)

        declarations = await self._resolve_tool_declarations_for_groups(normalized_groups)
        active_names = {
            str(declaration.get("name", "")).strip()
            for declaration in declarations
            if str(declaration.get("name", "")).strip()
        }
        changed = (
            tuple(normalized_groups) != self._active_tool_groups
            or active_names != self._active_tool_names
        )
        self._active_tool_groups = tuple(normalized_groups)
        self._active_tool_names = active_names
        self._active_tool_declarations = declarations
        if changed and refresh_provider and self._initialized and self.provider:
            await self.refresh_provider_tools(declarations)
        return changed

    async def _activate_tools_for_prompt(
        self,
        prompt: str,
        *,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
    ) -> None:
        if not isinstance(self.tool_registry, EnhancedToolRegistry):
            return
        groups = self.tool_registry.required_tool_groups(
            prompt,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            mcp_server_names=self._mcp_server_names(),
        )
        changed = await self._activate_tool_groups(
            groups,
            refresh_provider=self._initialized and self.provider is not None,
        )
        if changed:
            audit = self.tool_registry.audit_tool_catalog(
                extra_declarations=[
                    declaration
                    for declaration in self._active_tool_declarations
                    if str(declaration.get("name", "")).find(":") != -1
                ],
                extra_groups={
                    group_name: [
                        name
                        for name in self._active_tool_names
                        if (
                            group_name.startswith(MCP_GROUP_PREFIX)
                            and name.startswith(f"{group_name.split(':', 1)[1]}:")
                        )
                    ]
                    for group_name in self._active_tool_groups
                    if group_name.startswith(MCP_GROUP_PREFIX)
                },
            )
            logger.info(
                "lazy tools: groups=%s tools=%d schema_tokens=%d",
                ",".join(self._active_tool_groups),
                len(self._active_tool_names),
                audit.schema_tokens,
            )

    async def _ensure_tool_available_for_call(
        self,
        tool_name: str,
        *,
        user_request: str = "",
    ) -> Optional[str]:
        name = str(tool_name or "").strip()
        if not name:
            return None
        if name in self._active_tool_names:
            return None
        if not isinstance(self.tool_registry, EnhancedToolRegistry):
            return None

        group_name = self.tool_registry.tool_group_for_name(
            name,
            mcp_server_names=self._mcp_server_names(),
        )
        if group_name is None and self._mcp_manager and ":" in name:
            if await self._mcp_manager.ensure_tool_available(name):
                group_name = f"{MCP_GROUP_PREFIX}{name.split(':', 1)[0]}"
                declarations = self._mcp_manager.get_tool_declarations()
                self._register_mcp_tool_declarations(declarations)
        if group_name is None:
            return None

        changed = await self._activate_tool_groups(
            [*self._active_tool_groups, group_name],
            refresh_provider=False,
        )
        if not changed and name not in self._active_tool_names:
            return None
        return (
            f"[tool-schema-loader] Activated '{group_name}' for '{name}'. "
            f"Request='{user_request[:120]}'"
        )

    def _inspect_tool_targets(self, tool_name: str, tool_args: Dict[str, Any]) -> List[str]:
        if not self.tool_registry:
            return []
        try:
            return self.tool_registry.inspect_mutation_targets(tool_name, tool_args)
        except Exception as error:
            logger.debug("Failed to inspect mutation targets for %s: %s", tool_name, error)
            return []

    def _audit_permission_decision(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        *,
        allowed: bool,
        source: str,
        preview: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._log_audit_event(
            AuditEventType.PERMISSION_GRANTED if allowed else AuditEventType.PERMISSION_DENIED,
            operation=f"permission:{tool_name}",
            target=",".join(self._inspect_tool_targets(tool_name, tool_args)) or None,
            details={
                "toolName": tool_name,
                "toolArgs": self._stringify_tool_arguments(tool_args),
                "source": source,
                "previewPaths": (preview or {}).get("paths", []),
            },
            severity=AuditSeverity.INFO if allowed else AuditSeverity.WARNING,
            success=allowed,
        )

    def _inspect_instruction_snapshot(
        self,
        referenced_files: Optional[List[str]] = None,
        *,
        user_prompt: str = "",
        skill_context: Optional[InstructionSkillContext] = None,
        skill_plan: Optional[SkillLoadPlan] = None,
    ) -> InstructionSnapshot:
        manager = self._instruction_manager or InstructionManager(Path.cwd())
        repo_summary = ""
        if self._repo_graph is not None and self._repo_graph_task and not self._repo_graph_task.done():
            pass # graph still building, skip repo summary for now
        elif self._repo_graph is not None:
            try:
                repo_summary = self._repo_graph.build_repo_summary()
            except Exception:
                logger.debug("Failed to build repo summary", exc_info=True)
        return manager.build_snapshot(
            referenced_files or [],
            plan_mode_enabled=bool(self.config and self.config.plan_mode.enabled),
            repo_summary=repo_summary,
            user_prompt=user_prompt,
            skill_context=skill_context,
            skill_plan=skill_plan,
        )

    def _configured_skill_search_paths(self) -> List[str]:
        config = getattr(self, "config", None)
        if config is None or getattr(config, "skills", None) is None:
            return []
        raw_paths = getattr(config.skills, "search_paths", [])
        if not isinstance(raw_paths, list):
            return []
        return [str(path) for path in raw_paths if str(path).strip()]

    def _build_instruction_skill_context(self) -> InstructionSkillContext:
        repo_root = str(getattr(self, "_repo_root", Path.cwd()))
        terse = False
        batched = False
        plan_mode = False
        sandbox_preset = "workspace-write"
        if self.config:
            terse = resolve_output_verbosity(self.config.economy) == "caveman"
            batched = getattr(self.config.economy, "prefer_batched_reads", False)
            plan_mode = bool(self.config.plan_mode.enabled)
            sandbox_preset = getattr(self.config.sandbox, "default_preset", "workspace-write")
        return InstructionSkillContext(
            current_dir=repo_root,
            plan_mode_enabled=plan_mode,
            sandbox_preset=sandbox_preset,
            terse_mode=terse,
            batched_reads=batched,
            multiplayer_active=bool(getattr(self, "_embedded_multiplayer_room", False)),
        )

    def _tool_result_text(self, result: Any) -> str:
        if isinstance(result, ToolOutcome):
            return result.to_json()
        if isinstance(result, FilteredToolResult):
            return result.output
        return str(result)

    def _tool_result_raw_text(self, result: Any) -> str:
        if isinstance(result, FilteredToolResult):
            return result.raw_output
        return self._tool_result_text(result)

    def _tool_result_filter_metadata(self, result: Any) -> Dict[str, Any]:
        if not isinstance(result, FilteredToolResult):
            return {}
        filtered = result.filter_result
        return {
            "applied": filtered.applied,
            "flavor": filtered.flavor,
            "originalSize": filtered.original_size,
            "filteredSize": filtered.filtered_size,
            "droppedPaths": list(filtered.dropped_paths),
            "summary": filtered.note,
        }

    def get_tool_full_output(self, call_id: str) -> Dict[str, Any]:
        outputs = getattr(self, "_tool_full_outputs", {})
        return dict(outputs.get(call_id, {}))

    def _tool_result_diff(self, result: Any) -> str:
        if isinstance(result, ToolOutcome):
            return result.diff
        return ""

    def _tool_result_paths(self, tool_name: str, tool_args: Dict[str, Any], result: Any) -> List[str]:
        if isinstance(result, ToolOutcome):
            paths = result.metadata.get("changed_paths") or result.metadata.get("paths")
            if isinstance(paths, list) and paths:
                return [str(path) for path in paths]
            if result.path:
                return [result.path]
        return self._inspect_tool_targets(tool_name, tool_args)

    def _tool_result_checkpoint_id(self, result: Any) -> Optional[str]:
        if isinstance(result, ToolOutcome):
            return result.checkpoint_id
        return None

    def _tool_result_changed(self, result: Any) -> Optional[bool]:
        if isinstance(result, ToolOutcome):
            return result.changed
        return None

    def _tool_result_message(self, result: Any) -> str:
        if isinstance(result, ToolOutcome):
            return result.message
        return ""

    def _normalize_permission_decision(self, decision: Any) -> Dict[str, Any]:
        if isinstance(decision, dict):
            approved_paths = decision.get("approvedPaths")
            if approved_paths is None:
                approved_paths = decision.get("approved_paths")
            if not isinstance(approved_paths, list):
                approved_paths = []
            approved_chunks = decision.get("approvedChunks")
            if approved_chunks is None:
                approved_chunks = decision.get("approved_chunks")
            if not isinstance(approved_chunks, list):
                approved_chunks = []
            return {
                "allowed": bool(decision.get("allowed", False)),
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
        return {"allowed": bool(decision), "approvedPaths": [], "approvedChunks": []}

    def clear_approved_paths(self) -> None:
        """Reset session-scoped path approvals."""
        self._approved_write_paths.clear()

    def get_approved_paths(self) -> List[str]:
        """Return currently approved write paths."""
        return sorted(self._approved_write_paths)

    async def _request_permission(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.config and getattr(self.config.agentic, "path_scoped_approval", True) and tool_name in _MUTATING_TOOLS:
            target_paths = self._inspect_tool_targets(tool_name, tool_args)
            resolved = {str(Path(p).resolve()) for p in target_paths if p}
            if resolved and resolved.issubset(self._approved_write_paths):
                return {"allowed": True, "approvedPaths": list(resolved), "approvedChunks": []}
        if not self._permission_callback:
            decision = {"allowed": True, "approvedPaths": [], "approvedChunks": []}
            await self._emit_policy_hooks(
                "permission_decision",
                {
                    "toolName": tool_name,
                    "toolArgs": self._stringify_tool_arguments(tool_args),
                    "preview": preview or {},
                    "allowed": True,
                    "approvedPaths": [],
                    "approvedChunks": [],
                    "source": "default-allow",
                },
            )
            return decision

        decision = await self._permission_callback(tool_name, tool_args, preview)
        normalized = self._normalize_permission_decision(decision)
        if normalized["allowed"] and self.config and getattr(self.config.agentic, "path_scoped_approval", True):
            target_paths = self._inspect_tool_targets(tool_name, tool_args)
            for p in target_paths:
                if p:
                    self._approved_write_paths.add(str(Path(p).resolve()))
            for p in normalized.get("approvedPaths", []):
                if p:
                    self._approved_write_paths.add(str(Path(p).resolve()))
        await self._emit_policy_hooks(
            "permission_decision",
            {
                "toolName": tool_name,
                "toolArgs": self._stringify_tool_arguments(tool_args),
                "preview": preview or {},
                "allowed": normalized["allowed"],
                "approvedPaths": normalized["approvedPaths"],
                "approvedChunks": normalized["approvedChunks"],
                "source": "permission-callback",
            },
        )
        return normalized

    async def _apply_permission_scope(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        approved_paths: List[str],
        approved_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        approved_chunks = approved_chunks or []
        if (not approved_paths and not approved_chunks) or not self.tool_registry:
            return tool_args
        return self.tool_registry.narrow_mutation_arguments(
            tool_name,
            tool_args,
            approved_paths,
            approved_chunks,
        )

    def _should_checkpoint_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        if tool_name not in _MUTATING_TOOLS:
            return False
        if tool_name == "apply_patch_unified" and bool(tool_args.get("check_only")):
            return False
        return True

    async def _create_mutation_checkpoint(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Optional[str]:
        if not self.checkpoint_manager or not self.tool_registry:
            return None

        targets = self._inspect_tool_targets(tool_name, tool_args)
        if not targets:
            return None

        try:
            branch = self._current_git_branch()
            checkpoint = await asyncio.to_thread(
                self.checkpoint_manager.create_checkpoint,
                targets,
                f"Auto checkpoint before {tool_name} [{branch}]",
                f"pre_{tool_name}",
                [tool_name, f"branch:{branch}"],
            )
            self._log_audit_event(
                AuditEventType.CHECKPOINT_CREATE,
                operation=f"checkpoint:{tool_name}",
                target=",".join(targets),
                details={
                    "checkpointId": checkpoint.checkpoint_id,
                    "toolName": tool_name,
                    "targets": targets,
                    "branch": branch,
                },
            )
            return checkpoint.checkpoint_id
        except Exception as error:
            logger.warning("Failed to create pre-mutation checkpoint for %s: %s", tool_name, error)
            return None

    def _turn_cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Stable cache key for per-turn read-only tool result dedup."""
        return f"{tool_name}:{json.dumps(arguments, sort_keys=True, separators=(',', ':'))}"

    async def _execute_tool_internal(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        # Per-turn cache for read-only tools (avoid redundant I/O within same turn)
        if tool_name not in _MUTATING_TOOLS and self._is_concurrency_safe_tool(tool_name, arguments):
            cache_key = self._turn_cache_key(tool_name, arguments)
            cached = self._turn_tool_cache.get(cache_key)
            if cached is not None:
                logger.debug("turn cache hit: %s", tool_name)
                return cached

        targets = self._inspect_tool_targets(tool_name, arguments)
        pre_payload = {
            "toolName": tool_name,
            "toolArgs": self._stringify_tool_arguments(arguments),
            "targets": targets,
        }
        hook_results = await self._emit_policy_hooks("pre_tool_use", pre_payload)
        if any(result.blocked for result in hook_results):
            blocker = next(result for result in hook_results if result.blocked)
            raise PoorCLIError(
                f"Blocked by repo policy hook `{blocker.hook.name}`: "
                f"{blocker.stderr or blocker.stdout or 'non-zero exit'}"
            )

        checkpoint_id: Optional[str] = None
        if self._should_checkpoint_tool(tool_name, arguments):
            checkpoint_id = await self._create_mutation_checkpoint(tool_name, arguments)

        post_payload = {
            "toolName": tool_name,
            "toolArgs": self._stringify_tool_arguments(arguments),
            "targets": targets,
            "checkpointId": checkpoint_id,
        }

        try:
            from .retry import with_retry, RetryConfig as _RetryConfig
            from .exceptions import APITimeoutError, APIRateLimitError
            retry_cfg = _RetryConfig(max_retries=2, base_delay=1.0, max_delay=10.0)
            def _is_transient(exc: BaseException) -> bool:
                return isinstance(exc, (APITimeoutError, APIRateLimitError, TimeoutError, ConnectionError))
            result = await with_retry(
                lambda: self.tool_registry.execute_tool_raw(tool_name, arguments),
                config=retry_cfg,
                retryable=_is_transient,
            )
        except Exception as error:
            self._log_audit_event(
                AuditEventType.TOOL_EXECUTION,
                operation=f"tool:{tool_name}",
                target=",".join(targets) if targets else None,
                details=post_payload,
                severity=AuditSeverity.WARNING,
                success=False,
                error_message=str(error),
            )
            await self._emit_policy_hooks(
                "tool_failure",
                {
                    **post_payload,
                    "error": str(error),
                    "targets": targets,
                },
            )
            await self._emit_policy_hooks(
                "post_tool_use",
                {**post_payload, "success": False, "error": str(error)},
            )
            raise

        if isinstance(result, ToolOutcome):
            if checkpoint_id and not result.checkpoint_id:
                result.checkpoint_id = checkpoint_id
            if result.ok and self._context_manager:
                paths = self._tool_result_paths(tool_name, arguments, result)
                for file_path in paths:
                    self._context_manager.record_access(file_path, reason=tool_name)
                    if result.changed:
                        self._context_manager.mark_file_edited(file_path)

        self._log_audit_event(
            AuditEventType.TOOL_EXECUTION,
            operation=f"tool:{tool_name}",
            target=",".join(self._tool_result_paths(tool_name, arguments, result)) if targets else None,
            details={
                **post_payload,
                "changed": self._tool_result_changed(result),
                "message": self._tool_result_message(result),
                "paths": self._tool_result_paths(tool_name, arguments, result),
            },
        )
        await self._emit_policy_hooks(
            "post_tool_use",
            {
                **post_payload,
                "success": True,
                "changed": self._tool_result_changed(result),
                "paths": self._tool_result_paths(tool_name, arguments, result),
                "message": self._tool_result_message(result),
            },
        )
        # Cache read-only tool results for this turn
        if tool_name not in _MUTATING_TOOLS and self._is_concurrency_safe_tool(tool_name, arguments):
            cache_key = self._turn_cache_key(tool_name, arguments)
            self._turn_tool_cache[cache_key] = result
        return result

    def _check_auto_permission(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[bool]:
        """Check auto-approve/deny from AgenticConfig. Returns True/False/None."""
        if not self.config:
            return None
        ac = self.config.agentic
        if tool_name in ac.auto_approve_tools:
            return True
        args_str = str(tool_args)
        for pattern in ac.deny_patterns:
            if pattern in args_str:
                logger.warning(f"Deny pattern matched: {pattern}")
                return False
        return None # needs interactive permission

    def _compute_edit_diff(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Compute a unified diff for edit_file tool calls."""
        if tool_name != "edit_file":
            return ""
        old_text = tool_args.get("old_text", "")
        new_text = tool_args.get("new_text", "")
        file_path = tool_args.get("file_path", "unknown")
        if not old_text and not new_text:
            return ""
        diff_lines = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        ))
        return "".join(diff_lines)

    def _is_mutating_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """Check whether this tool invocation mutates state."""
        if tool_name == "apply_patch_unified" and bool(tool_args.get("check_only")):
            return False
        if self.tool_registry:
            try:
                return bool(self.tool_registry.is_mutating_tool(tool_name, tool_args))
            except Exception as error:
                logger.debug("Failed mutating check for %s: %s", tool_name, error)
        return tool_name in _MUTATING_TOOLS

    def _is_concurrency_safe_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """Check whether this tool invocation is safe for parallel execution."""
        if self.tool_registry:
            try:
                return bool(self.tool_registry.is_concurrency_safe_tool(tool_name, tool_args))
            except Exception as error:
                logger.debug("Failed concurrency-safety check for %s: %s", tool_name, error)
        return not self._is_mutating_tool_call(tool_name, tool_args)

    def _max_parallel_tool_calls(self) -> int:
        """Configured cap for concurrent safe tool calls."""
        if not self.config:
            return 6
        raw_value = getattr(self.config.agentic, "max_parallel_tool_calls", 6)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return 6
        return max(1, min(value, 32))

    def _max_tool_result_chars_per_turn(self) -> int:
        """Configured cap for tool-result payload size per turn."""
        if not self.config:
            return 60000
        raw_value = getattr(self.config.agentic, "max_tool_result_chars_per_turn", 60000)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return 60000
        return max(1000, min(value, 500000))

    def _total_tool_result_chars(self, tool_results: List[Dict[str, Any]]) -> int:
        total = 0
        for payload in tool_results:
            text = payload.get("result")
            if text is None:
                continue
            total += len(str(text))
        return total

    def _overflow_tool_result(self, result_text: str) -> str:
        """Save oversized result to a temp file, return a reference string."""
        overflow_dir = Path.cwd() / (getattr(self.config.agentic, "overflow_dir", ".poor-cli/overflow") if self.config else ".poor-cli/overflow")
        overflow_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(result_text.encode()).hexdigest()[:16]
        dest = overflow_dir / f"{content_hash}.txt"
        if not dest.exists():
            import tempfile as _tf
            fd, tmp = _tf.mkstemp(dir=str(overflow_dir), suffix=".tmp")
            try:
                os.write(fd, result_text.encode())
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp, str(dest))
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        preview = result_text[:200].rstrip()
        return f"{preview}\n\n[Full result saved to {dest} ({len(result_text):,} chars). Use read_file to access specific sections.]"

    def _gc_overflow_files(self) -> None:
        """Remove overflow files older than 24 hours."""
        overflow_dir = Path.cwd() / (getattr(self.config.agentic, "overflow_dir", ".poor-cli/overflow") if self.config else ".poor-cli/overflow")
        if not overflow_dir.is_dir():
            return
        cutoff = time.time() - 86400
        for f in overflow_dir.iterdir():
            if f.suffix == ".txt" and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)

    def _apply_tool_result_budget(
        self,
        tool_results: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int | bool]]:
        overflow_threshold = int(getattr(self.config.agentic, "overflow_threshold_chars", 30000)) if self.config else 30000
        overflow_count = 0
        pre_overflow: List[Dict[str, Any]] = []
        for payload in tool_results:
            result_text = str(payload.get("result", ""))
            if len(result_text) > overflow_threshold:
                try:
                    ref = self._overflow_tool_result(result_text)
                    pre_overflow.append({**payload, "result": ref})
                    overflow_count += 1
                except Exception:
                    pre_overflow.append(payload)
            else:
                pre_overflow.append(payload)
        budget = self._max_tool_result_chars_per_turn()
        total_before = self._total_tool_result_chars(pre_overflow)
        remaining = budget
        truncated = 0
        bounded: List[Dict[str, Any]] = []
        for payload in pre_overflow:
            result_text = str(payload.get("result", ""))
            if len(result_text) <= remaining:
                bounded.append(payload)
                remaining -= len(result_text)
                continue
            truncated += 1
            if remaining > 0:
                clipped = (
                    result_text[:remaining]
                    + f"\n\n[tool-result truncated: {len(result_text) - remaining} chars omitted; per-turn budget reached]"
                )
                remaining = 0
            else:
                clipped = "[tool-result omitted: per-turn budget reached]"
            bounded.append({**payload, "result": clipped})
        total_after = self._total_tool_result_chars(bounded)
        return bounded, {
            "budget": budget,
            "totalBefore": total_before,
            "totalAfter": total_after,
            "applied": bool(truncated > 0 or overflow_count > 0),
            "truncatedCount": truncated,
            "overflowCount": overflow_count,
        }

    async def _execute_single_call_events(
        self,
        fc: FunctionCall,
        iteration: int,
        max_iterations: int,
        request_id: str,
        expected_call_count: int = 1,
        user_request: str = "",
    ) -> Tuple[List["CoreEvent"], Dict[str, Any]]:
        """Execute a single function call with permission checks. Returns (events, result_dict)."""
        events: List[CoreEvent] = []
        tool_name = fc.name
        tool_args = fc.arguments
        preview_payload: Optional[Dict[str, Any]] = None
        tool_paths = self._inspect_tool_targets(tool_name, tool_args)
        schema_load_note = await self._ensure_tool_available_for_call(
            tool_name,
            user_request=user_request,
        )

        events.append(
            CoreEvent.tool_call_start(
                tool_name, tool_args, fc.id, iteration, max_iterations, paths=tool_paths,
            )
        )
        if schema_load_note:
            events.append(CoreEvent.progress("tool_schema_load", schema_load_note))
        logger.info(f"Executing tool: {tool_name}")

        # 1. check auto-approve/deny from config
        auto = self._check_auto_permission(tool_name, tool_args)
        if auto is False:
            result = "Operation denied by safety policy"
            self._audit_permission_decision(tool_name, tool_args, allowed=False, source="config:auto-deny")
            events.append(CoreEvent.tool_result(
                tool_name, result, fc.id, iteration, max_iterations,
                paths=tool_paths, changed=False, message=result,
            ))
            return events, {"id": fc.id, "name": tool_name, "result": result}

        # 2. if not auto-approved, check interactive permission callback
        if auto is None and self._permission_callback:
            try:
                if tool_name in _MUTATING_TOOLS and self.tool_registry:
                    try:
                        preview_payload = await self.preview_mutation(tool_name, tool_args)
                        preview_payload["requestId"] = request_id
                        tool_paths = preview_payload.get("paths") or tool_paths
                    except Exception as preview_error:
                        logger.warning("Failed to preview mutation for %s: %s", tool_name, preview_error)
                events.append(CoreEvent.permission_request(tool_name, tool_args, request_id, preview=preview_payload))
                permission = await self._request_permission(tool_name, tool_args, preview_payload)
                if not permission["allowed"]:
                    self._audit_permission_decision(tool_name, tool_args, allowed=False, source="interactive", preview=preview_payload)
                    result = "Operation cancelled by user"
                    events.append(CoreEvent.tool_result(
                        tool_name, result, fc.id, iteration, max_iterations,
                        diff=(preview_payload or {}).get("diff", ""), paths=tool_paths, changed=False, message=result,
                    ))
                    return events, {"id": fc.id, "name": tool_name, "result": result}
                self._audit_permission_decision(tool_name, tool_args, allowed=True, source="interactive", preview=preview_payload)
                if permission["approvedChunks"] or permission["approvedPaths"]:
                    try:
                        tool_args = await self._apply_permission_scope(
                            tool_name, tool_args, permission["approvedPaths"], permission["approvedChunks"],
                        )
                        tool_paths = self._inspect_tool_targets(tool_name, tool_args) or tool_paths
                    except Exception as scope_error:
                        result = f"Operation cancelled: {scope_error}"
                        events.append(CoreEvent.tool_result(
                            tool_name, result, fc.id, iteration, max_iterations,
                            diff=(preview_payload or {}).get("diff", ""), paths=tool_paths, changed=False, message=str(scope_error),
                        ))
                        return events, {"id": fc.id, "name": tool_name, "result": result}
            except Exception as e:
                logger.error(f"Permission callback error: {e}")
                self._audit_permission_decision(tool_name, tool_args, allowed=False, source="permission-callback-error", preview=preview_payload)
                result = "Operation denied: permission callback failed"
                events.append(CoreEvent.tool_result(
                    tool_name, result, fc.id, iteration, max_iterations,
                    diff=(preview_payload or {}).get("diff", ""), paths=tool_paths, changed=False, message=str(e),
                ))
                return events, {"id": fc.id, "name": tool_name, "result": result}
        elif auto is True:
            self._audit_permission_decision(tool_name, tool_args, allowed=True, source="config:auto-approve")

        # 3. execute the tool
        try:
            result = await self._execute_tool_internal(tool_name, tool_args)
        except Exception as e:
            result = f"Error: {e}"
            logger.error(f"Tool execution failed: {e}")

        result_text = self._tool_result_text(result)
        raw_result_text = self._tool_result_raw_text(result)
        filter_metadata = self._tool_result_filter_metadata(result)
        if filter_metadata.get("applied") and fc.id:
            if not hasattr(self, "_tool_full_outputs"):
                self._tool_full_outputs = {}
            self._tool_full_outputs[fc.id] = {
                "callId": fc.id,
                "toolName": tool_name,
                "output": raw_result_text,
                "filter": filter_metadata,
            }

        # Economy: diff-only reads — replace full read_file output with diff vs last read
        try:
            _before = result_text
            result_text = self._apply_diff_only_read(tool_name, tool_args, result_text)
            if result_text != _before: # diff was applied
                self._turn_economy.diff_only_applied = True
        except Exception:
            pass

        # Per-call truncation: prevent any single tool result from dominating the budget
        per_call_cap = self._max_tool_result_chars_per_turn() // max(1, expected_call_count)
        if schema_load_note:
            result_text = f"{schema_load_note}\n{result_text}" if result_text else schema_load_note
        if len(result_text) > per_call_cap:
            omitted = len(result_text) - per_call_cap
            result_text = result_text[:per_call_cap] + f"\n[truncated: {omitted} chars omitted]"

        events.append(CoreEvent.tool_result(
            tool_name, result_text, fc.id, iteration, max_iterations,
            diff=self._tool_result_diff(result),
            paths=self._tool_result_paths(tool_name, tool_args, result),
            checkpoint_id=self._tool_result_checkpoint_id(result),
            changed=self._tool_result_changed(result),
            message=self._tool_result_message(result),
            filter_metadata=filter_metadata,
        ))
        return events, {"id": fc.id, "name": tool_name, "result": result_text}

    async def _handle_function_calls_events(
        self,
        response: ProviderResponse,
        iteration: int,
        max_iterations: int,
        request_id: str,
        user_request: str = "",
        turn_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Handle function calls with auto-approve/deny guardrails and diff capture."""
        if not response.function_calls:
            return None

        self._pending_events: List[CoreEvent] = []
        tool_results = []

        plan_allowed = await self._request_plan_review(
            user_request,
            list(response.function_calls),
            request_id,
        )
        if not plan_allowed:
            rejection = "Execution plan rejected by user"
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="plan_rejected",
                iteration=iteration,
                details={"callCount": len(response.function_calls)},
            )
            self._append_turn_orchestration(
                turn_diagnostics,
                iteration=iteration,
                call_count=len(response.function_calls),
                concurrency_safe_count=0,
                sequential_count=len(response.function_calls),
                max_parallel=self._max_parallel_tool_calls(),
                plan_review="rejected",
                had_mutations=False,
                auto_feedback_injected=False,
                tool_names=[fc.name for fc in response.function_calls],
            )
            for fc in response.function_calls:
                self._pending_events.append(
                    CoreEvent.tool_result(
                        fc.name, rejection, fc.id, iteration, max_iterations,
                        changed=False, message=rejection,
                    )
                )
                tool_results.append({"id": fc.id, "name": fc.name, "result": rejection})
            if not self.provider:
                return tool_results
            return self.provider.format_tool_results(tool_results)

        # detect inefficient sequential read_file pattern
        read_calls = [fc for fc in response.function_calls if fc.name == "read_file"]
        if len(read_calls) == 1 and len(response.function_calls) == 1:
            self._turn_economy.sequential_reads_detected += 1

        # partition into concurrency-safe (bounded parallel) and sequential calls
        concurrency_safe_calls: List[FunctionCall] = []
        sequential_calls: List[FunctionCall] = []
        for fc in response.function_calls:
            if self._is_concurrency_safe_tool(fc.name, fc.arguments):
                concurrency_safe_calls.append(fc)
            else:
                sequential_calls.append(fc)
        max_parallel = self._max_parallel_tool_calls()
        total_call_count = len(response.function_calls) # for per-call result budgeting

        # execute safe calls in bounded parallel
        if concurrency_safe_calls:
            if len(concurrency_safe_calls) == 1 or max_parallel <= 1:
                parallel_results = []
                for fc in concurrency_safe_calls:
                    parallel_results.append(
                        await self._execute_single_call_events(
                            fc,
                            iteration,
                            max_iterations,
                            request_id,
                            expected_call_count=total_call_count,
                            user_request=user_request,
                        )
                    )
            else:
                semaphore = asyncio.Semaphore(max_parallel)

                async def _run_safe_call(fc: FunctionCall) -> Tuple[List["CoreEvent"], Dict[str, Any]]:
                    async with semaphore:
                        return await self._execute_single_call_events(
                            fc,
                            iteration,
                            max_iterations,
                            request_id,
                            expected_call_count=total_call_count,
                            user_request=user_request,
                        )

                parallel_results = await asyncio.gather(
                    *[_run_safe_call(fc) for fc in concurrency_safe_calls]
                )

            for call_events, call_result in parallel_results:
                self._pending_events.extend(call_events)
                tool_results.append(call_result)

        # execute sequential/mutating calls — parallelize if targeting different files
        had_mutations = False
        auto_feedback_injected = False
        if len(sequential_calls) > 1 and max_parallel > 1:
            target_groups: Dict[str, List[FunctionCall]] = {}
            no_target: List[FunctionCall] = []
            for fc in sequential_calls:
                targets = self._inspect_tool_targets(fc.name, fc.arguments)
                key = "|".join(sorted(targets)) if targets else ""
                if key:
                    target_groups.setdefault(key, []).append(fc)
                else:
                    no_target.append(fc)
            independent_calls: List[FunctionCall] = []
            truly_sequential: List[FunctionCall] = list(no_target)
            seen_targets: set = set()
            for key, group in target_groups.items():
                targets_set = set(key.split("|"))
                if targets_set & seen_targets:
                    truly_sequential.extend(group)
                else:
                    seen_targets.update(targets_set)
                    independent_calls.extend(group)
            if len(independent_calls) > 1:
                sem = asyncio.Semaphore(max_parallel)
                async def _run_mut(fc_inner: FunctionCall):
                    async with sem:
                        return await self._execute_single_call_events(
                            fc_inner, iteration, max_iterations, request_id,
                            expected_call_count=total_call_count,
                            user_request=user_request,
                        )
                par_results = await asyncio.gather(*[_run_mut(fc) for fc in independent_calls])
                for call_events, call_result in par_results:
                    self._pending_events.extend(call_events)
                    tool_results.append(call_result)
                had_mutations = True
            else:
                truly_sequential = independent_calls + truly_sequential
            for fc in truly_sequential:
                call_events, call_result = await self._execute_single_call_events(
                    fc, iteration, max_iterations, request_id,
                    expected_call_count=total_call_count,
                    user_request=user_request,
                )
                self._pending_events.extend(call_events)
                tool_results.append(call_result)
                if self._is_mutating_tool_call(fc.name, fc.arguments):
                    had_mutations = True
        else:
            for fc in sequential_calls:
                call_events, call_result = await self._execute_single_call_events(
                    fc, iteration, max_iterations, request_id,
                    expected_call_count=total_call_count,
                    user_request=user_request,
                )
                self._pending_events.extend(call_events)
                tool_results.append(call_result)
                if self._is_mutating_tool_call(fc.name, fc.arguments):
                    had_mutations = True

        # auto-feedback: run lint/test after mutations and inject errors
        if had_mutations and self._should_auto_feedback():
            feedback_text = await self._run_auto_feedback()
            if feedback_text:
                auto_feedback_injected = True
                tool_results.append({
                    "id": "__auto_feedback__",
                    "name": "auto_feedback",
                    "result": feedback_text,
                })
        bounded_tool_results, budget_info = self._apply_tool_result_budget(tool_results)
        if budget_info.get("applied"):
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="tool_result_budget_applied",
                iteration=iteration,
                details={
                    "budgetChars": int(budget_info.get("budget", 0) or 0),
                    "beforeChars": int(budget_info.get("totalBefore", 0) or 0),
                    "afterChars": int(budget_info.get("totalAfter", 0) or 0),
                    "truncatedCount": int(budget_info.get("truncatedCount", 0) or 0),
                },
            )
        self._append_turn_transition(
            turn_diagnostics,
            reason_code="tool_turn_executed",
            iteration=iteration,
            details={
                "callCount": len(response.function_calls),
                "concurrencySafeCount": len(concurrency_safe_calls),
                "sequentialCount": len(sequential_calls),
            },
        )
        self._append_turn_orchestration(
            turn_diagnostics,
            iteration=iteration,
            call_count=len(response.function_calls),
            concurrency_safe_count=len(concurrency_safe_calls),
            sequential_count=len(sequential_calls),
            max_parallel=max_parallel,
            plan_review="approved",
            had_mutations=had_mutations,
            auto_feedback_injected=auto_feedback_injected,
            tool_names=[fc.name for fc in response.function_calls],
            tool_result_chars=int(budget_info.get("totalBefore", 0) or 0),
            tool_result_chars_after_budget=int(budget_info.get("totalAfter", 0) or 0),
            tool_result_budget_applied=bool(budget_info.get("applied", False)),
            truncated_results=int(budget_info.get("truncatedCount", 0) or 0),
        )

        if not self.provider:
            return bounded_tool_results
        return self.provider.format_tool_results(bounded_tool_results)

    def _should_auto_feedback(self) -> bool:
        """Check if auto lint/test feedback is enabled via agentic.auto_lint."""
        if not self.config:
            return False
        agentic = getattr(self.config, "agentic", None)
        return bool(agentic and getattr(agentic, "auto_lint", False))

    async def _run_auto_feedback(self) -> str:
        """Run lint/test and return formatted errors, or empty string if all passed."""
        try:
            from .feedback_loop import detect_project, run_feedback_pass, format_feedback_for_model
            detection = detect_project()
            if detection.project_type == "unknown":
                return ""
            results = await run_feedback_pass(detection=detection)
            return format_feedback_for_model(results)
        except Exception as exc:
            logger.debug("auto-feedback failed: %s", exc)
            return ""

    async def reload_mcp_servers(self) -> Dict[str, Any]:
        """Rebuild MCP tool registration from current config."""
        if not self._initialized or not self.config:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        if self._mcp_manager is not None:
            await self._mcp_manager.shutdown()
            self._mcp_manager = None

        trunc_cfg = self.config.output_truncation
        self.tool_registry = EnhancedToolRegistry(
            config=self.config,
            checkpoint_manager=self.checkpoint_manager,
            output_max_chars=trunc_cfg.max_output_chars if trunc_cfg.enabled else 0,
            output_max_lines=trunc_cfg.max_output_lines if trunc_cfg.enabled else 0,
        )
        self.tool_registry._core = self
        if self.config.mcp_servers:
            self._mcp_manager = MCPManager(self.config.mcp_servers, repo_root=Path.cwd())
            await self._mcp_manager.initialize()
        await self._activate_tool_groups([CORE_TOOL_GROUP], refresh_provider=False)
        await self.refresh_provider_tools(self._active_tool_declarations)

        return self.get_mcp_status()

    async def refresh_provider_tools(
        self,
        tool_declarations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Reinitialize the active provider with updated tool declarations."""
        from .providers.tool_translator import ToolTranslator
        ToolTranslator.invalidate_cache() # tools changed, bust translation cache
        if not self._initialized or not self.provider:
            return
        previous_history: List[Dict[str, Any]] = []
        try:
            previous_history = self.provider.get_history()
        except Exception as error:
            logger.debug("Failed to capture provider history before tool refresh: %s", error)
        tools = (
            list(tool_declarations)
            if tool_declarations is not None
            else (
                list(self._active_tool_declarations)
                if self._active_tool_declarations
                else self._tool_declarations_for_shipping()
            )
        )
        if not provider_has_capability(self.provider, ProviderCapability.TOOL_CALLING):
            tools = []
        await self.provider.initialize(
            tools=tools,
            system_instruction=self._system_instruction or "",
        )
        if previous_history:
            history_to_restore = [
                message
                for message in previous_history
                if message.get("role") != "system"
            ]
            try:
                self.provider.set_history(history_to_restore)
            except Exception as error:
                logger.debug("Failed to restore provider history after tool refresh: %s", error)

    async def _handle_function_calls(
        self,
        response: ProviderResponse
    ) -> Any:
        """
        Handle function calls from a provider response.
        
        Args:
            response: The provider response containing function calls.
        
        Returns:
            Formatted tool results for the provider.
        """
        if not response.function_calls:
            return None
        
        tool_results = []
        
        for fc in response.function_calls:
            tool_name = fc.name
            tool_args = fc.arguments
            schema_load_note = await self._ensure_tool_available_for_call(tool_name)
            
            logger.info(f"Executing tool: {tool_name}")
            
            # Check permission if callback is set
            if self._permission_callback:
                try:
                    permission = await self._request_permission(tool_name, tool_args)
                    if not permission["allowed"]:
                        self._audit_permission_decision(
                            tool_name,
                            tool_args,
                            allowed=False,
                            source="interactive",
                        )
                        result = "Operation cancelled by user"
                        tool_results.append({
                            "id": fc.id,
                            "name": tool_name,
                            "result": result
                        })
                        continue
                    self._audit_permission_decision(
                        tool_name,
                        tool_args,
                        allowed=True,
                        source="interactive",
                    )
                    if permission["approvedChunks"] or permission["approvedPaths"]:
                        try:
                            tool_args = await self._apply_permission_scope(
                                tool_name,
                                tool_args,
                                permission["approvedPaths"],
                                permission["approvedChunks"],
                            )
                        except Exception as scope_error:
                            result = f"Operation cancelled: {scope_error}"
                            tool_results.append({
                                "id": fc.id,
                                "name": tool_name,
                                "result": result,
                            })
                            continue
                except Exception as e:
                    logger.error(f"Permission callback error: {e}")
                    self._audit_permission_decision(
                        tool_name,
                        tool_args,
                        allowed=False,
                        source="permission-callback-error",
                    )
                    result = "Operation denied: permission callback failed"
                    tool_results.append({
                        "id": fc.id,
                        "name": tool_name,
                        "result": result,
                    })
                    continue
            
            # Execute the tool
            try:
                result = await self._execute_tool_internal(tool_name, tool_args)
            except Exception as e:
                result = f"Error: {e}"
                logger.error(f"Tool execution failed: {e}")

            result_text = self._tool_result_text(result)
            if schema_load_note:
                result_text = f"{schema_load_note}\n{result_text}" if result_text else schema_load_note
            tool_results.append({
                "id": fc.id,
                "name": tool_name,
                "result": result_text
            })
        
        if not self.provider:
            return tool_results

        # Delegate provider-specific formatting to provider adapters.
        return self.provider.format_tool_results(tool_results)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Execute a tool with given arguments.
        
        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments as a dictionary.
        
        Returns:
            Tool execution result as string.
        
        Raises:
            PoorCLIError: If not initialized or tool execution fails.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Executing tool: {tool_name}")
        
        try:
            result = await self._execute_tool_internal(tool_name, arguments)
            logger.info(f"Tool {tool_name} completed successfully")
            return self._tool_result_text(result)
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            raise PoorCLIError(f"Tool execution failed: {e}")

    async def execute_tool_raw(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Execute a tool and return its structured/raw result."""
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        logger.info(f"Executing tool (raw): {tool_name}")
        try:
            return await self._execute_tool_internal(tool_name, arguments)
        except Exception as e:
            logger.error(f"Raw tool execution failed: {e}")
            raise PoorCLIError(f"Tool execution failed: {e}")

    async def apply_edit_outcome(
        self,
        file_path: str,
        old_text: str,
        new_text: str
    ) -> ToolOutcome:
        """
        Apply a code edit to a file.
        
        Args:
            file_path: Path to the file to edit.
            old_text: Text to replace.
            new_text: Replacement text.
        
        Returns:
            Structured mutation outcome.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Applying edit to {file_path}")
        
        try:
            result = await self.execute_tool_raw(
                "edit_file",
                {
                    "file_path": file_path,
                    "old_text": old_text,
                    "new_text": new_text
                }
            )
            if isinstance(result, ToolOutcome):
                return result
            raise PoorCLIError("edit_file returned an unexpected result type")
        except Exception as e:
            logger.error(f"Edit failed: {e}")
            raise PoorCLIError(f"Edit failed: {e}")

    async def apply_edit(
        self,
        file_path: str,
        old_text: str,
        new_text: str
    ) -> str:
        """Apply a code edit and return a serialized tool result."""
        outcome = await self.apply_edit_outcome(file_path, old_text, new_text)
        return outcome.to_json()

    async def read_file(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> str:
        """
        Read file contents.
        
        Args:
            file_path: Path to the file to read.
            start_line: Optional start line (1-indexed).
            end_line: Optional end line (1-indexed).
        
        Returns:
            File contents as string.
        
        Raises:
            PoorCLIError: If not initialized or file read fails.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Reading file: {file_path}")
        
        try:
            args = {"file_path": file_path}
            if start_line is not None:
                args["start_line"] = start_line
            if end_line is not None:
                args["end_line"] = end_line
            
            result = await self.tool_registry.execute_tool("read_file", args)
            return result
        except Exception as e:
            logger.error(f"File read failed: {e}")
            raise PoorCLIError(f"Failed to read file: {e}")

    async def write_file(
        self,
        file_path: str,
        content: str
    ) -> str:
        """
        Write content to a file.
        
        Args:
            file_path: Path to the file to write.
            content: Content to write.
        
        Returns:
            Success message.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Writing file: {file_path}")
        
        try:
            result = await self.tool_registry.execute_tool(
                "write_file",
                {
                    "file_path": file_path,
                    "content": content
                }
            )
            return result
        except Exception as e:
            logger.error(f"File write failed: {e}")
            raise PoorCLIError(f"Failed to write file: {e}")

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools.

        Returns:
            List of tool declarations.

        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        return self.tool_registry.get_tool_declarations()

    def _tool_declarations_for_shipping(self) -> List[Dict[str, Any]]:
        # honors config.model.tool_schema_mode — "core" ships only the core
        # group (lean menu, fewer tokens per turn); "all" preserves old behavior.
        if not self.tool_registry:
            return []
        mode = "all"
        if self.config is not None:
            mode = str(getattr(self.config.model, "tool_schema_mode", "all") or "all")
        if mode == "core" and isinstance(self.tool_registry, EnhancedToolRegistry):
            return self.tool_registry.get_tool_declarations_for_groups(
                (CORE_TOOL_GROUP,),
                mcp_server_names=self._mcp_server_names(),
            )
        return self.tool_registry.get_tool_declarations()


    async def preview_mutation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Preview a mutating tool without changing the filesystem."""
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        preview = await self.tool_registry.preview_mutation(tool_name, arguments)
        return {
            "ok": preview.ok,
            "operation": preview.operation,
            "paths": self._tool_result_paths(tool_name, arguments, preview),
            "diff": preview.diff,
            "checkpointId": preview.checkpoint_id,
            "changed": preview.changed,
            "message": preview.message,
            "metadata": preview.metadata,
        }
