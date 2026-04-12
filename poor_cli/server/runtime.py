"""
PoorCLI JSON-RPC Server runtime implementation.

This module contains the main JSON-RPC server classes. Import from
`poor_cli.server` for the stable public package surface.
"""

import argparse
import asyncio
from collections import deque
import contextlib
import copy
import difflib
import json
import logging
import os
import signal
import shlex
import shutil
import socket
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..automation_manager import AutomationManager
from ..command_validator import CommandRisk, get_command_validator
from ..config import Config, ConfigManager, PermissionMode, parse_permission_mode
from ..core import PoorCLICore, CoreEvent
from ..custom_commands import CustomCommandRegistry
from ..permission_rules import PermissionRuleEngine
from ..sandbox import (
    PRESET_DESCRIPTION,
    SandboxDecision,
    evaluate_tool_access,
    normalize_preset,
    permission_mode_from_preset,
    preset_from_permission_mode,
    raise_for_denial,
    summarize_capabilities,
)
from ..skills import SkillRegistry
from ..session_store import SessionStore
from ..task_manager import TaskManager
from ..exceptions import (
    ConfigurationError,
    MissingAPIKeyError,
    PoorCLIError,
    PermissionDeniedError,
    get_error_code,
    log_context,
    set_log_context,
    setup_logger,
)
from ..provider_catalog import common_models_for_provider, get_model_tier
from .types import JsonRpcMessage, JsonRpcError, InvalidParamsError, ManagedServiceRuntime
from .error_formatter import _sanitize_exception_message
from .transport import StdioTransport

logger = setup_logger(__name__)



# =============================================================================
# PoorCLI Server
# =============================================================================


class PoorCLIServer:
    """
    JSON-RPC server for PoorCLI.

    Provides editor integration via stdio transport (for Neovim).
    """

    def __init__(self):
        """Initialize the server."""
        from ..session_manager import SessionManager
        self._session_manager = SessionManager()
        self._session_manager.create_session(label="default", make_default=True)
        self._session_manager.set_permission_callback(self._server_permission_callback)
        self.handlers: Dict[str, Callable] = {}
        self.initialized = False
        self._needs_provider_init = False
        self._pending_init_params: Dict[str, Any] = {}
        self.permission_mode: str = PermissionMode.DEFAULT.value
        self.logger = setup_logger("poor_cli.server")
        self.session_id = f"server-{uuid.uuid4().hex[:8]}"
        set_log_context(session_id=self.session_id)
        self._running = False
        self._transport = StdioTransport()
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._client_streaming = False  # set True if client opts in during initialize
        self._client_capabilities: Dict[str, Any] = {}
        self._pending_permissions: Dict[str, asyncio.Future] = {}  # promptId → Future[bool]
        self._pending_plans: Dict[str, asyncio.Future] = {}  # promptId -> Future[bool]
        self._background_tasks: Set[asyncio.Task[Any]] = set()
        self._embedded_multiplayer_room = False
        self._host_server_lock: Optional[asyncio.Lock] = None
        self._host_server: Optional[Any] = None
        self._host_tunnel: Optional["NgrokTunnel"] = None
        self._host_bind_host = ""
        self._host_port = 0
        self._host_local_signaling_url = ""
        self._host_share_signaling_url = ""
        self._host_public_signaling_url: Optional[str] = None
        self._host_rooms: List[str] = []
        self._host_ngrok_enabled = False
        self._service_lock: Optional[asyncio.Lock] = None
        self._managed_services: Dict[str, ManagedServiceRuntime] = {}
        self._service_logs_dir = Path.home() / ".poor-cli" / "services"
        self._task_manager: Optional[TaskManager] = None
        self._automation_manager: Optional[AutomationManager] = None
        self._sandbox_preset: str = "workspace-write"
        self._permission_rules = PermissionRuleEngine(Path.cwd())

        self._register_handlers()

    @property
    def core(self) -> PoorCLICore:
        """backward-compat: returns the default session's core."""
        return self._session_manager.get_session().core

    @core.setter
    def core(self, value: PoorCLICore) -> None:
        """backward-compat setter — replaces core in default session."""
        session = self._session_manager.get_session()
        session.core = value

    def _resolve_core(self, params: Dict[str, Any]) -> PoorCLICore:
        """resolve the PoorCLICore for a request, supporting sessionId."""
        sid = params.get("sessionId")
        return self._session_manager.get_session(sid).core

    @staticmethod
    def _chat_request_id(params: Dict[str, Any]) -> str:
        """Return a stable request id string for chat logging."""
        request_id = str(params.get("requestId", "")).strip()
        if request_id:
            return request_id
        return f"chat-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _chat_context_count(context_files: Any) -> int:
        """Best-effort context file count for chat logging."""
        if isinstance(context_files, list):
            return len(context_files)
        return 0

    @staticmethod
    def _normalize_client_capabilities(raw_capabilities: Any) -> Dict[str, Any]:
        if isinstance(raw_capabilities, dict):
            return dict(raw_capabilities)
        return {}

    def _client_supports(self, *path: str, default: bool = True) -> bool:
        if not self._client_capabilities:
            return default
        current: Any = self._client_capabilities
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        if isinstance(current, bool):
            return current
        return default

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

    def _current_sandbox_preset(self) -> str:
        config = getattr(self.core, "config", None)
        if config is not None and getattr(config, "sandbox", None) is not None:
            configured = str(getattr(config.sandbox, "default_preset", "")).strip()
            if configured:
                self._sandbox_preset = normalize_preset(
                    configured,
                    fallback_permission_mode=self.permission_mode,
                )
        else:
            self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
        return self._sandbox_preset

    def _task_manager_instance(self) -> TaskManager:
        if self._task_manager is None:
            self._task_manager = TaskManager(Path.cwd())
        return self._task_manager

    def _automation_manager_instance(self) -> AutomationManager:
        if self._automation_manager is None:
            self._automation_manager = AutomationManager(
                Path.cwd(),
                task_manager=self._task_manager_instance(),
            )
        return self._automation_manager

    def _collaboration_status_payload(self) -> Dict[str, Any]:
        payload = {
            "running": False,
            "role": "solo",
            "room": "",
            "memberCount": 0,
            "queueState": {"depth": 0, "handsRaised": 0},
            "connectionHealth": "offline",
            "recentRecoveryEvents": [],
            "summary": "No active collaboration session.",
        }
        if self._host_server is None:
            return payload

        host_payload = self._compose_host_server_payload(created=False, stopped=False)
        rooms = host_payload.get("rooms") if isinstance(host_payload, dict) else None
        first_room = rooms[0] if isinstance(rooms, list) and rooms else {}
        if not isinstance(first_room, dict):
            first_room = {}
        room_name = str(first_room.get("name", "")).strip()
        member_count = int(first_room.get("memberCount", 0) or 0)
        hands_raised = int(first_room.get("handsRaised", 0) or 0)
        lobby_enabled = bool(first_room.get("lobbyEnabled", False))
        payload.update(
            {
                "running": True,
                "role": "host",
                "room": room_name,
                "memberCount": member_count,
                "queueState": {"depth": member_count, "handsRaised": hands_raised},
                "connectionHealth": "healthy",
                "recentRecoveryEvents": [],
                "summary": (
                    f"Hosting `{room_name}` with {member_count} member(s)"
                    if room_name
                    else f"Hosting {member_count} member(s)"
                ),
                "lobbyEnabled": lobby_enabled,
                "preset": str(first_room.get("preset", "") or ""),
                "mode": str(first_room.get("mode", "") or ""),
                "signalingUrl": str(host_payload.get("signalingUrl", "") or ""),
            }
        )
        return payload

    async def _emit_collaboration_event(self, action: str, payload: Dict[str, Any]) -> None:
        await self.core._emit_policy_hooks(
            "collaboration_event",
            {
                "action": action,
                **payload,
            },
        )

    def _status_view_payload(self) -> Dict[str, Any]:
        payload = self.core.build_status_view()
        payload["collaboration"] = self._collaboration_status_payload()
        trust = payload.get("trust")
        if isinstance(trust, dict):
            trust["mcp"] = self.core.get_mcp_status()
            trust["audit"] = self.core.get_policy_status().get("audit", {})
        return payload

    def _doctor_report_payload(self) -> Dict[str, Any]:
        payload = self.core.build_doctor_report()
        payload["statusView"] = self._status_view_payload()
        checks = payload.get("checks")
        if isinstance(checks, list):
            collab = payload["statusView"].get("collaboration", {})
            checks.append(
                {
                    "id": "collaboration",
                    "title": "Collaboration session",
                    "status": "ok" if collab.get("running") else "warning",
                    "message": collab.get("summary", "No active collaboration session."),
                    "action": "Use `/collab start`, `/collab join`, or inspect `/collab summary`.",
                }
            )
        return payload

    @staticmethod
    def _normalize_string_list(raw_values: Any, *, field_name: str) -> List[str]:
        if raw_values is None:
            return []
        if not isinstance(raw_values, list):
            raise InvalidParamsError(f"{field_name} must be an array")

        values: List[str] = []
        for raw_value in raw_values:
            value = str(raw_value or "").strip()
            if value:
                values.append(value)
        return values

    def _coerce_task_execution_metadata(self, raw_execution: Any) -> Dict[str, Any]:
        if raw_execution is None:
            return {}
        if not isinstance(raw_execution, dict):
            raise InvalidParamsError("execution must be an object")

        execution: Dict[str, Any] = {}

        provider = str(raw_execution.get("provider", "") or "").strip()
        if provider:
            execution["provider"] = provider

        model = str(raw_execution.get("model", "") or "").strip()
        if model:
            execution["model"] = model

        routing_mode = str(raw_execution.get("routingMode", "") or "").strip()
        if routing_mode:
            execution["routingMode"] = routing_mode

        config_path = str(raw_execution.get("configPath", "") or "").strip()
        if config_path:
            execution["configPath"] = config_path

        execution_mode = str(raw_execution.get("executionMode", "") or "").strip().lower()
        if execution_mode:
            if execution_mode not in {"worktree", "local"}:
                raise InvalidParamsError("execution.executionMode must be `worktree` or `local`")
            execution["executionMode"] = execution_mode

        reasoning_effort = str(raw_execution.get("reasoningEffort", "") or "").strip().lower()
        if reasoning_effort:
            if reasoning_effort not in {"low", "medium", "high"}:
                raise InvalidParamsError(
                    "execution.reasoningEffort must be `low`, `medium`, or `high`"
                )
            execution["reasoningEffort"] = reasoning_effort

        context_files = self._normalize_string_list(
            raw_execution.get("contextFiles"),
            field_name="execution.contextFiles",
        )
        if context_files:
            execution["contextFiles"] = context_files

        pinned_context_files = self._normalize_string_list(
            raw_execution.get("pinnedContextFiles"),
            field_name="execution.pinnedContextFiles",
        )
        if pinned_context_files:
            execution["pinnedContextFiles"] = pinned_context_files

        raw_context_budget = raw_execution.get("contextBudgetTokens")
        if raw_context_budget is not None:
            try:
                context_budget = int(raw_context_budget)
            except (TypeError, ValueError) as error:
                raise InvalidParamsError("execution.contextBudgetTokens must be an integer") from error
            if context_budget <= 0:
                raise InvalidParamsError("execution.contextBudgetTokens must be greater than zero")
            execution["contextBudgetTokens"] = context_budget

        return execution

    def _skill_registry(self) -> SkillRegistry:
        search_paths: List[str] = []
        config = getattr(self.core, "config", None)
        if config is not None and getattr(config, "skills", None) is not None:
            raw_paths = getattr(config.skills, "search_paths", [])
            if isinstance(raw_paths, list):
                search_paths = [str(path) for path in raw_paths if str(path).strip()]
        return SkillRegistry(Path.cwd(), search_paths=search_paths)

    def _command_registry(self) -> CustomCommandRegistry:
        return CustomCommandRegistry(Path.cwd())

    @staticmethod
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
        except Exception:
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

    def _get_host_server_lock(self) -> asyncio.Lock:
        if self._host_server_lock is None:
            self._host_server_lock = asyncio.Lock()
        return self._host_server_lock

    def _get_service_lock(self) -> asyncio.Lock:
        if self._service_lock is None:
            self._service_lock = asyncio.Lock()
        return self._service_lock

    def _track_background_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        self._background_tasks.add(task)

        def _discard(done_task: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(done_task)

        task.add_done_callback(_discard)
        return task

    def _resolve_pending_review_requests(self) -> None:
        denied_permission = {
            "allowed": False,
            "approvedPaths": [],
            "approvedChunks": [],
        }
        for future in list(self._pending_permissions.values()):
            if not future.done():
                future.set_result(dict(denied_permission))
        self._pending_permissions.clear()

        for future in list(self._pending_plans.values()):
            if not future.done():
                future.set_result(False)
        self._pending_plans.clear()

    async def _shutdown_background_tasks(self) -> None:
        tasks = [task for task in self._background_tasks if not task.done()]
        if not tasks:
            self._background_tasks.clear()
            return

        for task in tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def _server_permission_callback(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Server-side permission callback for core tool execution."""
        decision = self._evaluate_tool_access(tool_name, tool_args, preview)
        if not decision.allowed:
            if "outside trusted workspace roots" in decision.reason:
                raise_for_denial(tool_name, self.permission_mode, decision)
            return False
        return not decision.requires_approval

    def _register_handlers(self) -> None:
        """Register JSON-RPC method handlers."""
        self.handlers = {
            "initialize": self.handle_initialize,
            "shutdown": self.handle_shutdown,
            "chat": self.handle_chat,
            "listProviders": self.handle_list_providers,
            "getStartupState": self.handle_get_startup_state,
            "switchProvider": self.handle_switch_provider,
            "getConfig": self.handle_get_config,
            "setConfig": self.handle_set_config,
            "getPermissions": self.handle_get_permissions,
            "setPermissions": self.handle_set_permissions,
            "setApiKey": self.handle_set_api_key,
            "getApiKeyStatus": self.handle_get_api_key_status,
            "startService": self.handle_start_service,
            "stopService": self.handle_stop_service,
            "getServiceStatus": self.handle_get_service_status,
            "getServiceLogs": self.handle_get_service_logs,
            "poor-cli/chat": self.handle_chat,
            "poor-cli/inlineComplete": self.handle_inline_complete,
            "poor-cli/applyEdit": self.handle_apply_edit,
            "poor-cli/readFile": self.handle_read_file,
            "poor-cli/executeCommand": self.handle_execute_command,
            "poor-cli/getTools": self.handle_get_tools,
            "poor-cli/switchProvider": self.handle_switch_provider,
            "poor-cli/getProviderInfo": self.handle_get_provider_info,
            "poor-cli/getInstructionStack": self.handle_get_instruction_stack,
            "poor-cli/getStatusView": self.handle_get_status_view,
            "poor-cli/getTrustView": self.handle_get_trust_view,
            "poor-cli/getDoctorReport": self.handle_get_doctor_report,
            "poor-cli/getPolicyStatus": self.handle_get_policy_status,
            "poor-cli/getSandboxStatus": self.handle_get_sandbox_status,
            "poor-cli/getMcpStatus": self.handle_get_mcp_status,
            "poor-cli/clearHistory": self.handle_clear_history,
            "poor-cli/compactContext": self.handle_compact_context,
            "poor-cli/previewContext": self.handle_preview_context,
            "poor-cli/getContextExplain": self.handle_get_context_explain,
            "poor-cli/previewMutation": self.handle_preview_mutation,
            "poor-cli/exec": self.handle_exec,
            "poor-cli/listRuns": self.handle_list_runs,
            "poor-cli/listWorkflows": self.handle_list_workflows,
            "poor-cli/getWorkflow": self.handle_get_workflow,
            "poor-cli/listConfigOptions": self.handle_list_config_options,
            "poor-cli/setConfig": self.handle_set_config,
            "poor-cli/getPermissions": self.handle_get_permissions,
            "poor-cli/setPermissions": self.handle_set_permissions,
            "poor-cli/toggleConfig": self.handle_toggle_config,
            "poor-cli/setApiKey": self.handle_set_api_key,
            "poor-cli/getApiKeyStatus": self.handle_get_api_key_status,
            "poor-cli/testApiKey": self.handle_test_api_key,
            "poor-cli/listProviders": self.handle_list_providers,
            "poor-cli/listSessions": self.handle_list_sessions,
            "poor-cli/listHistory": self.handle_list_history,
            "poor-cli/searchHistory": self.handle_search_history,
            "poor-cli/listSkills": self.handle_list_skills,
            "poor-cli/getSkill": self.handle_get_skill,
            "poor-cli/listCustomCommands": self.handle_list_custom_commands,
            "poor-cli/getCustomCommand": self.handle_get_custom_command,
            "poor-cli/runCustomCommand": self.handle_run_custom_command,
            "poor-cli/createTask": self.handle_create_task,
            "poor-cli/listTasks": self.handle_list_tasks,
            "poor-cli/getTask": self.handle_get_task,
            "poor-cli/startTask": self.handle_start_task,
            "poor-cli/approveTask": self.handle_approve_task,
            "poor-cli/cancelTask": self.handle_cancel_task,
            "poor-cli/retryTask": self.handle_retry_task,
            "poor-cli/replayTask": self.handle_replay_task,
            "poor-cli/createAutomation": self.handle_create_automation,
            "poor-cli/listAutomations": self.handle_list_automations,
            "poor-cli/getAutomation": self.handle_get_automation,
            "poor-cli/setAutomationEnabled": self.handle_set_automation_enabled,
            "poor-cli/runAutomationNow": self.handle_run_automation_now,
            "poor-cli/runDueAutomations": self.handle_run_due_automations,
            "poor-cli/getAutomationHistory": self.handle_get_automation_history,
            "poor-cli/replayAutomation": self.handle_replay_automation,
            "poor-cli/listCheckpoints": self.handle_list_checkpoints,
            "poor-cli/createCheckpoint": self.handle_create_checkpoint,
            "poor-cli/restoreCheckpoint": self.handle_restore_checkpoint,
            "poor-cli/previewCheckpoint": self.handle_preview_checkpoint,
            "poor-cli/compareFiles": self.handle_compare_files,
            "poor-cli/exportConversation": self.handle_export_conversation,
            "poor-cli/startHostServer": self.handle_start_host_server,
            "poor-cli/getHostServerStatus": self.handle_get_host_server_status,
            "poor-cli/getCollabSummary": self.handle_get_collab_summary,
            "poor-cli/stopHostServer": self.handle_stop_host_server,
            "poor-cli/listHostMembers": self.handle_list_host_members,
            "poor-cli/removeHostMember": self.handle_remove_host_member,
            "poor-cli/setHostMemberRole": self.handle_set_host_member_role,
            "poor-cli/setHostLobby": self.handle_set_host_lobby,
            "poor-cli/approveHostMember": self.handle_approve_host_member,
            "poor-cli/denyHostMember": self.handle_deny_host_member,
            "poor-cli/rotateHostToken": self.handle_rotate_host_token,
            "poor-cli/revokeHostToken": self.handle_revoke_host_token,
            "poor-cli/handoffHostMember": self.handle_handoff_host_member,
            "poor-cli/setHostPreset": self.handle_set_host_preset,
            "poor-cli/listHostActivity": self.handle_list_host_activity,
            "poor-cli/startService": self.handle_start_service,
            "poor-cli/stopService": self.handle_stop_service,
            "poor-cli/getServiceStatus": self.handle_get_service_status,
            "poor-cli/getServiceLogs": self.handle_get_service_logs,
            "poor-cli/cancelRequest": self.handle_cancel_request,
            "poor-cli/chatStreaming": self.handle_chat_streaming,
            "poor-cli/pairStart": self.handle_pair_start,
            "poor-cli/suggestText": self.handle_suggest_text,
            "poor-cli/peerMessage": self.handle_peer_message,
            "poor-cli/passDriver": self.handle_pass_driver,
            "poor-cli/addAgendaItem": self.handle_add_agenda_item,
            "poor-cli/listAgenda": self.handle_list_agenda,
            "poor-cli/resolveAgendaItem": self.handle_resolve_agenda_item,
            "poor-cli/setHandRaised": self.handle_set_hand_raised,
            "poor-cli/nextDriver": self.handle_next_driver,
            "poor-cli/getSessionCost": self.handle_get_session_cost,
            "poor-cli/listOllamaModels": self.handle_list_ollama_models,
            "poor-cli/gcCheckpoints": self.handle_gc_checkpoints,
            "poor-cli/saveSession": self.handle_save_session,
            "poor-cli/mcpHealthCheck": self.handle_mcp_health_check,
            "poor-cli/restoreSession": self.handle_restore_session,
            "poor-cli/getEconomySavings": self.handle_get_economy_savings,
            "poor-cli/setEconomyPreset": self.handle_set_economy_preset,
            "poor-cli/getCacheStats": self.handle_get_cache_stats,
            "poor-cli/clearSemanticCache": self.handle_clear_semantic_cache,
            "poor-cli/getContextPressure": self.handle_get_context_pressure,
            "poor-cli/getContextBreakdown": self.handle_get_context_breakdown,
            "poor-cli/estimateCost": self.handle_estimate_cost,
            "poor-cli/compareModelCost": self.handle_compare_model_cost,
            "poor-cli/exportCostReport": self.handle_export_cost_report,
            "poor-cli/getTokensVisualization": self.handle_get_tokens_visualization,
            "poor-cli/getCostHistory": self.handle_get_cost_history,
            "poor-cli/applyBudgetTemplate": self.handle_apply_budget_template,
            "poor-cli/listBudgetTemplates": self.handle_list_budget_templates,
            "poor-cli/createSession": self.handle_create_session,
            "poor-cli/destroySession": self.handle_destroy_session,
            "poor-cli/switchSession": self.handle_switch_session,
            "poor-cli/forkSession": self.handle_fork_session,
            "poor-cli/listMuxSessions": self.handle_list_mux_sessions,
            "poor-cli/renameSession": self.handle_rename_session,
            "poor-cli/getCompletion": self.handle_get_completion,
            "poor-cli/semanticSearch": self.handle_semantic_search,
            "poor-cli/indexCodebase": self.handle_index_codebase,
            "poor-cli/getIndexStats": self.handle_get_index_stats,
            "poor-cli/indexEmbeddings": self.handle_index_embeddings,
            "poor-cli/vectorSearch": self.handle_vector_search,
            "poor-cli/hybridSearch": self.handle_hybrid_search,
            "poor-cli/createAgent": self.handle_create_agent,
            "poor-cli/listAgents": self.handle_list_agents,
            "poor-cli/getAgent": self.handle_get_agent,
            "poor-cli/startAgent": self.handle_start_agent,
            "poor-cli/cancelAgent": self.handle_cancel_agent,
            "poor-cli/getAgentLogs": self.handle_get_agent_logs,
            "poor-cli/getAgentResult": self.handle_get_agent_result,
            "poor-cli/listProfiles": self.handle_list_profiles,
            "poor-cli/applyProfile": self.handle_apply_profile,
            "poor-cli/getTrustStatus": self.handle_get_trust_status,
            "poor-cli/trustRepo": self.handle_trust_repo,
            "poor-cli/untrustRepo": self.handle_untrust_repo,
            "poor-cli/memoryList": self.handle_memory_list,
            "poor-cli/memorySave": self.handle_memory_save,
            "poor-cli/memorySearch": self.handle_memory_search,
            "poor-cli/memoryDelete": self.handle_memory_delete,
            "poor-cli/getDockerSandboxStatus": self.handle_get_docker_sandbox_status,
            "poor-cli/watchScan": self.handle_watch_scan,
            "poor-cli/previewStart": self.handle_preview_start,
            "poor-cli/previewStop": self.handle_preview_stop,
            "poor-cli/previewStatus": self.handle_preview_status,
            "poor-cli/deploy": self.handle_deploy,
            "poor-cli/deployTargets": self.handle_deploy_targets,
            "poor-cli/deployValidate": self.handle_deploy_validate,
            "poor-cli/deployHistory": self.handle_deploy_history,
            "poor-cli/getRecoverySuggestions": self.handle_get_recovery_suggestions,
            "poor-cli/promptSave": self.handle_prompt_save,
            "poor-cli/promptLoad": self.handle_prompt_load,
            "poor-cli/promptList": self.handle_prompt_list,
            "poor-cli/promptDelete": self.handle_prompt_delete,
            "poor-cli/getCommandManifest": self.handle_get_command_manifest,
            "poor-cli/latentCompatibility": self.handle_latent_compatibility,
        }

    # =========================================================================
    # Handler Methods
    # =========================================================================

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
            loop = asyncio.get_event_loop()
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
                    except OSError:
                        pass
                    graph_nodes.append({"name": d, "children": sub})
            except Exception:
                pass
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
            raise ConfigurationError(f"Initialization failed: {e}") from e

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

    async def handle_preview_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview backend-owned context selection for a chat turn."""
        self._ensure_initialized()

        return await self.core.preview_context(
            message=str(params.get("message", "")),
            context_files=params.get("contextFiles"),
            pinned_context_files=params.get("pinnedContextFiles"),
            context_budget_tokens=params.get("contextBudgetTokens"),
        )

    async def handle_preview_mutation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview a mutating file tool without writing to disk."""
        self._ensure_initialized()

        return await self.core.preview_mutation(
            tool_name=str(params.get("toolName", "")),
            arguments=params.get("toolArgs") or {},
        )

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

    async def handle_switch_provider(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Switch AI provider.

        Params:
            provider: Provider name
            model: Optional model name

        Returns:
            success: Whether the switch succeeded
            provider: New provider info
        """
        self._ensure_initialized()

        provider = params.get("provider", "")
        model = params.get("model")

        # validate API key availability before switch (from provider_lifecycle)
        if provider and provider != "ollama":
            config_manager, config = self._ensure_config_loaded()
            api_key = config_manager.get_api_key(provider)
            if not api_key:
                from ..provider_lifecycle import ProviderLifecycleService
                pls = type("_Stub", (), {"_providers_with_keys": lambda self: [p for p in config.model.providers if p == "ollama" or config_manager.get_api_key(p)]})()
                available = pls._providers_with_keys()
                provider_cfg = config.model.providers.get(provider)
                env_var = provider_cfg.api_key_env_var if provider_cfg else "API key"
                return {"success": False, "error": f"No API key for {provider} (set {env_var})", "availableProviders": available}

        await self.core.switch_provider(provider, model)
        provider_info = self.core.get_provider_info()

        # push providerChanged so lualine / status UIs update without polling
        async def _emit_provider_changed() -> None:
            try:
                await self.write_message_stdio(JsonRpcMessage(
                    method="poor-cli/providerChanged",
                    params={"providerInfo": provider_info},
                ))
            except Exception as exc:
                logger.debug("emit providerChanged notification failed: %s", exc)
        asyncio.create_task(_emit_provider_changed())

        return {"success": True, "provider": provider_info}

    async def handle_get_provider_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current provider info.

        Returns:
            Provider info dict
        """
        self._ensure_initialized()
        return self.core.get_provider_info()

    async def handle_get_instruction_stack(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the active instruction stack for the given referenced files."""
        self._ensure_initialized()
        referenced_files = params.get("referencedFiles")
        if not isinstance(referenced_files, list):
            referenced_files = []
        return self.core.inspect_instruction_stack([str(path) for path in referenced_files])

    async def handle_get_policy_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return repo-local policy hook and audit status."""
        del params
        self._ensure_initialized()
        return self.core.get_policy_status()

    async def handle_get_status_view(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical session status payload shared across clients."""
        del params
        self._ensure_initialized()
        return self._status_view_payload()

    async def handle_get_trust_view(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the trust-center payload shared across clients."""
        del params
        self._ensure_initialized()
        payload = self._status_view_payload()
        payload["view"] = "trust"
        return payload

    async def handle_get_doctor_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return structured diagnostics with actionable remediation."""
        del params
        self._ensure_initialized()
        return self._doctor_report_payload()

    async def handle_get_sandbox_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return sandbox preset and capability summary."""
        del params
        self._ensure_initialized()
        preset = self._current_sandbox_preset()
        return {
            "sandboxPreset": preset,
            "permissionMode": self.permission_mode,
            "description": PRESET_DESCRIPTION.get(preset, ""),
            "trustedRoots": [str(root) for root in self._trusted_workspace_roots()],
        }

    async def handle_get_mcp_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return MCP connectivity and registered tool status."""
        del params
        self._ensure_initialized()
        return self.core.get_mcp_status()

    async def handle_clear_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clear conversation history.

        Returns:
            success: Always true
        """
        self._ensure_initialized()
        await self.core.clear_history()
        return {"success": True}

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

    async def handle_list_runs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List recent run records from the shared run ledger."""
        self._ensure_initialized()
        source_kind = str(params.get("sourceKind", "") or "").strip() or None
        source_id = str(params.get("sourceId", "") or "").strip() or None
        limit = self._clamp_count(params.get("limit"), default=25, min_value=1, max_value=200)
        return {
            "runs": self.core.list_runs(
                source_kind=source_kind,
                source_id=source_id,
                limit=limit,
            )
        }

    async def handle_list_workflows(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List built-in workflow templates."""
        del params
        self._ensure_initialized()
        workflows = self.core.list_workflow_templates()
        recommended = next(
            (
                workflow.get("name", "")
                for workflow in workflows
                if workflow.get("recommended")
            ),
            "",
        )
        if not recommended and workflows:
            recommended = str(workflows[0].get("name", "") or "")
        return {"workflows": workflows, "recommended": recommended}

    async def handle_get_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a single workflow template."""
        self._ensure_initialized()
        name = str(params.get("name", "") or "").strip()
        if not name:
            raise InvalidParamsError("Missing workflow name")
        workflow = self.core.get_workflow_template(name)
        if workflow is None:
            raise InvalidParamsError(f"Unknown workflow: {name}")
        return {"workflow": workflow}

    async def handle_compact_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply context management strategy.
        Params: strategy - one of 'auto', 'compact', 'gentle', 'aggressive', 'compress', 'handoff'
        Returns: strategy, summary, messages_before, messages_after"""
        self._ensure_initialized()
        strategy = params.get("strategy", "compact")
        return await self.core.compact_context(strategy)

    async def handle_get_context_explain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Alias for previewContext using context-explanation naming."""
        return await self.handle_preview_context(params)

    async def handle_list_providers(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List all available providers with their models.

        Returns:
            Dictionary of provider name -> {available, models, ...}
        """
        from ..providers.provider_factory import ProviderFactory

        config_manager, config = self._ensure_config_loaded()
        result: Dict[str, Any] = {}
        seen_provider_keys: set[str] = set()
        ollama_models: List[str] = []
        ollama_base_url = self._ollama_base_url()
        ollama_ready = self._is_ollama_reachable(ollama_base_url)
        if ollama_ready:
            ollama_models = self._list_ollama_models(ollama_base_url)

        for name, cls in ProviderFactory.list_providers().items():
            info = ProviderFactory.get_provider_info(name) or {}
            provider_key = self._normalize_provider_name(name)
            if provider_key in seen_provider_keys:
                continue
            seen_provider_keys.add(provider_key)
            provider_cfg = config.model.providers.get(provider_key)
            dependency_available = bool(info.get("available", True))
            # Provide default model suggestions per provider
            model_suggestions: Dict[str, list] = {
                "gemini": common_models_for_provider("gemini"),
                "openai": common_models_for_provider("openai"),
                "anthropic": common_models_for_provider("anthropic"),
                "claude": common_models_for_provider("anthropic"),
                "ollama": ollama_models if ollama_models else common_models_for_provider("ollama"),
            }
            if provider_key == "ollama":
                ready = ollama_ready
                status_label = (
                    "service up"
                    if ready
                    else f"service unavailable at {ollama_base_url}"
                )
            else:
                api_key = config_manager.get_api_key(provider_key) if provider_cfg else None
                ready = bool(api_key)
                env_var = provider_cfg.api_key_env_var if provider_cfg else "API key"
                status_label = (
                    "API key configured" if ready else f"missing {env_var}"
                )
            if not dependency_available:
                ready = False
                status_label = "provider dependency unavailable"
            models = model_suggestions.get(name, [])
            tier_info: Dict[str, Any] = {}
            for model_name in models:
                mt = get_model_tier(provider_key, model_name)
                if mt:
                    tier_info[model_name] = {"tier": mt.tier, "cost1kIn": mt.cost_1k_in, "cost1kOut": mt.cost_1k_out, "speedRank": mt.speed_rank, "contextWindow": mt.context_window}
            result[name] = {
                "available": dependency_available,
                "ready": ready,
                "statusLabel": status_label,
                "models": models,
                "modelTiers": tier_info,
            }
        return result

    async def handle_get_startup_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return configured provider/model before full backend initialization."""
        del params
        _, config = self._ensure_config_loaded()
        return {
            "provider": str(config.model.provider),
            "model": str(config.model.model_name),
        }

    async def handle_get_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return the current configuration for the Rust TUI.

        Returns:
            Serialized config dictionary.
        """
        self._ensure_initialized()
        config = self.core.config
        if config is None:
            raise RuntimeError("Core configuration unavailable")
        provider_info = self.core.get_provider_info()
        config_path = None
        if self.core._config_manager is not None:
            config_path = str(self.core._config_manager.config_path)
        return {
            "provider": provider_info.get("name", "unknown"),
            "model": provider_info.get("model", "unknown"),
            "theme": config.ui.theme,
            "streaming": config.ui.enable_streaming,
            "showTokenCount": config.ui.show_token_count,
            "markdownRendering": config.ui.markdown_rendering,
            "showToolCalls": config.ui.show_tool_calls,
            "verboseLogging": config.ui.verbose_logging,
            "planMode": config.plan_mode.enabled,
            "checkpointing": config.checkpoint.enabled,
            "version": getattr(self.core, "_version", "0.4.0"),
            "permissionMode": self.permission_mode,
            "sandboxPreset": self._current_sandbox_preset(),
            "configFile": config_path,
        }

    async def handle_get_permissions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return current permission mode and effective rule scopes."""
        del params
        self._ensure_initialized()
        return {
            "permissionMode": self.permission_mode,
            "sandboxPreset": self._current_sandbox_preset(),
            "rules": self._permission_rules.list_rules(),
        }

    async def handle_set_permissions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update permission mode and/or permission rules.

        Params:
            mode?: default | acceptEdits | plan | bypassPermissions | dontAsk | prompt | auto-safe | danger-full-access
            addRule?: {scope, toolName, behavior, ruleContent}
            clearSessionRules?: bool
        """
        self._ensure_initialized()
        if self.core.config is None:
            raise RuntimeError("Core configuration unavailable")

        mode = params.get("mode")
        if mode is not None:
            try:
                parsed_mode = parse_permission_mode(mode)
            except ConfigurationError:
                raise InvalidParamsError(
                    "Invalid mode. Expected one of: default, acceptEdits, plan, bypassPermissions, "
                    "dontAsk, prompt, auto-safe, danger-full-access."
                )
            self.permission_mode = parsed_mode.value
            self.core.config.security.permission_mode = parsed_mode
            self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
            if self.core._config_manager is not None:
                self.core._config_manager.config = self.core.config
                self.core._config_manager.save()

        if bool(params.get("clearSessionRules", False)):
            self._permission_rules.clear_session_rules()

        add_rule = params.get("addRule")
        if isinstance(add_rule, dict):
            scope = str(add_rule.get("scope", "session")).strip().lower() or "session"
            tool_name = str(add_rule.get("toolName") or add_rule.get("tool_name") or "").strip()
            behavior = str(add_rule.get("behavior", "ask")).strip().lower()
            rule_content = str(add_rule.get("ruleContent") or add_rule.get("rule_content") or "").strip()
            if not tool_name:
                raise InvalidParamsError("addRule.toolName is required")
            if scope == "session":
                self._permission_rules.add_session_rule(
                    tool_name=tool_name,
                    behavior=behavior,
                    rule_content=rule_content,
                )
            else:
                self._permission_rules.add_persistent_rule(
                    scope=scope,
                    tool_name=tool_name,
                    behavior=behavior,
                    rule_content=rule_content,
                )

        await self._sync_provider_tool_visibility()

        return {
            "permissionMode": self.permission_mode,
            "sandboxPreset": self._current_sandbox_preset(),
            "rules": self._permission_rules.list_rules(),
        }

    async def handle_list_config_options(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List editable config leaf values in dot-notation form.

        Returns:
            options: [{"path", "value", "type", "isBoolean"}]
        """
        del params
        self._ensure_initialized()
        if self.core.config is None:
            raise RuntimeError("Core configuration unavailable")

        options: List[Dict[str, Any]] = []
        self._flatten_config_values(self.core.config.to_dict(), "", options)
        options.sort(key=lambda item: item["path"])

        config_path = None
        if self.core._config_manager is not None:
            config_path = str(self.core._config_manager.config_path)

        return {
            "options": options,
            "permissionMode": self.permission_mode,
            "configFile": config_path,
        }

    async def handle_set_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Set a config value by keyPath.

        Params:
            keyPath: Dot path (e.g. ui.enable_streaming)
            value: New value (JSON scalar/object/array)
        """
        self._ensure_initialized()
        if self.core.config is None:
            raise RuntimeError("Core configuration unavailable")
        if self.core._config_manager is None:
            raise RuntimeError("Config manager unavailable")

        key_path = str(params.get("keyPath", "")).strip()
        if not key_path:
            raise InvalidParamsError("Missing keyPath")
        if "value" not in params:
            raise InvalidParamsError("Missing value")

        old_value = copy.deepcopy(self._get_config_value(key_path))
        new_value = self._coerce_config_value(old_value, params["value"], key_path)
        self._set_config_value(key_path, new_value)

        provider_switched = False
        try:
            if key_path in {"model.provider", "model.model_name"}:
                provider_name = self.core.config.model.provider
                model_name = self.core.config.model.model_name
                await self.core.switch_provider(provider_name, model_name)
                provider_switched = True
            elif key_path.startswith("mcp_servers."):
                await self.core.reload_mcp_servers()

            if key_path == "security.permission_mode":
                mode = self.core.config.security.permission_mode
                if isinstance(mode, PermissionMode):
                    self.permission_mode = mode.value
                else:
                    self.permission_mode = str(mode)
                self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
            if key_path == "sandbox.default_preset":
                self._sandbox_preset = normalize_preset(
                    self.core.config.sandbox.default_preset,
                    fallback_permission_mode=self.permission_mode,
                )
                self.permission_mode = permission_mode_from_preset(self._sandbox_preset)

            self.core._config_manager.config = self.core.config
            self.core._config_manager.validate()
            self.core._config_manager.save()
        except Exception:
            self._set_config_value(key_path, old_value)
            if key_path == "security.permission_mode":
                mode = self.core.config.security.permission_mode
                self.permission_mode = mode.value if isinstance(mode, PermissionMode) else str(mode)
                self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
            if key_path == "sandbox.default_preset":
                self._sandbox_preset = normalize_preset(
                    self.core.config.sandbox.default_preset,
                    fallback_permission_mode=self.permission_mode,
                )
            raise

        return {
            "success": True,
            "keyPath": key_path,
            "value": self._jsonable_value(self._get_config_value(key_path)),
            "providerSwitched": provider_switched,
        }

    async def handle_toggle_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Toggle a boolean config key by keyPath.
        """
        self._ensure_initialized()
        key_path = str(params.get("keyPath", "")).strip()
        if not key_path:
            raise InvalidParamsError("Missing keyPath")

        current = self._get_config_value(key_path)
        if not isinstance(current, bool):
            raise InvalidParamsError(f"{key_path} is not a boolean value")

        return await self.handle_set_config(
            {
                "keyPath": key_path,
                "value": not current,
            }
        )

    @staticmethod
    def _normalize_provider_name(provider_name: str) -> str:
        provider = provider_name.strip().lower()
        if provider == "claude":
            return "anthropic"
        return provider

    @staticmethod
    def _mask_api_key(raw_key: Optional[str]) -> str:
        if not raw_key:
            return "(not set)"
        if len(raw_key) <= 8:
            return "*" * len(raw_key)
        return f"{raw_key[:4]}…{raw_key[-4:]}"

    def _ensure_config_loaded(self) -> Tuple[ConfigManager, Config]:
        """Load config metadata needed for API key/status operations before full init."""
        if self.core._config_manager is None:
            self.core._config_manager = ConfigManager(self.core._config_path)
        if self.core.config is None:
            self.core.config = self.core._config_manager.load()
        return self.core._config_manager, self.core.config

    async def handle_set_api_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store/update a provider API key for this session and secure local storage.

        Params:
            provider: Provider name (gemini, openai, anthropic, claude)
            apiKey: Raw API key value
            persist: Optional bool (default true) to persist in secure key store
            reloadActiveProvider: Optional bool (default true) to reinitialize current provider
        """
        config_manager, config = self._ensure_config_loaded()

        provider = self._normalize_provider_name(str(params.get("provider", "")))
        if not provider:
            raise InvalidParamsError("Missing provider")

        api_key = str(params.get("apiKey", "")).strip()
        if not api_key:
            raise InvalidParamsError("Missing apiKey")

        if provider == "ollama":
            raise InvalidParamsError("Ollama does not require an API key")

        provider_config = config.model.providers.get(provider)
        if provider_config is None:
            raise InvalidParamsError(f"Unknown provider: {provider}")

        persist = bool(params.get("persist", True))
        reload_active_provider = bool(params.get("reloadActiveProvider", True))

        env_var = provider_config.api_key_env_var
        os.environ[env_var] = api_key
        config.api_keys[provider] = api_key
        config_manager.config.api_keys[provider] = api_key

        stored_securely = False
        if persist:
            from ..api_key_manager import get_api_key_manager

            get_api_key_manager().store_key(
                provider,
                api_key,
                metadata={"env_var": env_var},
            )
            stored_securely = True

        active_provider_reloaded = False
        if (
            self.initialized
            and reload_active_provider
            and config.model.provider == provider
        ):
            # if server came up in soft-init (no key at boot), now complete full init
            if getattr(self, "_needs_provider_init", False):
                pending = getattr(self, "_pending_init_params", {}) or {}
                await self.core.initialize(
                    provider_name=pending.get("provider") or provider,
                    model_name=pending.get("model") or config.model.model_name,
                    api_key=api_key,
                )
                self._needs_provider_init = False
                self._pending_init_params = {}
                active_provider_reloaded = True
            else:
                await self.core.switch_provider(
                    provider,
                    config.model.model_name,
                )
                active_provider_reloaded = True

        return {
            "success": True,
            "provider": provider,
            "envVar": env_var,
            "persisted": stored_securely,
            "activeProviderReloaded": active_provider_reloaded,
            "maskedKey": self._mask_api_key(api_key),
        }

    async def handle_get_api_key_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return non-secret API key configuration status per provider.

        Params:
            provider: Optional provider filter.
        """
        _, config = self._ensure_config_loaded()

        requested_provider = str(params.get("provider", "")).strip()
        normalized_provider = self._normalize_provider_name(requested_provider)

        providers: List[str]
        if normalized_provider:
            if normalized_provider not in config.model.providers:
                raise InvalidParamsError(f"Unknown provider: {requested_provider}")
            providers = [normalized_provider]
        else:
            providers = sorted(config.model.providers.keys())

        secure_store = None
        secure_store_entries: Dict[str, Dict[str, Any]] = {}
        try:
            from ..api_key_manager import get_api_key_manager

            secure_store = get_api_key_manager()
            secure_store_entries = secure_store.list_providers()
        except Exception as error:  # pragma: no cover - defensive fallback
            self.logger.debug(f"API key manager unavailable: {error}")

        active_provider = self._normalize_provider_name(config.model.provider)
        status: Dict[str, Dict[str, Any]] = {}
        for provider in providers:
            provider_cfg = config.model.providers[provider]
            env_var = provider_cfg.api_key_env_var

            env_key = os.getenv(env_var)
            session_key = config.api_keys.get(provider)
            secure_key = None
            secure_available = provider in secure_store_entries
            if secure_available and secure_store is not None:
                secure_key = secure_store.get_key(provider)

            source = "none"
            key_value = None
            if env_key:
                source = "environment"
                key_value = env_key
            elif session_key:
                source = "session"
                key_value = session_key
            elif secure_key:
                source = "secure-store"
                key_value = secure_key

            status[provider] = {
                "configured": key_value is not None,
                "source": source,
                "envVar": env_var,
                "active": provider == active_provider,
                "persisted": secure_available,
                "masked": self._mask_api_key(key_value),
            }

        return {"providers": status}

    async def handle_test_api_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an API key by making a minimal API call (zero tokens)."""
        provider = self._normalize_provider_name(str(params.get("provider", "")))
        if not provider:
            raise InvalidParamsError("Missing provider")
        api_key = str(params.get("apiKey", "")).strip()
        if provider == "ollama":
            base_url = self._ollama_base_url()
            reachable = self._is_ollama_reachable(base_url)
            return {"valid": reachable, "error": None if reachable else f"Ollama not reachable at {base_url}"}
        if not api_key:
            raise InvalidParamsError("Missing apiKey")
        try:
            valid, error_msg = await self._probe_api_key(provider, api_key)
            return {"valid": valid, "error": error_msg}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def _probe_api_key(self, provider: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """Hit a lightweight model-list endpoint to verify an API key."""
        import urllib.error
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            req = Request(url, method="GET")
        elif provider == "openai":
            req = Request("https://api.openai.com/v1/models", method="GET")
            req.add_header("Authorization", f"Bearer {api_key}")
        elif provider == "anthropic":
            req = Request("https://api.anthropic.com/v1/models", method="GET")
            req.add_header("x-api-key", api_key)
            req.add_header("anthropic-version", "2023-06-01")
        elif provider == "openrouter":
            req = Request("https://openrouter.ai/api/v1/models", method="GET")
            req.add_header("Authorization", f"Bearer {api_key}")
        else:
            return False, f"No validation endpoint for provider: {provider}"
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: urlopen(req, timeout=30))
            return (True, None) if response.status == 200 else (False, f"HTTP {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Invalid API key (401 Unauthorized)"
            if e.code == 403:
                return False, "API key forbidden (403)"
            return False, f"HTTP error {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)

    def _get_repo_config(self):
        from ..repo_config import get_repo_config

        auto_migrate = True
        if self.core.config is not None:
            auto_migrate = self.core.config.history.auto_migrate_legacy_history
        return get_repo_config(enable_legacy_history_migration=auto_migrate)

    @staticmethod
    def _clamp_count(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(min(parsed, max_value), min_value)

    @staticmethod
    def _resolve_path(path_text: str) -> Path:
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    async def handle_list_sessions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List recent repo-scoped chat sessions."""
        self._ensure_initialized()

        limit = self._clamp_count(params.get("limit"), default=10, min_value=1, max_value=200)
        session_store = SessionStore(Path.cwd())
        snapshots = session_store.list(limit=limit)
        if snapshots:
            return {
                "sessions": [
                    {
                        "sessionId": str(entry.get("sessionId", "")),
                        "startedAt": str(entry.get("savedAt", "")),
                        "endedAt": None,
                        "model": str(entry.get("model") or "unknown"),
                        "messageCount": int(entry.get("messageCount") or 0),
                        "isActive": str(entry.get("sessionId", "")) == self.session_id,
                        "source": "snapshot",
                    }
                    for entry in snapshots
                ],
                "activeSessionId": self.session_id,
            }

        repo_config = self._get_repo_config()
        sessions = repo_config.list_sessions(limit=limit)
        active_session_id = (
            repo_config.current_session.session_id if repo_config.current_session else None
        )

        return {
            "sessions": [
                {
                    "sessionId": session.session_id,
                    "startedAt": session.started_at,
                    "endedAt": session.ended_at,
                    "model": session.model,
                    "messageCount": len(session.messages),
                    "isActive": session.session_id == active_session_id,
                }
                for session in sessions
            ],
            "activeSessionId": active_session_id,
        }

    async def handle_list_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return recent messages from the active repo-scoped session."""
        self._ensure_initialized()

        count = self._clamp_count(params.get("count"), default=10, min_value=1, max_value=1000)
        repo_config = self._get_repo_config()
        messages = repo_config.get_recent_messages(count=count)
        session_id = repo_config.current_session.session_id if repo_config.current_session else None

        return {
            "sessionId": session_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                for msg in messages
            ],
        }

    async def handle_search_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search recent messages in the active session history."""
        self._ensure_initialized()

        term = str(params.get("term", "")).strip()
        if not term:
            raise InvalidParamsError("Missing term")

        window = self._clamp_count(params.get("window"), default=1000, min_value=1, max_value=5000)
        limit = self._clamp_count(params.get("limit"), default=20, min_value=1, max_value=200)
        repo_config = self._get_repo_config()
        messages = repo_config.get_recent_messages(count=window)
        lowered = term.lower()

        matches = [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
            for msg in messages
            if lowered in msg.content.lower()
        ]

        return {
            "term": term,
            "totalMatches": len(matches),
            "matches": matches[:limit],
        }

    async def handle_list_skills(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List repo-local and user-global skills."""
        del params
        self._ensure_initialized()
        registry = self._skill_registry()
        return {"skills": [skill.to_dict() for skill in registry.list_skills()]}

    async def handle_get_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return details for a single skill."""
        self._ensure_initialized()
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("Missing skill name")
        registry = self._skill_registry()
        skill = registry.get_skill(name)
        if skill is None:
            raise InvalidParamsError(f"Unknown skill: {name}")
        payload = skill.to_dict()
        payload["content"] = skill.skill_file.read_text(encoding="utf-8")
        return payload

    async def handle_list_custom_commands(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List repo-local and user-global custom command wrappers."""
        del params
        self._ensure_initialized()
        registry = self._command_registry()
        return {"commands": [command.to_dict() for command in registry.list_commands()]}

    async def handle_get_custom_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return details for a single command wrapper."""
        self._ensure_initialized()
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("Missing command name")
        registry = self._command_registry()
        command = registry.get_command(name)
        if command is None:
            raise InvalidParamsError(f"Unknown command wrapper: {name}")
        payload = command.to_dict()
        payload["template"] = command.template
        return payload

    async def handle_run_custom_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Render and execute a custom command wrapper through the shared core."""
        self._ensure_initialized()
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("Missing command name")
        args_text = str(params.get("argsText", "") or "")
        registry = self._command_registry()
        prompt = registry.render_prompt(name, args_text=args_text)
        response = await self.core.send_message_sync(prompt)
        return {"name": name, "prompt": prompt, "content": response}

    async def handle_create_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a durable task and optionally start a background worker."""
        self._ensure_initialized()
        prompt = str(params.get("prompt", "") or "").strip()
        if not prompt:
            raise InvalidParamsError("Missing prompt")
        title = str(params.get("title", "") or "").strip()
        source = str(params.get("source", "manual") or "manual")
        metadata = params.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        base_execution = metadata.get("execution")
        if base_execution is not None and not isinstance(base_execution, dict):
            raise InvalidParamsError("metadata.execution must be an object")
        execution = dict(base_execution) if isinstance(base_execution, dict) else {}
        execution.update(self._coerce_task_execution_metadata(params.get("execution")))
        if execution:
            metadata["execution"] = execution
        sandbox_preset = normalize_preset(
            params.get("sandboxPreset"),
            fallback_permission_mode=self.permission_mode,
        )
        auto_start = bool(params.get("autoStart", False))
        requires_approval = bool(params.get("requiresApproval", False))
        auto_approve = bool(params.get("autoApprove", False))
        if self.core.config is not None and getattr(self.core.config, "tasks", None) is not None:
            if sandbox_preset in {"read-only", "review-only"} and "autoStart" not in params:
                auto_start = bool(self.core.config.tasks.auto_start_read_only)
            if sandbox_preset == "workspace-write" and "autoStart" not in params:
                auto_start = bool(self.core.config.tasks.auto_start_workspace_write)
        task = self._task_manager_instance().create_task(
            title=title or prompt.splitlines()[0][:80],
            prompt=prompt,
            sandbox_preset=sandbox_preset,
            source=source,
            metadata=metadata,
            auto_start=auto_start and not requires_approval,
            requires_approval=requires_approval,
            auto_approve=auto_approve,
        )
        return {"task": task.to_dict()}

    async def handle_list_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List durable task records or inbox items."""
        self._ensure_initialized()
        statuses = params.get("statuses")
        if not isinstance(statuses, list):
            statuses = None
        limit = self._clamp_count(params.get("limit"), default=50, min_value=1, max_value=500)
        inbox_only = bool(params.get("inboxOnly", False))
        tasks = self._task_manager_instance().list_tasks(
            statuses=[str(status) for status in statuses] if statuses else None,
            limit=limit,
            inbox_only=inbox_only,
        )
        return {"tasks": [task.to_dict() for task in tasks]}

    async def handle_get_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a single task record."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().get_task(task_id)
        if task is None:
            raise InvalidParamsError(f"Unknown task: {task_id}")
        return {"task": task.to_dict()}

    async def handle_start_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a queued or approved task worker."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().start_task_process(task_id)
        return {"task": task.to_dict()}

    async def handle_approve_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Approve a queued task and optionally start it."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        auto_start = bool(params.get("autoStart", True))
        task = self._task_manager_instance().approve_task(task_id, auto_start=auto_start)
        return {"task": task.to_dict()}

    async def handle_cancel_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a task."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().cancel_task(task_id)
        return {"task": task.to_dict()}

    async def handle_retry_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create and optionally start a retry task."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        auto_start = params.get("autoStart")
        task = self._task_manager_instance().retry_task(
            task_id,
            auto_start=None if auto_start is None else bool(auto_start),
        )
        return {
            "task": task.to_dict(),
            "runs": self._task_manager_instance().task_runs(task.task_id, limit=10),
        }

    async def handle_replay_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create and optionally start a replay task."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        auto_start = params.get("autoStart")
        task = self._task_manager_instance().replay_task(
            task_id,
            auto_start=None if auto_start is None else bool(auto_start),
        )
        return {
            "task": task.to_dict(),
            "runs": self._task_manager_instance().task_runs(task.task_id, limit=10),
        }

    async def handle_create_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a durable scheduled automation backed by the task runner."""
        self._ensure_initialized()
        prompt = str(params.get("prompt", "") or "").strip()
        if not prompt:
            raise InvalidParamsError("Missing prompt")
        schedule = params.get("schedule")
        if not isinstance(schedule, dict):
            raise InvalidParamsError("schedule must be an object")

        name = str(params.get("name", "") or "").strip()
        metadata = params.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        base_execution = metadata.get("execution")
        if base_execution is not None and not isinstance(base_execution, dict):
            raise InvalidParamsError("metadata.execution must be an object")
        execution = dict(base_execution) if isinstance(base_execution, dict) else {}
        execution.update(self._coerce_task_execution_metadata(params.get("execution")))
        if execution:
            metadata["execution"] = execution

        sandbox_preset = normalize_preset(
            params.get("sandboxPreset"),
            fallback_permission_mode=self.permission_mode,
        )
        automation = self._automation_manager_instance().create_automation(
            name=name or prompt.splitlines()[0][:80],
            prompt=prompt,
            schedule=schedule,
            sandbox_preset=sandbox_preset,
            enabled=bool(params.get("enabled", True)),
            requires_approval=bool(params.get("requiresApproval", False)),
            metadata=metadata,
            auto_approve=bool(params.get("autoApprove", False)),
        )
        return {"automation": automation.to_dict()}

    async def handle_list_automations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List scheduled automations."""
        self._ensure_initialized()
        enabled_param = params.get("enabled")
        enabled = None if enabled_param is None else bool(enabled_param)
        limit = self._clamp_count(params.get("limit"), default=100, min_value=1, max_value=500)
        automations = self._automation_manager_instance().list_automations(
            enabled=enabled,
            limit=limit,
        )
        return {"automations": [automation.to_dict() for automation in automations]}

    async def handle_get_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return one automation record."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        automation = self._automation_manager_instance().get_automation(automation_id)
        if automation is None:
            raise InvalidParamsError(f"Unknown automation: {automation_id}")
        return {"automation": automation.to_dict()}

    async def handle_set_automation_enabled(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Enable or disable an automation."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        if "enabled" not in params:
            raise InvalidParamsError("Missing enabled")
        automation = self._automation_manager_instance().set_enabled(
            automation_id,
            bool(params.get("enabled")),
        )
        return {"automation": automation.to_dict()}

    async def handle_run_automation_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch one automation immediately and return the resulting task."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        task = self._automation_manager_instance().run_now(automation_id)
        return {"task": task.to_dict()}

    async def handle_run_due_automations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run all automations currently due."""
        self._ensure_initialized()
        limit = self._clamp_count(params.get("limit"), default=20, min_value=1, max_value=200)
        tasks = self._automation_manager_instance().run_due(limit=limit)
        return {"tasks": [task.to_dict() for task in tasks]}

    async def handle_get_automation_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return recent run history for one automation."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        limit = self._clamp_count(params.get("limit"), default=25, min_value=1, max_value=200)
        history = self._automation_manager_instance().history(automation_id, limit=limit)
        return {"runs": history}

    async def handle_replay_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch an automation replay task."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        task = self._automation_manager_instance().replay(automation_id)
        return {"task": task.to_dict()}

    async def handle_list_checkpoints(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available checkpoints with storage metadata."""
        self._ensure_initialized()

        manager = self.core.checkpoint_manager
        if manager is None:
            return {
                "available": False,
                "checkpoints": [],
                "storageSizeBytes": 0,
                "storagePath": "",
            }

        limit = self._clamp_count(params.get("limit"), default=20, min_value=1, max_value=200)
        checkpoints = manager.list_checkpoints(limit=limit)
        return {
            "available": True,
            "checkpoints": [
                {
                    "checkpointId": cp.checkpoint_id,
                    "createdAt": cp.created_at,
                    "description": cp.description,
                    "operationType": cp.operation_type,
                    "fileCount": cp.get_file_count(),
                    "totalSizeBytes": cp.get_total_size(),
                    "tags": cp.tags,
                }
                for cp in checkpoints
            ],
            "storageSizeBytes": manager.get_storage_size(),
            "storagePath": str(manager.checkpoints_dir),
        }

    def _discover_default_checkpoint_files(self, limit: int = 10) -> List[str]:
        files: List[str] = []
        for path in Path.cwd().rglob("*.py"):
            if not path.is_file():
                continue
            path_parts = set(path.parts)
            if ".git" in path_parts or ".poor-cli" in path_parts:
                continue
            files.append(str(path.resolve()))
            if len(files) >= limit:
                break
        return files

    async def handle_create_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a manual checkpoint and return summary metadata."""
        self._ensure_initialized()

        manager = self.core.checkpoint_manager
        if manager is None:
            raise PoorCLIError("Checkpoint system not available")

        description = str(params.get("description", "Manual checkpoint")).strip() or "Manual checkpoint"
        operation_type = str(params.get("operationType", "manual")).strip() or "manual"

        raw_file_paths = params.get("filePaths")
        file_paths: List[str]
        if raw_file_paths is None:
            file_paths = self._discover_default_checkpoint_files(limit=10)
        elif isinstance(raw_file_paths, list):
            file_paths = [str(self._resolve_path(str(path))) for path in raw_file_paths if str(path).strip()]
        else:
            raise InvalidParamsError("filePaths must be a list of file paths")

        if not file_paths:
            raise PoorCLIError("No files found to checkpoint")

        raw_tags = params.get("tags")
        tags: Optional[List[str]] = None
        if isinstance(raw_tags, list):
            tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]

        checkpoint = await asyncio.to_thread(
            manager.create_checkpoint,
            file_paths,
            description,
            operation_type,
            tags,
        )

        return {
            "checkpointId": checkpoint.checkpoint_id,
            "createdAt": checkpoint.created_at,
            "description": checkpoint.description,
            "operationType": checkpoint.operation_type,
            "fileCount": checkpoint.get_file_count(),
            "totalSizeBytes": checkpoint.get_total_size(),
            "tags": checkpoint.tags,
        }

    async def handle_restore_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Restore a checkpoint by ID (or restore the latest checkpoint)."""
        self._ensure_initialized()

        manager = self.core.checkpoint_manager
        if manager is None:
            raise PoorCLIError("Checkpoint system not available")

        requested_id = str(params.get("checkpointId", "")).strip()
        if not requested_id or requested_id == "last":
            checkpoints = manager.list_checkpoints(limit=1)
            if not checkpoints:
                raise PoorCLIError("No checkpoints available to restore")
            checkpoint = checkpoints[0]
        else:
            checkpoint = manager.get_checkpoint(requested_id)
            if checkpoint is None:
                raise InvalidParamsError(f"Checkpoint not found: {requested_id}")

        restored_count = await asyncio.to_thread(
            manager.restore_checkpoint,
            checkpoint.checkpoint_id,
        )

        return {
            "checkpointId": checkpoint.checkpoint_id,
            "restoredFiles": restored_count,
            "description": checkpoint.description,
            "createdAt": checkpoint.created_at,
        }

    async def handle_preview_checkpoint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview what restoring a checkpoint would change."""
        self._ensure_initialized()
        manager = self.core.checkpoint_manager
        if manager is None:
            raise PoorCLIError("Checkpoint system not available")
        checkpoint_id = str(params.get("checkpointId", "")).strip()
        if not checkpoint_id:
            raise InvalidParamsError("checkpointId is required")
        files = await asyncio.to_thread(manager.preview_checkpoint, checkpoint_id)
        return {"checkpointId": checkpoint_id, "files": files}

    async def handle_compare_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a unified diff for two files."""
        self._ensure_initialized()

        file1 = str(params.get("file1", "")).strip()
        file2 = str(params.get("file2", "")).strip()
        if not file1 or not file2:
            raise InvalidParamsError("Missing file paths. Usage: /diff <file1> <file2>")

        path1 = self._resolve_path(file1)
        path2 = self._resolve_path(file2)
        if not path1.is_file():
            raise InvalidParamsError(f"File not found: {file1}")
        if not path2.is_file():
            raise InvalidParamsError(f"File not found: {file2}")

        text1 = path1.read_text(encoding="utf-8", errors="ignore")
        text2 = path2.read_text(encoding="utf-8", errors="ignore")
        diff = "".join(
            difflib.unified_diff(
                text1.splitlines(keepends=True),
                text2.splitlines(keepends=True),
                fromfile=str(path1),
                tofile=str(path2),
            )
        )
        if not diff:
            diff = "(No differences)"

        return {"diff": diff}

    async def handle_export_conversation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Export active-session conversation history to json/md/txt."""
        self._ensure_initialized()

        export_format = str(params.get("format", "json")).strip().lower() or "json"
        if export_format == "markdown":
            export_format = "md"
        if export_format not in {"json", "md", "txt"}:
            raise InvalidParamsError("Invalid format. Supported: json, md, txt")

        repo_config = self._get_repo_config()
        if not repo_config.current_session:
            raise PoorCLIError("No active session to export")

        messages = repo_config.get_recent_messages(count=100000)
        if not messages:
            raise PoorCLIError("No messages in current session")

        session = repo_config.current_session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{session.session_id[:8]}_{timestamp}.{export_format}"
        output_path = Path.cwd() / filename

        if export_format == "json":
            payload = {
                "session_id": session.session_id,
                "exported_at": datetime.now().isoformat(),
                "provider": self.core.config.model.provider if self.core.config else "unknown",
                "model": self.core.config.model.model_name if self.core.config else "unknown",
                "message_count": len(messages),
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                    }
                    for msg in messages
                ],
            }
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        elif export_format == "md":
            lines = [
                "# Conversation Export",
                "",
                f"**Session ID:** {session.session_id}",
                f"**Provider:** {self.core.config.model.provider if self.core.config else 'unknown'}",
                f"**Model:** {self.core.config.model.model_name if self.core.config else 'unknown'}",
                f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Messages:** {len(messages)}",
                "",
                "---",
                "",
            ]
            for idx, msg in enumerate(messages, 1):
                role_name = "User" if msg.role == "user" else "Assistant"
                lines.extend(
                    [
                        f"## Message {idx}: {role_name}",
                        "",
                        f"*{msg.timestamp}*",
                        "",
                        msg.content,
                        "",
                        "---",
                        "",
                    ]
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            lines = [
                "=" * 60,
                "CONVERSATION EXPORT",
                "=" * 60,
                "",
                f"Session ID: {session.session_id}",
                f"Provider: {self.core.config.model.provider if self.core.config else 'unknown'}",
                f"Model: {self.core.config.model.model_name if self.core.config else 'unknown'}",
                f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Messages: {len(messages)}",
                "",
                "=" * 60,
                "",
            ]
            for msg in messages:
                role_name = "USER" if msg.role == "user" else "ASSISTANT"
                lines.extend(
                    [
                        f"[{role_name}] {msg.timestamp}",
                        "-" * 60,
                        msg.content,
                        "",
                    ]
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")

        return {
            "filePath": str(output_path),
            "format": export_format,
            "messageCount": len(messages),
            "sizeBytes": output_path.stat().st_size,
        }

    def _ensure_service_controls_available(self) -> None:
        """Disallow service lifecycle controls from nested multiplayer room engines."""
        if self._embedded_multiplayer_room:
            raise InvalidParamsError(
                "Service controls are unavailable inside multiplayer room sessions"
            )

    @staticmethod
    def _normalize_service_name(raw_name: Any) -> str:
        """Normalize and validate user-provided service names."""
        service_name = str(raw_name or "").strip().lower()
        if not service_name:
            raise InvalidParamsError("Missing service name")

        if not all(ch.isalnum() or ch in {"-", "_", "."} for ch in service_name):
            raise InvalidParamsError(
                "Service name must contain only letters, numbers, '-', '_' or '.'"
            )
        return service_name

    @staticmethod
    def _parse_service_command(raw_command: Any) -> List[str]:
        """Parse a command (string or argv list) into argv parts."""
        if raw_command is None:
            return []

        parts: List[str]
        if isinstance(raw_command, str):
            command_text = raw_command.strip()
            if not command_text:
                return []
            try:
                parts = shlex.split(command_text)
            except ValueError as error:
                raise InvalidParamsError(f"Invalid command syntax: {error}") from error
        elif isinstance(raw_command, list):
            parts = [str(item).strip() for item in raw_command if str(item).strip()]
        else:
            raise InvalidParamsError("command must be a string or a list of argv tokens")

        if not parts:
            raise InvalidParamsError("command cannot be empty")
        return parts

    @staticmethod
    def _service_default_command(service_name: str) -> Optional[List[str]]:
        """Return built-in command defaults for known local services."""
        if service_name == "ollama":
            return ["ollama", "serve"]
        return None

    @staticmethod
    def _render_command_display(command_parts: List[str]) -> str:
        """Render argv parts to a user-facing shell-safe display string."""
        return " ".join(shlex.quote(part) for part in command_parts)

    @staticmethod
    def _resolve_service_executable(
        command_name: str,
        service_name: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a command to an executable path, with service-specific fallbacks."""
        if not command_name:
            return None

        command_path = Path(command_name).expanduser()
        if "/" in command_name or command_path.is_absolute():
            if command_path.exists():
                return str(command_path)
            return None

        resolved = shutil.which(command_name)
        if resolved:
            return resolved

        # GUI-launched apps on macOS often lack Homebrew PATH entries.
        # Keep this narrowly scoped to Ollama so other services remain explicit.
        if (service_name or "").strip().lower() == "ollama" or command_name == "ollama":
            fallback_candidates: List[str] = []

            env_override = os.environ.get("OLLAMA_BIN") or os.environ.get("OLLAMA_PATH")
            if env_override:
                fallback_candidates.append(env_override)

            if sys.platform == "darwin":
                fallback_candidates.extend(
                    ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama"]
                )
            elif os.name == "nt":
                fallback_candidates.extend(
                    [
                        r"C:\\Program Files\\Ollama\\ollama.exe",
                        r"C:\\Program Files (x86)\\Ollama\\ollama.exe",
                    ]
                )
            else:
                fallback_candidates.extend(
                    ["/usr/local/bin/ollama", "/usr/bin/ollama", "/snap/bin/ollama"]
                )

            for candidate in fallback_candidates:
                candidate_path = Path(candidate).expanduser()
                if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
                    return str(candidate_path)

        return None

    def _ollama_base_url(self) -> str:
        """Resolve configured Ollama base URL with a safe default."""
        default_base_url = "http://localhost:11434"
        if self.core.config is None:
            return default_base_url

        provider_cfg = self.core.config.model.providers.get("ollama")
        if provider_cfg is None:
            return default_base_url
        return str(provider_cfg.base_url or default_base_url).strip() or default_base_url

    @staticmethod
    def _is_tcp_endpoint_reachable(host: str, port: int, timeout_seconds: float = 0.8) -> bool:
        """Cheap TCP readiness check used for local service health probes."""
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds):
                return True
        except OSError:
            return False

    def _is_ollama_reachable(self, base_url: Optional[str] = None) -> bool:
        """Check whether the configured Ollama endpoint is accepting TCP connections."""
        target_url = (base_url or self._ollama_base_url()).strip()
        parsed = urlparse(target_url)
        host = parsed.hostname or "localhost"
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return self._is_tcp_endpoint_reachable(host, port)

    def _list_ollama_models(self, base_url: Optional[str] = None) -> List[str]:
        """Fetch installed Ollama models from /api/tags."""
        target_url = (base_url or self._ollama_base_url()).rstrip("/")
        if not target_url:
            return []

        request = Request(f"{target_url}/api/tags", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:
            return []

        models: List[str] = []
        for entry in payload.get("models", []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                models.append(name.strip())

        deduped: List[str] = []
        seen = set()
        for model in models:
            if model in seen:
                continue
            seen.add(model)
            deduped.append(model)
        return deduped

    async def _stop_managed_service_locked(
        self,
        service: ManagedServiceRuntime,
        timeout_seconds: float = 5.0,
    ) -> bool:
        """Stop a managed service process and close log handles (lock must be held)."""
        was_running = service.process.returncode is None

        if was_running:
            self._signal_managed_service_process(service, signal.SIGTERM)
            try:
                await asyncio.wait_for(service.process.wait(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                self._signal_managed_service_process(service, signal.SIGKILL)
                with contextlib.suppress(Exception):
                    await service.process.wait()

        if service.process.returncode is not None:
            service.last_exit_code = service.process.returncode

        if getattr(service, "log_handle", None) is not None:
            with contextlib.suppress(Exception):
                service.log_handle.flush()
                service.log_handle.close()
            service.log_handle = None

        return was_running

    async def _shutdown_managed_services_locked(self) -> None:
        """Stop every managed service (lock must be held)."""
        for service in self._managed_services.values():
            with contextlib.suppress(Exception):
                await self._stop_managed_service_locked(service)
        self._managed_services.clear()

    def _refresh_managed_service_locked(
        self,
        service_name: str,
    ) -> Optional[ManagedServiceRuntime]:
        """Sync cached service runtime state with the underlying process."""
        service = self._managed_services.get(service_name)
        if service is None:
            return None
        if service.process.returncode is None:
            return service

        service.last_exit_code = service.process.returncode
        if getattr(service, "log_handle", None) is not None:
            with contextlib.suppress(Exception):
                service.log_handle.flush()
                service.log_handle.close()
            service.log_handle = None
        return service

    def _service_payload_locked(
        self,
        service_name: str,
        *,
        created: bool = False,
        stopped: bool = False,
        message: str = "",
    ) -> Dict[str, Any]:
        """Build stable status payload for a managed/external service."""
        managed = self._refresh_managed_service_locked(service_name)
        managed_running = False

        payload: Dict[str, Any] = {
            "service": service_name,
            "running": False,
            "managed": managed is not None,
            "managedRunning": False,
            "external": False,
            "created": created,
            "stopped": stopped,
            "message": message,
        }

        default_command = self._service_default_command(service_name)
        command_for_availability = (
            managed.command if managed is not None else (default_command or [])
        )
        executable_path = (
            self._resolve_service_executable(
                command_for_availability[0],
                service_name=service_name,
            )
            if command_for_availability
            else None
        )
        payload["available"] = executable_path is not None
        if executable_path is not None:
            payload["executable"] = executable_path

        if managed is not None:
            managed_running = managed.process.returncode is None
            if managed.process.returncode is not None and managed.last_exit_code is None:
                managed.last_exit_code = managed.process.returncode

            payload.update(
                {
                    "managedRunning": managed_running,
                    "running": managed_running,
                    "pid": managed.process.pid if managed_running else None,
                    "command": managed.command_display,
                    "cwd": managed.cwd,
                    "logPath": str(managed.log_path),
                    "startedAt": managed.started_at,
                    "exitCode": managed.last_exit_code,
                }
            )
        elif default_command is not None:
            payload["command"] = self._render_command_display(default_command)
            payload["logPath"] = str(self._service_logs_dir / f"{service_name}.log")

        if service_name == "ollama":
            base_url = self._ollama_base_url()
            healthy = self._is_ollama_reachable(base_url)
            external = healthy and not managed_running
            payload["baseUrl"] = base_url
            payload["healthy"] = healthy
            payload["external"] = external
            payload["running"] = managed_running or external

        return payload

    @staticmethod
    def _tail_log_file(log_path: Path, line_count: int) -> str:
        """Read the last N lines from a text log file."""
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            tail = deque(handle, maxlen=max(line_count, 1))
        return "".join(tail).strip()

    @staticmethod
    def _service_log_rotation_threshold_bytes() -> int:
        """Maximum managed service log size before rotating on next launch."""
        return 5 * 1024 * 1024

    def _rotate_service_log_if_needed(self, log_path: Path) -> None:
        threshold_bytes = int(self._service_log_rotation_threshold_bytes())
        if threshold_bytes <= 0 or not log_path.exists():
            return

        with contextlib.suppress(OSError):
            if log_path.stat().st_size < threshold_bytes:
                return

        rotated_path = log_path.with_name(f"{log_path.name}.1")
        with contextlib.suppress(OSError):
            rotated_path.unlink()
        with contextlib.suppress(OSError):
            log_path.replace(rotated_path)

    def _normalize_service_cwd(self, cwd_path: Path, raw_cwd: str) -> str:
        resolved = cwd_path.resolve()
        if not resolved.is_dir():
            raise InvalidParamsError(f"cwd is not a directory: {raw_cwd}")
        if self._trusted_workspace_enabled() and not self._path_is_trusted(str(resolved)):
            raise InvalidParamsError(
                f"cwd falls outside trusted workspace roots: {resolved}"
            )
        return str(resolved)

    @staticmethod
    def _signal_managed_service_process(service: ManagedServiceRuntime, sig: int) -> bool:
        process = service.process
        pid = getattr(process, "pid", None)

        if pid is not None and int(pid) > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(int(pid), sig)
                return True
            except PermissionError:
                return True
            except OSError:
                pass

        try:
            if sig == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            return False
        return True

    async def handle_start_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start a managed local background service.

        Params:
            name: Service identifier (e.g. ollama)
            command: Optional command string or argv array
            cwd: Optional working directory
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        service_name = self._normalize_service_name(params.get("name"))
        command_parts = self._parse_service_command(params.get("command"))
        cwd_value: Optional[str] = None

        raw_cwd = params.get("cwd")
        if raw_cwd not in (None, ""):
            cwd_path = self._resolve_path(str(raw_cwd))
            cwd_value = self._normalize_service_cwd(cwd_path, str(raw_cwd))

        async with self._get_service_lock():
            existing = self._refresh_managed_service_locked(service_name)
            if existing is not None and existing.process.returncode is None:
                return self._service_payload_locked(
                    service_name,
                    created=False,
                    stopped=False,
                    message="Service is already running.",
                )

            if not command_parts:
                if existing is not None and existing.command:
                    command_parts = list(existing.command)
                else:
                    default_command = self._service_default_command(service_name)
                    if default_command is not None:
                        command_parts = list(default_command)

            if not command_parts:
                raise InvalidParamsError(
                    "Missing command. Usage: /service start <name> <command...>"
                )

            if cwd_value is None and existing is not None and existing.cwd:
                cwd_value = self._normalize_service_cwd(Path(existing.cwd), existing.cwd)

            executable_path = self._resolve_service_executable(
                command_parts[0],
                service_name=service_name,
            )
            if executable_path is None:
                raise InvalidParamsError(
                    f"Command not found for service '{service_name}': {command_parts[0]}"
                )
            command_parts[0] = executable_path

            if (
                service_name == "ollama"
                and self._is_ollama_reachable()
                and (existing is None or existing.process.returncode is not None)
            ):
                return self._service_payload_locked(
                    service_name,
                    created=False,
                    stopped=False,
                    message="Ollama is already running (external to poor-cli).",
                )

            self._service_logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._service_logs_dir / f"{service_name}.log"
            self._rotate_service_log_if_needed(log_path)

            if existing is not None and getattr(existing, "log_handle", None) is not None:
                with contextlib.suppress(Exception):
                    existing.log_handle.flush()
                    existing.log_handle.close()

            log_handle = open(log_path, "ab")
            try:
                spawn_kwargs = {
                    "stdout": log_handle,
                    "stderr": asyncio.subprocess.STDOUT,
                    "cwd": cwd_value,
                }
                if hasattr(os, "killpg"):
                    spawn_kwargs["start_new_session"] = True
                process = await asyncio.create_subprocess_exec(
                    *command_parts,
                    **spawn_kwargs,
                )
            except Exception:
                with contextlib.suppress(Exception):
                    log_handle.close()
                raise

            runtime = ManagedServiceRuntime(
                name=service_name,
                command=list(command_parts),
                command_display=self._render_command_display(command_parts),
                cwd=cwd_value,
                process=process,
                log_path=log_path,
                log_handle=log_handle,
                started_at=datetime.now().isoformat(),
            )
            self._managed_services[service_name] = runtime

            # Catch immediate launch failures and surface actionable output.
            await asyncio.sleep(0.15)
            if process.returncode is not None:
                runtime.last_exit_code = process.returncode
                await self._stop_managed_service_locked(runtime, timeout_seconds=0.1)
                raise PoorCLIError(
                    f"Service '{service_name}' exited immediately with code "
                    f"{runtime.last_exit_code}. Check logs: {log_path}"
                )

            message = "Service started."
            if service_name == "ollama":
                # Ollama can take a few seconds before port 11434 accepts requests.
                # Wait briefly so `/ollama start` is reliably usable right away.
                warmed_up = False
                for _ in range(40):  # ~8 seconds
                    if self._is_ollama_reachable():
                        warmed_up = True
                        break
                    if process.returncode is not None:
                        runtime.last_exit_code = process.returncode
                        await self._stop_managed_service_locked(runtime, timeout_seconds=0.1)
                        raise PoorCLIError(
                            f"Service '{service_name}' exited during startup with code "
                            f"{runtime.last_exit_code}. Check logs: {log_path}"
                        )
                    await asyncio.sleep(0.2)
                if not warmed_up:
                    message = (
                        "Service started, but Ollama is still warming up. "
                        "Run `/ollama status` and retry shortly."
                    )

            return self._service_payload_locked(
                service_name,
                created=True,
                stopped=False,
                message=message,
            )

    async def handle_stop_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop a managed local background service.

        Params:
            name: Service identifier
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        service_name = self._normalize_service_name(params.get("name"))

        async with self._get_service_lock():
            service = self._managed_services.get(service_name)
            if service is None:
                payload = self._service_payload_locked(
                    service_name,
                    created=False,
                    stopped=False,
                    message="Service is not managed by poor-cli.",
                )
                if service_name == "ollama" and payload.get("external"):
                    payload["message"] = (
                        "Ollama is running externally and cannot be stopped by poor-cli."
                    )
                return payload

            was_running = await self._stop_managed_service_locked(service)
            return self._service_payload_locked(
                service_name,
                created=False,
                stopped=was_running,
                message="Service stopped." if was_running else "Service was already stopped.",
            )

    async def handle_get_service_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get service status for one service or all known services.

        Params:
            name: Optional service identifier filter
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        requested_name = str(params.get("name", "")).strip()
        async with self._get_service_lock():
            if requested_name:
                service_name = self._normalize_service_name(requested_name)
                return self._service_payload_locked(service_name)

            names = set(self._managed_services.keys())
            names.add("ollama")
            return {
                "services": [
                    self._service_payload_locked(service_name)
                    for service_name in sorted(names)
                ]
            }

    async def handle_get_service_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return tail logs for a managed local service.

        Params:
            name: Service identifier
            lines: Optional number of tail lines (default 80, max 500)
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        service_name = self._normalize_service_name(params.get("name"))
        raw_lines = params.get("lines", 80)
        try:
            line_count = int(raw_lines)
        except (TypeError, ValueError) as error:
            raise InvalidParamsError("lines must be an integer") from error
        line_count = max(1, min(line_count, 500))

        async with self._get_service_lock():
            payload = self._service_payload_locked(service_name)
            service = self._managed_services.get(service_name)
            if service is not None:
                log_path = service.log_path
            elif service_name == "ollama":
                log_path = self._service_logs_dir / "ollama.log"
            else:
                raise InvalidParamsError(f"Unknown service: {service_name}")

        exists = log_path.is_file()
        content = ""
        if exists:
            content = self._tail_log_file(log_path, line_count)

        return {
            "service": service_name,
            "lines": line_count,
            "logPath": str(log_path),
            "exists": exists,
            "content": content,
            "status": payload,
        }

    def _ensure_host_controls_available(self) -> None:
        """Disallow host lifecycle controls from nested multiplayer room engines."""
        if self._embedded_multiplayer_room:
            raise InvalidParamsError(
                "Host controls are unavailable inside multiplayer room sessions"
            )

    @staticmethod
    def _normalize_multiplayer_room_names(
        raw_rooms: Any,
        fallback_room: str = "",
    ) -> List[str]:
        """Normalize and validate requested room names."""
        candidates: List[str] = []
        if isinstance(raw_rooms, list):
            candidates.extend(str(item) for item in raw_rooms)
        elif isinstance(raw_rooms, str):
            candidates.append(raw_rooms)
        elif raw_rooms is not None:
            raise InvalidParamsError("rooms must be a list of names or a single string")

        if fallback_room.strip():
            candidates.append(fallback_room.strip())

        if not candidates:
            candidates.append("dev")

        normalized: List[str] = []
        for raw_room in candidates:
            room_name = raw_room.strip()
            if not room_name:
                continue
            if len(room_name) > 64:
                raise InvalidParamsError(f"Room name too long: {room_name}")
            if not all(ch.isalnum() or ch in {"-", "_", "."} for ch in room_name):
                raise InvalidParamsError(
                    f"Invalid room name: {room_name}. Use letters, numbers, '-', '_' or '.'."
                )
            if room_name not in normalized:
                normalized.append(room_name)

        if not normalized:
            raise InvalidParamsError("At least one non-empty room name is required")

        return normalized

    @staticmethod
    def _resolve_multiplayer_share_host(bind_host: str) -> str:
        """Resolve a shareable host/IP when binding to wildcard interfaces."""
        host = bind_host.strip()
        if host and host not in {"0.0.0.0", "::"}:
            return host

        try:
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
                sock.connect(("8.8.8.8", 80))
                lan_ip = sock.getsockname()[0]
                if lan_ip and not lan_ip.startswith("127."):
                    return lan_ip
        except OSError:
            pass

        return "127.0.0.1"

    @staticmethod
    def _build_multiplayer_ice_servers(config: Config) -> List[Dict[str, Any]]:
        """Build ICE server configuration from loaded config and env-backed TURN creds."""
        multiplayer = config.multiplayer
        ice_servers = [dict(entry) for entry in (multiplayer.ice_servers or [])]

        turn_urls = [str(url).strip() for url in (multiplayer.turn_urls or []) if str(url).strip()]
        if not turn_urls:
            return ice_servers

        username = os.environ.get(multiplayer.turn_username_env, "").strip()
        credential = os.environ.get(multiplayer.turn_credential_env, "").strip()
        if not username or not credential:
            return ice_servers

        turn_entry: Dict[str, Any] = {
            "urls": turn_urls,
            "username": username,
            "credential": credential,
        }
        if multiplayer.turn_realm.strip():
            turn_entry["credentialType"] = "password"
            turn_entry["realm"] = multiplayer.turn_realm.strip()
        ice_servers.append(turn_entry)
        return ice_servers

    @staticmethod
    def _is_port_bindable(bind_host: str, port: int) -> bool:
        """Return True when the given host/port pair can be bound."""
        try:
            address_info = socket.getaddrinfo(bind_host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise InvalidParamsError(f"Invalid bind host: {bind_host}") from e

        for family, socktype, proto, _, sockaddr in address_info:
            with contextlib.closing(socket.socket(family, socktype, proto)) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(sockaddr)
                    return True
                except OSError:
                    continue

        return False

    def _select_multiplayer_port(self, bind_host: str, requested_port: Optional[int]) -> int:
        """Choose a usable host port, preferring 8765+ when unspecified."""
        if requested_port is not None:
            if requested_port <= 0 or requested_port > 65535:
                raise InvalidParamsError("port must be between 1 and 65535")
            if not self._is_port_bindable(bind_host, requested_port):
                raise InvalidParamsError(f"Port {requested_port} is unavailable on {bind_host}")
            return requested_port

        for port_candidate in range(8765, 8865):
            if self._is_port_bindable(bind_host, port_candidate):
                return port_candidate

        raise InvalidParamsError(
            "Unable to find an open port in the 8765-8864 range. Specify `port` explicitly."
        )

    def _compose_host_server_payload(self, *, created: bool, stopped: bool) -> Dict[str, Any]:
        """Build a stable payload describing the active host state."""
        if self._host_server is None:
            return {
                "running": False,
                "created": created,
                "stopped": stopped,
                "rooms": [],
            }

        tokens: Dict[str, Dict[str, str]] = self._host_server.get_room_tokens()
        signaling_url = (
            self._host_public_signaling_url
            or self._host_share_signaling_url
            or self._host_local_signaling_url
        )
        member_count_by_room: Dict[str, int] = {}
        lobby_by_room: Dict[str, bool] = {}
        preset_by_room: Dict[str, str] = {}
        mode_by_room: Dict[str, str] = {}
        agenda_summary_by_room: Dict[str, Dict[str, Any]] = {}
        hands_raised_by_room: Dict[str, int] = {}
        if hasattr(self._host_server, "list_room_members"):
            with contextlib.suppress(Exception):
                member_snapshots = self._host_server.list_room_members(None)
                if isinstance(member_snapshots, list):
                    for room_entry in member_snapshots:
                        if not isinstance(room_entry, dict):
                            continue
                        room_name = str(room_entry.get("name", "")).strip()
                        if not room_name:
                            continue
                        try:
                            member_count_by_room[room_name] = int(room_entry.get("memberCount", 0))
                        except (TypeError, ValueError):
                            member_count_by_room[room_name] = 0
                        lobby_by_room[room_name] = bool(room_entry.get("lobbyEnabled", False))
                        preset_by_room[room_name] = str(room_entry.get("preset", "pairing"))
                        mode_by_room[room_name] = str(room_entry.get("mode", "pair"))
                        agenda_summary_by_room[room_name] = dict(
                            room_entry.get("agendaSummary", {}) or {}
                        )
                        try:
                            hands_raised_by_room[room_name] = int(room_entry.get("handsRaised", 0))
                        except (TypeError, ValueError):
                            hands_raised_by_room[room_name] = 0

        rooms: List[Dict[str, Any]] = []
        for room_name in sorted(tokens.keys()):
            role_map = tokens.get(room_name, {})
            viewer_join_command = ""
            prompter_join_command = ""
            viewer_invite_code = ""
            prompter_invite_code = ""
            if signaling_url:
                if hasattr(self._host_server, "build_room_share_payload"):
                    viewer_share = self._host_server.build_room_share_payload(
                        room_name,
                        "viewer",
                        signaling_url=signaling_url,
                    )
                    if isinstance(viewer_share, dict):
                        viewer_invite_code = str(viewer_share.get("inviteCode", "")).strip()
                        viewer_join_command = (
                            f"poor-cli --remote-invite {viewer_invite_code}"
                            if viewer_invite_code
                            else ""
                        )
                    prompter_share = self._host_server.build_room_share_payload(
                        room_name,
                        "prompter",
                        signaling_url=signaling_url,
                    )
                    if isinstance(prompter_share, dict):
                        prompter_invite_code = str(
                            prompter_share.get("inviteCode", "")
                        ).strip()
                        prompter_join_command = (
                            f"poor-cli --remote-invite {prompter_invite_code}"
                            if prompter_invite_code
                            else ""
                        )

            rooms.append(
                {
                    "name": room_name,
                    "signalingUrl": signaling_url,
                    "viewerJoinCommand": viewer_join_command,
                    "prompterJoinCommand": prompter_join_command,
                    "viewerInviteCode": viewer_invite_code,
                    "prompterInviteCode": prompter_invite_code,
                    "memberCount": member_count_by_room.get(room_name, 0),
                    "lobbyEnabled": lobby_by_room.get(room_name, False),
                    "preset": preset_by_room.get(room_name, "pairing"),
                    "mode": mode_by_room.get(room_name, "pair"),
                    "agendaSummary": agenda_summary_by_room.get(room_name, {}),
                    "handsRaised": hands_raised_by_room.get(room_name, 0),
                }
            )

        return {
            "running": True,
            "created": created,
            "stopped": stopped,
            "bindHost": self._host_bind_host,
            "port": self._host_port,
            "localSignalingUrl": self._host_local_signaling_url,
            "shareSignalingUrl": self._host_share_signaling_url,
            "publicSignalingUrl": self._host_public_signaling_url,
            "signalingUrl": signaling_url,
            "permissionMode": self.permission_mode,
            "ngrokEnabled": self._host_ngrok_enabled,
            "rooms": rooms,
        }

    @staticmethod
    def _find_host_room_payload(payload: Dict[str, Any], room_name: str) -> Optional[Dict[str, Any]]:
        rooms = payload.get("rooms")
        if not isinstance(rooms, list):
            return None
        for room in rooms:
            if isinstance(room, dict) and str(room.get("name", "")).strip() == room_name:
                return room
        return None

    async def _shutdown_host_server_locked(self) -> bool:
        """Stop active host/tunnel and reset state. Call only while holding lock."""
        host = self._host_server
        tunnel = self._host_tunnel
        was_running = host is not None

        self._host_server = None
        self._host_tunnel = None
        self._host_bind_host = ""
        self._host_port = 0
        self._host_local_signaling_url = ""
        self._host_share_signaling_url = ""
        self._host_public_signaling_url = None
        self._host_rooms = []
        self._host_ngrok_enabled = False

        if host is not None:
            await host.stop()
        if tunnel is not None:
            await tunnel.stop()

        return was_running

    async def handle_start_host_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start an in-process multiplayer host and return join details/tokens.

        Params:
            room: Optional room name shortcut
            rooms: Optional list of room names
            bindHost: Optional bind host (default 0.0.0.0)
            port: Optional port; auto-selects from 8765+ when omitted
            ngrok: Optional bool to launch ngrok helper
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()
        _, config = self._ensure_config_loaded()

        default_bind_host = str(config.multiplayer.signaling_bind_host or "0.0.0.0").strip()
        bind_host = str(params.get("bindHost", default_bind_host)).strip() or default_bind_host
        room_hint = str(params.get("room", "")).strip()
        rooms = self._normalize_multiplayer_room_names(params.get("rooms"), room_hint)

        requested_port: Optional[int] = None
        raw_port = params.get("port")
        if raw_port not in (None, ""):
            try:
                requested_port = int(raw_port)
            except (TypeError, ValueError) as e:
                raise InvalidParamsError("port must be an integer") from e

        enable_ngrok = bool(params.get("ngrok", False))

        async with self._get_host_server_lock():
            if self._host_server is not None:
                return self._compose_host_server_payload(created=False, stopped=False)

            port = self._select_multiplayer_port(bind_host, requested_port)

            from ..multiplayer import MultiplayerHost

            host = MultiplayerHost(
                bind_host=bind_host,
                port=port,
                room_names=rooms,
                server_factory=PoorCLIServer,
                message_cls=JsonRpcMessage,
                rpc_error_cls=JsonRpcError,
                default_permission_mode=self.permission_mode,
                invite_ttl_seconds=config.multiplayer.invite_ttl_seconds,
                owner_name=config.multiplayer.owner_name,
                ice_servers=self._build_multiplayer_ice_servers(config),
            )
            try:
                await host.start()
            except Exception:
                with contextlib.suppress(Exception):
                    await host.stop()
                raise

            tunnel: Optional[Any] = None
            public_ws_url: Optional[str] = None
            if enable_ngrok:
                from .multiplayer_runtime import NgrokTunnel

                tunnel = NgrokTunnel(f"{bind_host}:{port}")
                try:
                    public_https = await tunnel.start()
                    if public_https:
                        public_ws_url = public_https + "/rpc"
                except Exception as error:
                    self.logger.warning(f"ngrok helper failed while starting host: {error}")

            local_host = "127.0.0.1" if bind_host in {"0.0.0.0", "::"} else bind_host
            share_host = str(config.multiplayer.share_host or "").strip()
            if not share_host:
                share_host = self._resolve_multiplayer_share_host(bind_host)

            self._host_server = host
            self._host_tunnel = tunnel
            self._host_bind_host = bind_host
            self._host_port = port
            self._host_local_signaling_url = f"http://{local_host}:{port}/rpc"
            self._host_share_signaling_url = f"http://{share_host}:{port}/rpc"
            self._host_public_signaling_url = public_ws_url
            self._host_rooms = rooms
            self._host_ngrok_enabled = enable_ngrok

            payload = self._compose_host_server_payload(created=True, stopped=False)
            await self._emit_collaboration_event(
                "host_started",
                {
                    "rooms": rooms,
                    "bindHost": bind_host,
                    "port": port,
                    "shareSignalingUrl": self._host_share_signaling_url,
                },
            )
            return payload

    async def handle_get_host_server_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return current in-process multiplayer host status."""
        del params
        self._ensure_initialized()
        self._ensure_host_controls_available()
        async with self._get_host_server_lock():
            return self._compose_host_server_payload(created=False, stopped=False)

    async def handle_get_collab_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a concise collaboration summary for shared status surfaces."""
        del params
        self._ensure_initialized()
        return {"collaboration": self._collaboration_status_payload()}

    async def handle_stop_host_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop an active in-process multiplayer host if one is running."""
        del params
        self._ensure_initialized()
        self._ensure_host_controls_available()
        async with self._get_host_server_lock():
            active_rooms = list(self._host_rooms)
            was_running = await self._shutdown_host_server_locked()
            payload = self._compose_host_server_payload(created=False, stopped=was_running)
            if was_running:
                await self._emit_collaboration_event(
                    "host_stopped",
                    {
                        "rooms": active_rooms,
                    },
                )
            return payload

    def _host_room_names_locked(self) -> List[str]:
        """Return active host room names (call while holding host lock)."""
        if self._host_server is None:
            return []

        host_rooms = getattr(self._host_server, "rooms", None)
        if isinstance(host_rooms, dict) and host_rooms:
            return sorted(str(name) for name in host_rooms.keys())
        return sorted(str(name) for name in self._host_rooms)

    def _resolve_host_room_name_locked(self, requested_room: str) -> str:
        """Resolve room name for host-member controls (call while holding host lock)."""
        room_names = self._host_room_names_locked()
        if not room_names:
            raise InvalidParamsError("No multiplayer host is currently running")

        normalized = requested_room.strip()
        if normalized:
            if normalized not in room_names:
                raise InvalidParamsError(
                    f"Unknown room `{normalized}`. Available rooms: {', '.join(room_names)}"
                )
            return normalized

        if len(room_names) == 1:
            return room_names[0]
        raise InvalidParamsError(
            "Multiple rooms are active; specify one with `room`."
        )

    @staticmethod
    def _normalize_member_role(raw_role: Any) -> str:
        """Normalize role values used by host-member controls."""
        role_name = str(raw_role or "").strip().lower()
        if role_name in {"viewer", "read", "read-only"}:
            return "viewer"
        if role_name in {"prompter", "writer", "editor", "admin"}:
            return "prompter"
        raise InvalidParamsError("role must be one of: viewer, prompter")

    def _resolve_host_member_reference_locked(self, room_name: str, reference: str) -> str:
        normalized = str(reference or "").strip()
        if not normalized:
            raise InvalidParamsError("Missing connectionId")
        host = self._host_server
        if host is None:
            raise InvalidParamsError("No multiplayer host is currently running")
        if hasattr(host, "resolve_room_member_reference"):
            resolved = host.resolve_room_member_reference(room_name, normalized)
            if resolved:
                return resolved
        return normalized

    async def handle_list_host_members(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List connected members per room for the active in-process multiplayer host.

        Params:
            room: Optional room name filter.
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                return {"running": False, "rooms": []}

            room_names = self._host_room_names_locked()
            if requested_room and requested_room not in room_names:
                raise InvalidParamsError(
                    f"Unknown room `{requested_room}`. Available rooms: {', '.join(room_names)}"
                )

            host = self._host_server
            if not hasattr(host, "list_room_members"):
                raise RuntimeError("Active host does not support member listing")

            rooms_payload = host.list_room_members(requested_room or None)
            return {"running": True, "rooms": rooms_payload}

    async def handle_remove_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove/disconnect a connected member from a host room.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "remove_room_member"):
                raise RuntimeError("Active host does not support member removal")

            removed = await host.remove_room_member(room_name, connection_id)
            if not removed:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "removed": True,
            }

    async def handle_set_host_member_role(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a connected member role for a host room.

        Params:
            connectionId: Target connection id
            role: viewer | prompter
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        role_name = self._normalize_member_role(params.get("role"))
        requested_room = str(params.get("room", "")).strip()

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "set_room_member_role"):
                raise RuntimeError("Active host does not support role updates")

            try:
                updated = await host.set_room_member_role(room_name, connection_id, role_name)
            except ValueError as error:
                raise InvalidParamsError(str(error)) from error

            if not updated:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "role": role_name,
            }

    async def handle_set_host_lobby(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable/disable host lobby approval mode for a room.

        Params:
            enabled: bool
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        enabled = bool(params.get("enabled", True))
        requested_room = str(params.get("room", "")).strip()

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "set_room_lobby"):
                raise RuntimeError("Active host does not support lobby controls")

            updated = await host.set_room_lobby(room_name, enabled)
            if not updated:
                raise InvalidParamsError(f"Unknown room `{room_name}`")

            return {
                "success": True,
                "room": room_name,
                "lobbyEnabled": enabled,
            }

    async def handle_approve_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Approve a pending room member when lobby mode is enabled.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "approve_room_member"):
                raise RuntimeError("Active host does not support member approvals")

            approved = await host.approve_room_member(room_name, connection_id)
            if not approved:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "approved": True,
            }

    async def handle_deny_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deny/remove a pending room member when lobby mode is enabled.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "deny_room_member"):
                raise RuntimeError("Active host does not support member denial")

            denied = await host.deny_room_member(room_name, connection_id)
            if not denied:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "denied": True,
            }

    async def handle_rotate_host_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rotate room invite token for a role.

        Params:
            role: viewer | prompter
            room: Optional room name (required if multiple rooms)
            expiresInSeconds: Optional token expiry (seconds)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        role_name = self._normalize_member_role(params.get("role"))
        requested_room = str(params.get("room", "")).strip()
        raw_ttl = params.get("expiresInSeconds")
        ttl_seconds: Optional[int]
        if raw_ttl is None:
            ttl_seconds = None
        else:
            try:
                ttl_seconds = int(raw_ttl)
            except (TypeError, ValueError) as e:
                raise InvalidParamsError("expiresInSeconds must be a positive integer") from e
            if ttl_seconds <= 0:
                raise InvalidParamsError("expiresInSeconds must be a positive integer")

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "rotate_room_token"):
                raise RuntimeError("Active host does not support token rotation")

            try:
                token = await host.rotate_room_token(
                    room_name,
                    role_name,
                    expires_in_seconds=ttl_seconds,
                )
            except ValueError as error:
                raise InvalidParamsError(str(error)) from error

            if not token:
                raise InvalidParamsError(f"Unable to rotate token for room `{room_name}`")

            signaling_url = (
                self._host_public_signaling_url
                or self._host_share_signaling_url
                or self._host_local_signaling_url
            )
            join_command = ""
            invite_code = ""
            expires_at = ""
            if ttl_seconds is not None:
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                ).isoformat()
            if signaling_url:
                if hasattr(host, "build_room_share_payload"):
                    share_payload = host.build_room_share_payload(
                        room_name,
                        role_name,
                        signaling_url=signaling_url,
                        expires_in_seconds=ttl_seconds,
                    )
                    if isinstance(share_payload, dict):
                        invite_code = str(share_payload.get("inviteCode", "")).strip()
                        join_command = (
                            f"poor-cli --remote-invite {invite_code}"
                            if invite_code
                            else ""
                        )

            return {
                "success": True,
                "room": room_name,
                "role": role_name,
                "joinCommand": join_command,
                "inviteCode": invite_code,
                "expiresAt": expires_at,
            }

    async def handle_revoke_host_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Revoke an invite token or remove a member by connection id.

        Params:
            value: token or connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        value = str(params.get("value", "")).strip()
        if not value:
            raise InvalidParamsError("Missing value (token or connectionId)")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server

            removed_member = False
            resolved_value = self._resolve_host_member_reference_locked(room_name, value)
            if hasattr(host, "remove_room_member"):
                removed_member = await host.remove_room_member(room_name, resolved_value)
                if removed_member:
                    return {
                        "success": True,
                        "room": room_name,
                        "connectionId": resolved_value,
                        "removed": True,
                        "kind": "member",
                    }

            if not hasattr(host, "revoke_room_token"):
                raise RuntimeError("Active host does not support token revocation")

            revoked_token = await host.revoke_room_token(room_name, value)
            if not revoked_token:
                raise InvalidParamsError(
                    f"`{value}` was not found as a connection id or token in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "token": value,
                "revoked": True,
                "kind": "token",
            }

    async def handle_handoff_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handoff prompter control to a specific member.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "handoff_room_prompter"):
                raise RuntimeError("Active host does not support role handoff")

            handed_off = await host.handoff_room_prompter(room_name, connection_id)
            if not handed_off:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "role": "prompter",
                "handoff": True,
            }

    async def handle_pair_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a pair session with auto-generated 6-char room code."""
        self._ensure_initialized()
        import secrets as _secrets
        short_code = _secrets.token_hex(3)  # 6 hex chars
        lobby = bool(params.get("lobby", False))
        host_result = await self.handle_start_host_server({"room": short_code})
        room_payload = self._find_host_room_payload(host_result, short_code)
        if room_payload is None:
            raise RuntimeError("Host started without returning canonical pair room details")

        invite_code = str(room_payload.get("viewerInviteCode", "")).strip()
        signaling_url = str(
            room_payload.get("signalingUrl")
            or host_result.get("signalingUrl")
            or host_result.get("shareSignalingUrl")
            or host_result.get("publicSignalingUrl")
            or ""
        ).strip()
        if not invite_code or not signaling_url:
            raise RuntimeError("Pair session is missing shareable invite details")
        if lobby:
            try:
                await self.handle_set_host_lobby({"enabled": True, "room": short_code})
            except Exception:
                pass
        return {
            "shortCode": short_code,
            "inviteCode": invite_code,
            "signalingUrl": signaling_url,
            "room": room_payload,
            **host_result,
        }

    async def handle_suggest_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest text in local host mode; review rooms promote suggestions into agenda."""
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        text = str(params.get("text", "")).strip()
        if not text:
            raise InvalidParamsError("text is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                return {"success": True, "local": True}
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            room = host.rooms.get(room_name) if hasattr(host, "rooms") else None
            if room is not None and room.preset == "review" and hasattr(host, "add_room_agenda_item"):
                item = await host.add_room_agenda_item(room_name, text, author="host")
                return {
                    "success": True,
                    "room": room_name,
                    "mode": "agenda",
                    "item": item,
                    "agendaSummary": host.list_room_members(room_name)[0].get("agendaSummary", {}),
                }
        return {"success": True, "local": True}

    async def handle_peer_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Broadcast a freeform chat message to all other members of the current host room."""
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        text = str(params.get("text", "")).strip()
        if not text:
            raise InvalidParamsError("text is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                return {"success": False, "reason": "no_host"}
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "broadcast_host_message"):
                return {"success": False, "reason": "unsupported"}
            delivered = await host.broadcast_host_message(room_name, text, sender="host")
            return {"success": True, "room": room_name, "delivered": delivered}

    async def handle_add_agenda_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        text = str(params.get("text", "")).strip()
        if not text:
            raise InvalidParamsError("text is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "add_room_agenda_item"):
                raise RuntimeError("Active host does not support agenda items")
            item = await host.add_room_agenda_item(
                room_name,
                text,
                author=str(params.get("author", "host")).strip() or "host",
            )
            if item is None:
                raise InvalidParamsError(f"Unknown room `{room_name}`")
            room_payload = host.list_room_members(room_name) if hasattr(host, "list_room_members") else []
            agenda_summary = {}
            if room_payload and isinstance(room_payload, list):
                agenda_summary = dict(room_payload[0].get("agendaSummary", {}) or {})
            payload = {
                "success": True,
                "room": room_name,
                "item": item,
                "agendaSummary": agenda_summary,
            }
            await self._emit_collaboration_event(
                "agenda_added",
                {
                    "room": room_name,
                    "itemId": str(item.get("itemId", "")) if isinstance(item, dict) else "",
                    "text": text,
                },
            )
            return payload

    async def handle_list_agenda(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        include_resolved = bool(params.get("includeResolved", True))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "list_room_agenda"):
                raise RuntimeError("Active host does not support agenda items")
            items = host.list_room_agenda(room_name, include_resolved=include_resolved)
            agenda_summary = {}
            if hasattr(host, "list_room_members"):
                room_payload = host.list_room_members(room_name)
                if room_payload and isinstance(room_payload, list):
                    agenda_summary = dict(room_payload[0].get("agendaSummary", {}) or {})
            return {
                "room": room_name,
                "items": items,
                "agendaSummary": agenda_summary,
            }

    async def handle_resolve_agenda_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        item_id = str(params.get("itemId", params.get("id", ""))).strip()
        if not item_id:
            raise InvalidParamsError("itemId is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "resolve_room_agenda_item"):
                raise RuntimeError("Active host does not support agenda items")
            item = await host.resolve_room_agenda_item(
                room_name,
                item_id,
                resolved_by=str(params.get("resolvedBy", "host")).strip() or "host",
            )
            if item is None:
                raise InvalidParamsError(f"Agenda item `{item_id}` was not found in room `{room_name}`")
            agenda_summary = {}
            if hasattr(host, "list_room_members"):
                room_payload = host.list_room_members(room_name)
                if room_payload and isinstance(room_payload, list):
                    agenda_summary = dict(room_payload[0].get("agendaSummary", {}) or {})
            payload = {
                "success": True,
                "room": room_name,
                "item": item,
                "agendaSummary": agenda_summary,
            }
            await self._emit_collaboration_event(
                "agenda_resolved",
                {
                    "room": room_name,
                    "itemId": item_id,
                },
            )
            return payload

    async def handle_set_hand_raised(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("connectionId is required in local host mode")
        raised = bool(params.get("raised", True))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "set_room_member_hand_raised"):
                raise RuntimeError("Active host does not support hand raise state")
            result = await host.set_room_member_hand_raised(room_name, connection_id, raised)
            if result is None:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )
            return {
                "success": True,
                "room": room_name,
                **result,
            }

    async def handle_next_driver(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "handoff_next_driver"):
                raise RuntimeError("Active host does not support next-driver handoff")
            connection_id = await host.handoff_next_driver(room_name)
            if connection_id is None:
                raise InvalidParamsError("No eligible member found to receive driver role")
            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "handoff": True,
            }

    async def handle_pass_driver(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve display name to connection ID and hand off prompter role."""
        self._ensure_initialized()
        self._ensure_host_controls_available()
        display_name = str(params.get("displayName", "")).strip()
        connection_id = str(params.get("connectionId", "")).strip()
        requested_room = str(params.get("room", "")).strip()
        if not connection_id and not display_name:
            return await self.handle_next_driver({"room": requested_room})
        if not connection_id and display_name:
            connection_id = display_name
        return await self.handle_handoff_host_member({
            "connectionId": connection_id,
            "room": requested_room,
        })

    async def handle_set_host_preset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a room preset for collaboration mode.

        Params:
            preset: pairing | mob | review
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        preset = str(params.get("preset", "")).strip().lower()
        if preset not in {"pairing", "mob", "review"}:
            raise InvalidParamsError("preset must be one of: pairing, mob, review")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "set_room_preset"):
                raise RuntimeError("Active host does not support presets")

            try:
                applied = await host.set_room_preset(room_name, preset)
            except ValueError as error:
                raise InvalidParamsError(str(error)) from error
            if not applied:
                raise InvalidParamsError(f"Unknown room `{room_name}`")

            lobby_enabled = False
            if hasattr(host, "list_room_members"):
                with contextlib.suppress(Exception):
                    room_data = host.list_room_members(room_name)
                    if room_data and isinstance(room_data, list):
                        lobby_enabled = bool(room_data[0].get("lobbyEnabled", False))

            return {
                "success": True,
                "room": room_name,
                "preset": preset,
                "lobbyEnabled": lobby_enabled,
            }

    async def handle_list_host_activity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List recent multiplayer room activity entries.

        Params:
            room: Optional room name (required if multiple rooms)
            limit: Optional max items (default 50)
            eventType: Optional event type filter
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        event_type = str(params.get("eventType", "")).strip()
        raw_limit = params.get("limit", 50)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as e:
            raise InvalidParamsError("limit must be an integer") from e
        limit = max(1, min(limit, 200))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "list_room_activity"):
                raise RuntimeError("Active host does not support activity logs")

            events = host.list_room_activity(room_name, limit, event_type or None)
            return {
                "success": True,
                "room": room_name,
                "events": events,
                "eventType": event_type,
                "count": len(events),
            }

    # choices metadata for dropdown fields
    _CHOICES_MAP: Dict[str, List[str]] = {
        "ui.theme": ["github-light", "quiet-light", "solarized-light", "one-dark", "dracula", "github-dark", "monokai", "nord"],
        "model.provider": ["gemini", "openai", "anthropic", "ollama"],
        "model.routing_mode": ["manual", "quality", "speed", "cheap", "private"],
        "sandbox.default_preset": ["read-only", "review-only", "workspace-write", "full-access"],
        "security.permission_mode": [
            "default",
            "acceptEdits",
            "plan",
            "bypassPermissions",
            "dontAsk",
            "prompt",
            "auto-safe",
            "danger-full-access",
        ],
        "economy.preset": ["frugal", "balanced", "quality"],
    }

    def _flatten_config_values(self, value: Any, prefix: str, output: List[Dict[str, Any]]) -> None:
        """Flatten nested dict/list/scalars into a dot-path list with choices metadata."""
        if isinstance(value, dict):
            for key in sorted(value.keys()):
                next_prefix = f"{prefix}.{key}" if prefix else key
                self._flatten_config_values(value[key], next_prefix, output)
            return

        if isinstance(value, list):
            output.append(
                {
                    "path": prefix,
                    "value": value,
                    "type": "list",
                    "isBoolean": False,
                }
            )
            return

        if isinstance(value, bool):
            value_type = "bool"
        elif isinstance(value, int):
            value_type = "int"
        elif isinstance(value, float):
            value_type = "float"
        elif value is None:
            value_type = "null"
        else:
            value_type = "string"

        entry: Dict[str, Any] = {
            "path": prefix,
            "value": value,
            "type": value_type,
            "isBoolean": isinstance(value, bool),
        }
        if prefix in self._CHOICES_MAP:
            entry["choices"] = self._CHOICES_MAP[prefix]
        output.append(entry)

    def _resolve_config_parent(self, key_path: str) -> Tuple[Any, str]:
        keys = [k for k in key_path.split(".") if k]
        if not keys:
            raise InvalidParamsError("Invalid keyPath")

        current: Any = self.core.config
        for key in keys[:-1]:
            if isinstance(current, dict):
                if key not in current:
                    raise InvalidParamsError(f"Unknown config path: {key_path}")
                current = current[key]
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                raise InvalidParamsError(f"Unknown config path: {key_path}")

        return current, keys[-1]

    def _get_config_value(self, key_path: str) -> Any:
        parent, final_key = self._resolve_config_parent(key_path)
        if isinstance(parent, dict):
            if final_key not in parent:
                raise InvalidParamsError(f"Unknown config key: {key_path}")
            return parent[final_key]
        if hasattr(parent, final_key):
            return getattr(parent, final_key)
        raise InvalidParamsError(f"Unknown config key: {key_path}")

    def _set_config_value(self, key_path: str, value: Any) -> None:
        parent, final_key = self._resolve_config_parent(key_path)
        if isinstance(parent, dict):
            parent[final_key] = value
            return
        if hasattr(parent, final_key):
            setattr(parent, final_key, value)
            return
        raise InvalidParamsError(f"Unknown config key: {key_path}")

    def _coerce_config_value(self, current: Any, proposed: Any, key_path: str) -> Any:
        if isinstance(current, Enum):
            enum_cls = type(current)
            if isinstance(proposed, str):
                try:
                    return enum_cls(proposed)
                except ValueError as e:
                    raise InvalidParamsError(f"Invalid value for {key_path}: {proposed}") from e
            raise InvalidParamsError(f"{key_path} expects a string enum value")

        if isinstance(current, bool):
            if isinstance(proposed, bool):
                return proposed
            if isinstance(proposed, str):
                normalized = proposed.strip().lower()
                if normalized in {"1", "true", "yes", "on", "enabled"}:
                    return True
                if normalized in {"0", "false", "no", "off", "disabled"}:
                    return False
            raise InvalidParamsError(f"{key_path} expects a boolean value")

        if isinstance(current, int) and not isinstance(current, bool):
            if isinstance(proposed, (int, float)):
                return int(proposed)
            if isinstance(proposed, str):
                try:
                    return int(proposed.strip())
                except ValueError as e:
                    raise InvalidParamsError(f"{key_path} expects an integer value") from e
            raise InvalidParamsError(f"{key_path} expects an integer value")

        if isinstance(current, float):
            if isinstance(proposed, (int, float)):
                return float(proposed)
            if isinstance(proposed, str):
                try:
                    return float(proposed.strip())
                except ValueError as e:
                    raise InvalidParamsError(f"{key_path} expects a float value") from e
            raise InvalidParamsError(f"{key_path} expects a float value")

        if isinstance(current, list):
            if isinstance(proposed, list):
                return proposed
            if isinstance(proposed, str):
                candidate = proposed.strip()
                if candidate.startswith("["):
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError as e:
                        raise InvalidParamsError(f"{key_path} expects a JSON list") from e
                    if isinstance(parsed, list):
                        return parsed
                    raise InvalidParamsError(f"{key_path} expects a JSON list")
                if candidate == "":
                    return []
                return [part.strip() for part in candidate.split(",") if part.strip()]
            raise InvalidParamsError(f"{key_path} expects a list value")

        if isinstance(current, dict):
            if isinstance(proposed, dict):
                return proposed
            if isinstance(proposed, str):
                try:
                    parsed = json.loads(proposed.strip())
                except json.JSONDecodeError as e:
                    raise InvalidParamsError(f"{key_path} expects a JSON object") from e
                if isinstance(parsed, dict):
                    return parsed
            raise InvalidParamsError(f"{key_path} expects an object value")

        if current is None:
            return proposed

        return str(proposed)

    def _jsonable_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        return value

    async def handle_cancel_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel an in-flight agentic loop."""
        request_id = str(params.get("requestId", "")).strip()
        self.core.cancel_request(request_id)
        return {"success": True, "requestId": request_id}

    async def handle_get_session_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return session token/cost totals."""
        self._ensure_initialized()
        return self.core.get_session_cost_summary()

    async def handle_get_economy_savings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return accumulated economy savings metrics."""
        self._ensure_initialized()
        return self.core.get_economy_savings()

    async def handle_set_economy_preset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Switch economy preset (frugal | balanced | quality)."""
        self._ensure_initialized()
        preset = str(params.get("preset", "balanced")).strip()
        return self.core.set_economy_preset(preset)

    async def handle_export_cost_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Export full session cost report for accounting/auditing."""
        self._ensure_initialized()
        return self.core.export_cost_report()

    async def handle_get_tokens_visualization(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return text-based context window visualization."""
        self._ensure_initialized()
        return self.core.get_tokens_visualization()

    async def handle_apply_budget_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a named budget template to cost guardrails."""
        self._ensure_initialized()
        template = str(params.get("template", "")).strip()
        return self.core.apply_budget_template(template)

    async def handle_list_budget_templates(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available budget templates."""
        from ..core import PoorCLICore
        return {"templates": PoorCLICore.list_budget_templates()}

    async def handle_get_cost_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return historical session cost data."""
        from ..core import PoorCLICore
        limit = int(params.get("limit", 50))
        entries = PoorCLICore.get_cost_history(limit)
        total_cost = sum(e.get("cost_usd", 0) for e in entries)
        return {"entries": entries, "count": len(entries), "total_cost_usd": round(total_cost, 6)}

    async def handle_get_cache_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return tool cache + response cache + semantic cache stats."""
        self._ensure_initialized()
        return self.core.get_cache_stats()

    async def handle_clear_semantic_cache(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Clear the semantic response cache."""
        self._ensure_initialized()
        return self.core.clear_semantic_cache()

    async def handle_get_context_pressure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return context window utilization metrics."""
        self._ensure_initialized()
        return self.core.get_context_pressure()

    async def handle_get_context_breakdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return token breakdown by category: system, history, tool results."""
        self._ensure_initialized()
        return self.core.get_context_breakdown()

    async def handle_estimate_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate token cost of a message before sending."""
        self._ensure_initialized()
        message = str(params.get("message", ""))
        return self.core.estimate_cost(message)

    async def handle_compare_model_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compare cost between current model and a target model."""
        self._ensure_initialized()
        provider = str(params.get("provider", "")).strip()
        model = str(params.get("model", "")).strip()
        return self.core.compare_model_cost(provider, model)

    async def handle_list_ollama_models(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Discover models available on the local Ollama server."""
        self._ensure_initialized()
        try:
            from ..providers.ollama_provider import OllamaProvider
            base_url = str(params.get("baseUrl", "http://localhost:11434")).strip()
            models = await OllamaProvider.discover_models(base_url)
            return {"models": models, "count": len(models)}
        except Exception as e:
            return {"models": [], "count": 0, "error": str(e)}

    async def handle_gc_checkpoints(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run checkpoint garbage collection."""
        self._ensure_initialized()
        if not self.core.checkpoint_manager:
            return {"deleted": 0, "freed_bytes": 0, "error": "Checkpoints disabled"}
        stats = self.core.checkpoint_manager.gc()
        return stats

    async def handle_save_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save current session transcript for later restore."""
        del params
        self._ensure_initialized()
        if not self.core.provider:
            return {"saved": False, "error": "No active provider"}
        history = self.core.provider.get_history()
        try:
            store = SessionStore(Path.cwd())
            entry = store.save(
                self.session_id,
                {
                    "provider": self.core.config.model.provider if self.core.config else "",
                    "model": self.core.config.model.model_name if self.core.config else "",
                    "history": history,
                    "cost": self.core.get_session_cost_summary(),
                },
            )
            return {
                "saved": True,
                "path": str(entry.get("path", "")),
                "sessionId": str(entry.get("sessionId", self.session_id)),
                "savedAt": str(entry.get("savedAt", "")),
                "messageCount": int(entry.get("messageCount") or 0),
            }
        except Exception as e:
            return {"saved": False, "error": str(e)}

    async def handle_mcp_health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of all registered MCP servers."""
        self._ensure_initialized()
        mcp = getattr(self.core, "_mcp_manager", None)
        if mcp is None:
            return {"servers": {}, "error": "No MCP servers configured"}
        try:
            results = await mcp.health_check_all()
            return {"servers": results}
        except Exception as e:
            return {"servers": {}, "error": str(e)}

    async def handle_restore_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Restore the most recent saved session transcript."""
        self._ensure_initialized()
        try:
            requested_session_id = str(params.get("sessionId", "")).strip()
            store = SessionStore(Path.cwd())
            data = store.load(requested_session_id or None)
            if not data:
                return {"restored": False, "error": "No saved sessions found"}
            messages = data.get("history") or data.get("messages") or []
            if not isinstance(messages, list) or not messages:
                return {"restored": False, "error": "Session has no messages"}
            if self.core.provider:
                self.core.provider.set_history(messages)
            return {
                "restored": True,
                "sessionId": data.get("session_id", ""),
                "message_count": len(messages),
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
                "savedAt": data.get("saved_at", ""),
            }
        except Exception as e:
            return {"restored": False, "error": str(e)}

    # ---- multiplexing session handlers ----

    async def handle_create_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new independent agent session."""
        label = str(params.get("label", "")).strip()
        cwd = params.get("workingDirectory")
        make_default = bool(params.get("makeDefault", False))
        state = self._session_manager.create_session(label=label, cwd=cwd, make_default=make_default)
        return {"session": state.to_dict()}

    async def handle_rename_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Rename a session's label."""
        sid = str(params.get("sessionId", "")).strip()
        label = str(params.get("label", "")).strip()
        if not sid:
            return {"error": "sessionId required"}
        session = self._session_manager.get_session(sid)
        if session is None:
            return {"error": f"session {sid} not found"}
        session.label = label
        return {"sessionId": sid, "label": label}

    async def handle_destroy_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Destroy a session and release resources."""
        sid = str(params.get("sessionId", "")).strip()
        if not sid:
            return {"error": "sessionId required"}
        self._session_manager.destroy_session(sid)
        return {"destroyed": sid}

    async def handle_switch_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Switch the default active session."""
        sid = str(params.get("sessionId", "")).strip()
        if not sid:
            return {"error": "sessionId required"}
        state = self._session_manager.switch_default(sid)
        return {"session": state.to_dict()}

    async def handle_fork_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fork a new session from an existing one, deep-copying conversation history."""
        source = str(params.get("sourceSessionId", "")).strip()
        label = str(params.get("label", "")).strip()
        copy_history = bool(params.get("copyHistory", True))
        if not source:
            return {"error": "sourceSessionId required"}
        state = self._session_manager.fork_session(source, label=label, copy_history=copy_history)
        return {"session": state.to_dict(), "historyForked": copy_history}

    async def handle_list_mux_sessions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all active multiplexed sessions."""
        return {"sessions": self._session_manager.list_sessions()}

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
            params={
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
            },
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
        prompt_id = str(uuid.uuid4())
        notification = JsonRpcMessage(
            method="poor-cli/planReq",
            params={
                "requestId": str(payload.get("requestId", "")),
                "promptId": prompt_id,
                "summary": str(payload.get("summary", "")),
                "originalRequest": str(payload.get("originalRequest", "")),
                "steps": payload.get("steps") or [],
            },
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

    async def handle_chat_streaming(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle chat with structured CoreEvent streaming.

        Sends JSON-RPC notifications for each CoreEvent, then returns a
        final RPC result with the accumulated text.

        Permission requests are handled via the streaming permission callback
        which sends a permissionReq notification and awaits a permissionRes.
        """
        self._ensure_initialized()

        message = params.get("message", "")
        context_files = params.get("contextFiles")
        pinned_context_files = params.get("pinnedContextFiles")
        context_budget_tokens = params.get("contextBudgetTokens")
        max_response_tokens = params.get("maxResponseTokens")
        request_id = self._chat_request_id(params)
        message_text = str(message)
        context_count = self._chat_context_count(context_files) + self._chat_context_count(
            pinned_context_files
        )
        started_at = time.monotonic()

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
                            params={
                                "requestId": request_id,
                                "chunk": event.data.get("chunk", ""),
                            },
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "text_chunk":
                        notification = JsonRpcMessage(
                            method="poor-cli/streamChunk",
                            params={
                                "requestId": request_id,
                                "chunk": event.data.get("chunk", ""),
                                "done": False,
                            },
                        )
                        await self.write_message_stdio(notification)
                        accumulated_text += event.data.get("chunk", "")
                    elif event.type in ("tool_call_start", "tool_result"):
                        event_type = event.type
                        notification = JsonRpcMessage(
                            method="poor-cli/toolEvent",
                            params={
                                "requestId": request_id,
                                "eventType": event_type,
                                "toolName": event.data.get("toolName", ""),
                                "toolArgs": event.data.get("toolArgs", {}),
                                "toolResult": event.data.get("toolResult", ""),
                                "diff": event.data.get("diff", ""),
                                "paths": event.data.get("paths", []),
                                "checkpointId": event.data.get("checkpointId"),
                                "changed": event.data.get("changed"),
                                "message": event.data.get("message", ""),
                                "iterationIndex": event.data.get("iterationIndex", 0),
                                "iterationCap": event.data.get("iterationCap", 25),
                            },
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
                                   "systemTokens", "historyTokens", "toolResultTokens"):
                            if event.data.get(_k):
                                cost_params[_k] = event.data[_k]
                        notification = JsonRpcMessage(method="poor-cli/costUpdate", params=cost_params)
                        await self.write_message_stdio(notification)
                    elif event.type == "context_pressure":
                        notification = JsonRpcMessage(
                            method="poor-cli/contextPressure",
                            params={"requestId": request_id, **event.data},
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "economy_turn_report":
                        notification = JsonRpcMessage(
                            method="poor-cli/economyTurnReport",
                            params={"requestId": request_id, **event.data},
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "progress":
                        notification = JsonRpcMessage(
                            method="poor-cli/progress",
                            params={
                                "requestId": request_id,
                                "phase": event.data.get("phase", ""),
                                "message": event.data.get("message", ""),
                                "iterationIndex": event.data.get("iterationIndex", 0),
                                "iterationCap": event.data.get("iterationCap", 25),
                            },
                        )
                        await self.write_message_stdio(notification)
                    elif event.type == "done":
                        done_notification = JsonRpcMessage(
                            method="poor-cli/streamChunk",
                            params={
                                "requestId": request_id,
                                "chunk": "",
                                "done": True,
                                "reason": event.data.get("reason", "complete"),
                            },
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

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        self.logger.info(
            "chat_complete mode=stream request_id=%s response_chars=%d duration_ms=%d",
            request_id,
            len(accumulated_text),
            elapsed_ms,
        )

        return {"content": accumulated_text, "role": "assistant"}

    def _ensure_initialized(self) -> None:
        """Ensure the server is initialized."""
        if not self.initialized:
            raise Exception("Server not initialized. Call 'initialize' first.")

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

    # =========================================================================
    # Completion handler
    # =========================================================================

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

    # =========================================================================
    # Index handlers
    # =========================================================================

    async def handle_semantic_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        query = str(params.get("query", "")).strip()
        if not query:
            return {"error": "query required"}
        max_results = int(params.get("maxResults", 10))
        file_filter = params.get("fileFilter") or None
        results = indexer.search(query, max_results=max_results, file_filter=file_filter)
        return {"results": [r.to_dict() for r in results]}

    async def handle_index_codebase(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        force = bool(params.get("force", False))
        stats = indexer.index(force=force)
        return {"stats": stats.to_dict()}

    async def handle_get_index_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        return {"stats": indexer.get_stats().to_dict()}

    async def handle_index_embeddings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        from ..embeddings import get_embedding_provider
        indexer = CodebaseIndexer()
        preferred = params.get("provider") or None
        provider = get_embedding_provider(preferred)
        force = bool(params.get("force", False))
        result = await indexer.index_embeddings(provider=provider, force=force)
        return {"result": result}

    async def handle_vector_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        query = str(params.get("query", "")).strip()
        if not query:
            return {"error": "query required"}
        results = await indexer.vector_search(
            query,
            max_results=int(params.get("maxResults", 10)),
            file_filter=params.get("fileFilter") or None,
        )
        return {"results": [r.to_dict() for r in results]}

    async def handle_hybrid_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        query = str(params.get("query", "")).strip()
        if not query:
            return {"error": "query required"}
        results = await indexer.hybrid_search(
            query,
            max_results=int(params.get("maxResults", 10)),
            file_filter=params.get("fileFilter") or None,
        )
        return {"results": [r.to_dict() for r in results]}

    # =========================================================================
    # Agent handlers
    # =========================================================================

    async def handle_create_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        prompt = str(params.get("prompt", "")).strip()
        if not prompt:
            return {"error": "prompt required"}
        agent = mgr.create_agent(
            prompt=prompt,
            sandbox_preset=str(params.get("sandboxPreset", "workspace-write")),
            source=str(params.get("source", "rpc")),
            use_worktree=bool(params.get("useWorktree", True)),
            max_runtime=int(params.get("maxRuntime", 3600)),
            max_cost_usd=float(params.get("maxCostUsd", 5.0)),
            auto_start=bool(params.get("autoStart", False)),
        )
        return {"agent": agent.to_dict()}

    async def handle_list_agents(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        statuses = params.get("statuses") or None
        agents = mgr.list_agents(statuses=statuses)
        return {"agents": [a.to_dict() for a in agents]}

    async def handle_get_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        agent = mgr.get_agent(agent_id)
        if not agent:
            return {"error": f"unknown agent: {agent_id}"}
        return {"agent": agent.to_dict()}

    async def handle_start_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        agent = mgr.start_agent(agent_id)
        return {"agent": agent.to_dict()}

    async def handle_cancel_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        agent = mgr.cancel_agent(agent_id)
        return {"agent": agent.to_dict()}

    async def handle_get_agent_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        tail = int(params.get("tail", 100))
        return {"logs": mgr.get_logs(agent_id, tail=tail)}

    async def handle_get_agent_result(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        return {"result": mgr.get_result(agent_id)}

    # =========================================================================
    # Profile handlers
    # =========================================================================

    async def handle_list_profiles(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..profiles import ProfileManager
        mgr = ProfileManager()
        return {"profiles": [p.to_dict() for p in mgr.list_profiles()]}

    async def handle_apply_profile(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..profiles import ProfileManager
        name = str(params.get("name", "")).strip()
        if not name:
            return {"error": "name required"}
        mgr = ProfileManager()
        session = self._session_manager.get_session(params.get("sessionId"))
        if session.core.config:
            mgr.apply_to_config(session.core.config, name)
            return {"applied": name}
        return {"error": "session not initialized"}

    # =========================================================================
    # Trust handlers
    # =========================================================================

    async def handle_get_trust_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..trust import TrustManager
        mgr = TrustManager()
        return mgr.to_dict()

    async def handle_trust_repo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..trust import TrustManager
        mgr = TrustManager()
        path = params.get("path") or None
        canonical = mgr.trust(path)
        return {"trusted": True, "path": canonical}

    async def handle_untrust_repo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..trust import TrustManager
        mgr = TrustManager()
        path = params.get("path") or None
        removed = mgr.untrust(path)
        return {"untrusted": removed, "path": str(Path.cwd().resolve())}

    # =========================================================================
    # Memory handlers
    # =========================================================================

    async def handle_memory_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        type_filter = params.get("type") or None
        entries = mgr.list_all(type_filter=type_filter)
        return {"memories": [e.to_dict() for e in entries]}

    async def handle_memory_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager, MemoryEntry
        mgr = MemoryManager()
        mgr.load()
        name = str(params.get("name", "")).strip()
        mtype = str(params.get("type", "project")).strip()
        description = str(params.get("description", "")).strip()
        content = str(params.get("content", "")).strip()
        if not name:
            return {"error": "name required"}
        existing = mgr.get(name)
        if existing:
            mgr.update(name, content=content, description=description, type_=mtype)
            return {"status": "updated", "name": name}
        entry = MemoryEntry(name=name, description=description, type=mtype, content=content)
        mgr.save(entry)
        return {"status": "saved", "name": name}

    async def handle_memory_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        query = str(params.get("query", "")).strip()
        type_filter = params.get("type") or None
        max_results = int(params.get("maxResults", 10))
        results = mgr.search(query, type_filter=type_filter, max_results=max_results)
        return {"results": [e.to_dict() for e in results]}

    async def handle_memory_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        name = str(params.get("name", "")).strip()
        if not name:
            return {"error": "name required"}
        deleted = mgr.delete(name)
        return {"deleted": deleted, "name": name}

    # =========================================================================
    # Docker / Watch / Preview / Deploy Handlers
    # =========================================================================

    async def handle_get_docker_sandbox_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..docker_sandbox import docker_sandbox_status
        return docker_sandbox_status()

    async def handle_watch_scan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..ide_watch import scan_directory_for_instructions
        root = params.get("root")
        instructions = scan_directory_for_instructions(root=root)
        return {"instructions": instructions, "count": len(instructions)}

    async def handle_preview_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..preview_server import PreviewServer
        port = params.get("port", 3456)
        if not hasattr(self, "_preview_server"):
            self._preview_server = PreviewServer(port=port)
        return await self._preview_server.start()

    async def handle_preview_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self, "_preview_server"):
            return await self._preview_server.stop()
        return {"stopped": []}

    async def handle_preview_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self, "_preview_server"):
            return self._preview_server.status()
        return {"running": False, "mode": "none"}

    async def handle_deploy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import deploy
        result = await deploy(target=params.get("target"), prod=params.get("prod", False))
        return result.to_dict()

    async def handle_deploy_targets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import detect_deploy_targets
        targets = detect_deploy_targets()
        return {"targets": [t.to_dict() for t in targets]}

    async def handle_deploy_validate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import validate_pre_deploy
        return validate_pre_deploy()

    async def handle_deploy_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..deploy import get_deploy_history
        return {"history": get_deploy_history(limit=params.get("limit", 20))}

    def _get_prompt_library(self):
        from ..prompt_library import PromptLibrary
        return PromptLibrary(Path.home() / ".poor-cli")

    async def handle_prompt_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        lib.save(params["name"], params["content"])
        return {"success": True}

    async def handle_prompt_load(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        return {"content": lib.load(params["name"])}

    async def handle_prompt_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        return {"prompts": lib.list_all()}

    async def handle_prompt_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lib = self._get_prompt_library()
        lib.delete(params["name"])
        return {"success": True}

    async def handle_latent_compatibility(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from ..latent_communication import is_latent_compatible
            return is_latent_compatible()
        except Exception as e:
            return {"feasible": False, "reason": str(e)}

    async def handle_get_command_manifest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from ..command_manifest import load_command_manifest, render_commands_markdown
            manifest = load_command_manifest()
            return {"commands": [{"name": c.name, "summary": c.summary, "usage": c.usage, "aliases": list(c.aliases)} for c in manifest.commands], "markdown": render_commands_markdown()}
        except Exception as e:
            return {"commands": [], "markdown": "", "error": str(e)}

    async def handle_get_recovery_suggestions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..error_recovery import ErrorRecoveryManager
        error_text = params.get("error", "")
        mgr = ErrorRecoveryManager()
        suggestions = mgr.get_suggestions(Exception(error_text))
        return {"suggestions": [{"title": s.title, "description": s.description, "commands": s.commands, "priority": s.priority} for s in suggestions]}

    # =========================================================================
    # Message Dispatch
    # =========================================================================

    async def dispatch(self, message: JsonRpcMessage) -> JsonRpcMessage:
        """
        Dispatch a JSON-RPC message to the appropriate handler.

        Args:
            message: The incoming message

        Returns:
            Response message
        """
        with log_context(request_id=message.id):
            if not message.method:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INVALID_REQUEST,
                        "Missing method",
                        {"error_code": "INVALID_REQUEST"},
                    ),
                )

            handler = self.handlers.get(message.method)
            if not handler:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.METHOD_NOT_FOUND,
                        f"Unknown method: {message.method}",
                        {"error_code": "METHOD_NOT_FOUND"},
                    ),
                )

            try:
                result = await handler(message.params or {})
                return JsonRpcMessage(id=message.id, result=result)
            except InvalidParamsError as e:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INVALID_PARAMS,
                        _sanitize_exception_message(e),
                        {"error_code": "INVALID_PARAMS"},
                    ),
                )
            except PermissionDeniedError as e:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INTERNAL_ERROR,
                        _sanitize_exception_message(e),
                        {
                            "error_code": e.error_code,
                            "tool": e.tool_name,
                            "permission_mode": e.permission_mode,
                        },
                    ),
                )
            except Exception as e:
                error_code = get_error_code(e)
                self.logger.exception(f"Handler error for {message.method}")
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INTERNAL_ERROR,
                        _sanitize_exception_message(e),
                        {"error_code": error_code},
                    ),
                )

    # =========================================================================
    # STDIO Transport
    # =========================================================================

    async def read_message_stdio(self) -> Optional[JsonRpcMessage]:
        """Read a JSON-RPC message from stdin (delegates to StdioTransport)."""
        return await self._transport.read_message()

    async def write_message_stdio(self, message: JsonRpcMessage) -> None:
        """Write a JSON-RPC message to stdout (delegates to StdioTransport)."""
        await self._transport.write_message(message)

    async def _dispatch_and_respond(self, message: JsonRpcMessage) -> None:
        """Dispatch a request and write the response. Used for background tasks."""
        try:
            response = await self.dispatch(message)
            if message.id is not None:
                await self.write_message_stdio(response)
        except Exception as e:
            self.logger.exception(f"Error in background dispatch for {message.method}")
            if message.id is None:
                return
            error_response = JsonRpcMessage(
                id=message.id,
                error=JsonRpcError.make_error(
                    JsonRpcError.INTERNAL_ERROR,
                    _sanitize_exception_message(e),
                    {"error_code": get_error_code(e)},
                ),
            )
            with contextlib.suppress(Exception):
                await self.write_message_stdio(error_response)

    async def run_stdio(self) -> None:
        """
        Run the server using stdio transport.

        Reads JSON-RPC messages from stdin and writes responses to stdout.
        Streaming requests run as background tasks so the main loop can
        process incoming notifications (e.g. permissionRes) concurrently.
        """
        self.logger.info("Starting stdio server")
        self._running = True

        while self._running:
            try:
                message = await self.read_message_stdio()
                transport_error = getattr(self._transport, "last_error", None)

                if message is None:
                    if transport_error is not None:
                        self.logger.warning(
                            "Skipping malformed stdio message: %s",
                            transport_error,
                        )
                        continue
                    self.logger.info("EOF received, shutting down")
                    break

                # Handle notifications (no id) — e.g. permissionRes
                if message.id is None:
                    await self._handle_notification(message)
                    continue

                # Streaming requests run concurrently so permission flow works
                if message.method == "poor-cli/chatStreaming":
                    self._track_background_task(
                        asyncio.create_task(self._dispatch_and_respond(message))
                    )
                else:
                    response = await self.dispatch(message)
                    if message.id is not None:
                        await self.write_message_stdio(response)

            except Exception as e:
                self.logger.exception("Error in main loop")

        self._resolve_pending_review_requests()
        await self._shutdown_background_tasks()
        async with self._get_host_server_lock():
            with contextlib.suppress(Exception):
                await self._shutdown_host_server_locked()
        async with self._get_service_lock():
            with contextlib.suppress(Exception):
                await self._shutdown_managed_services_locked()
        with contextlib.suppress(Exception):
            await self.core.shutdown()
        self.logger.info("Stdio server stopped")


# =============================================================================
# Streaming Server Extension
# =============================================================================


class StreamingJsonRpcServer(PoorCLIServer):
    """
    Extended server with streaming support.

    Kept for backward compatibility. New streaming uses
    PoorCLIServer.handle_chat_streaming() with CoreEvent notifications.
    """

    async def handle_chat_streaming_legacy(self, params: Dict[str, Any], request_id: int) -> None:
        """Legacy text-only streaming handler."""
        self._ensure_initialized()

        message = params.get("message", "")
        context_files = params.get("contextFiles")
        pinned_context_files = params.get("pinnedContextFiles")
        context_budget_tokens = params.get("contextBudgetTokens")

        async for chunk in self.core.send_message(
            message=message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        ):
            notification = JsonRpcMessage(
                method="poor-cli/streamChunk",
                params={"requestId": request_id, "chunk": chunk, "done": False},
            )
            await self.write_message_stdio(notification)

        final = JsonRpcMessage(
            method="poor-cli/streamChunk",
            params={"requestId": request_id, "chunk": "", "done": True},
        )
        await self.write_message_stdio(final)


# =============================================================================
# Main Entry Point
# =============================================================================
