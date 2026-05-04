"""Permission engine mixin for PoorCLICore.

Handles permission requests, path-scoped approvals, mutation checkpoints,
and tool execution with policy hooks.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import os
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .audit_log import AuditEventType, AuditSeverity
from .exceptions import setup_logger

logger = setup_logger(__name__)

_MUTATING_TOOLS = {
    "write_file", "edit_file", "delete_file",
    "apply_patch_unified", "json_yaml_edit",
}

PermissionDecision = Dict[str, Any]
PermissionCallback = Callable[[str, Dict[str, Any], Optional[Dict[str, Any]]], Awaitable[PermissionDecision]]


def _as_async(cb: Callable[..., Any]) -> PermissionCallback:
    """Wrap a permission callback into a 3-arg async coroutine.

    Accepts either an async or sync callable. If the callable's signature does
    not accept a ``preview`` argument, the wrapper drops it before forwarding.
    Use this at every registration site that still passes a legacy shape.

    This callable MUST be a coroutine function once stored on the core; pass
    legacy sync functions through this helper first.
    """
    try:
        sig = inspect.signature(cb)
        accepts_preview = len(sig.parameters) >= 3 or any(
            p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        accepts_preview = True

    if inspect.iscoroutinefunction(cb):
        if accepts_preview:
            return cb

        @functools.wraps(cb)
        async def async_wrapped(tool: str, args: Dict[str, Any], preview: Optional[Dict[str, Any]] = None) -> PermissionDecision:
            return await cb(tool, args)

        return async_wrapped

    @functools.wraps(cb)
    async def sync_wrapped(tool: str, args: Dict[str, Any], preview: Optional[Dict[str, Any]] = None) -> PermissionDecision:
        if accepts_preview:
            return cb(tool, args, preview)
        return cb(tool, args)

    return sync_wrapped


class PermissionEngineMixin:
    """Mixin providing permission checking, approval scoping, and checkpoint logic."""

    @staticmethod
    def _normalize_permission_decision(decision: Any) -> Dict[str, Any]:
        if isinstance(decision, dict):
            approved_paths = decision.get("approvedPaths") or decision.get("approved_paths")
            if not isinstance(approved_paths, list):
                approved_paths = []
            approved_chunks = decision.get("approvedChunks") or decision.get("approved_chunks")
            if not isinstance(approved_chunks, list):
                approved_chunks = []
            return {
                "allowed": bool(decision.get("allowed", False)),
                "approvedPaths": [str(p) for p in approved_paths if isinstance(p, str) and p],
                "approvedChunks": [c for c in approved_chunks if isinstance(c, dict)],
            }
        return {"allowed": bool(decision), "approvedPaths": [], "approvedChunks": []}

    def clear_approved_paths(self) -> None:
        self._approved_write_paths.clear()

    def get_approved_paths(self) -> List[str]:
        return sorted(self._approved_write_paths)

    def _inspect_tool_targets(self, tool_name: str, tool_args: Dict[str, Any]) -> List[str]:
        if not self.tool_registry:
            return []
        try:
            return self.tool_registry.inspect_mutation_targets(tool_name, tool_args)
        except Exception as error:
            logger.debug("Failed to inspect mutation targets for %s: %s", tool_name, error)
            return []

    def _audit_permission_decision(
        self, tool_name: str, tool_args: Dict[str, Any],
        *, allowed: bool, source: str, preview: Optional[Dict[str, Any]] = None,
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

    async def _request_permission(
        self, tool_name: str, tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.config and getattr(self.config.agentic, "path_scoped_approval", True) and tool_name in _MUTATING_TOOLS:
            target_paths = self._inspect_tool_targets(tool_name, tool_args)
            resolved = {str(Path(p).resolve()) for p in target_paths if p}
            if resolved and resolved.issubset(self._approved_write_paths):
                return {"allowed": True, "approvedPaths": list(resolved), "approvedChunks": []}
        if not self._permission_callback:
            decision = {"allowed": True, "approvedPaths": [], "approvedChunks": []}
            await self._emit_policy_hooks("permission_decision", {
                "toolName": tool_name,
                "toolArgs": self._stringify_tool_arguments(tool_args),
                "preview": preview or {}, "allowed": True, "approvedPaths": [],
                "approvedChunks": [], "source": "default-allow",
            })
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
        await self._emit_policy_hooks("permission_decision", {
            "toolName": tool_name,
            "toolArgs": self._stringify_tool_arguments(tool_args),
            "preview": preview or {}, "allowed": normalized["allowed"],
            "approvedPaths": normalized["approvedPaths"],
            "approvedChunks": normalized["approvedChunks"], "source": "permission-callback",
        })
        return normalized

    async def _apply_permission_scope(
        self, tool_name: str, tool_args: Dict[str, Any],
        approved_paths: List[str], approved_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        approved_chunks = approved_chunks or []
        if (not approved_paths and not approved_chunks) or not self.tool_registry:
            return tool_args
        return self.tool_registry.narrow_mutation_arguments(
            tool_name, tool_args, approved_paths, approved_chunks,
        )

    def _should_checkpoint_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        if tool_name not in _MUTATING_TOOLS:
            return False
        if tool_name == "apply_patch_unified" and bool(tool_args.get("check_only")):
            return False
        if tool_name in {"write_file", "edit_file", "apply_patch_unified"}:
            mode = str(getattr(getattr(self.config, "diff_review", None), "mode", "review") or "review").lower()
            if os.environ.get("POOR_CLI_DIFF_REVIEW", "").strip().lower() != "auto" and mode == "review":
                return False
        return True

    async def _create_mutation_checkpoint(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
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
                operation=f"checkpoint:{tool_name}", target=",".join(targets),
                details={"checkpointId": checkpoint.checkpoint_id, "toolName": tool_name, "targets": targets, "branch": branch},
            )
            return checkpoint.checkpoint_id
        except Exception as error:
            logger.warning("Failed to create pre-mutation checkpoint for %s: %s", tool_name, error)
            return None

    def _check_auto_permission(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[bool]:
        """Return True if auto-approved, False if auto-denied, None if manual check needed."""
        candidate: Optional[str] = None
        if not self.config:
            candidate = None
        else:
            agentic = self.config.agentic
            auto_approve = getattr(agentic, "auto_approve_tools", [])
            if tool_name in auto_approve:
                candidate = "allow"
            deny_patterns = getattr(agentic, "deny_patterns", [])
            args_str = str(tool_args)
            for pattern in deny_patterns:
                if pattern in args_str:
                    logger.warning("Deny pattern matched: %s", pattern)
                    candidate = "deny"
                    break
        try:
            from .permission_dsl import PermissionDsl, combine_behaviors
            model = getattr(getattr(self.config, "model", None), "model_name", "") if self.config else ""
            provider = getattr(getattr(self.config, "model", None), "provider", "") if self.config else ""
            decision = PermissionDsl(Path.cwd()).evaluate(
                tool_name,
                tool_args,
                context={"provider": provider, "model": model},
            )
            if decision is not None:
                candidate = decision.behavior if candidate is None else combine_behaviors(candidate, decision.behavior)
        except Exception as error:
            logger.debug("permission DSL evaluation skipped: %s", error)
        if candidate == "deny":
            return False
        if candidate == "allow":
            return True
        return None
