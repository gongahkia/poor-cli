"""
PoorCLI JSON-RPC Server

This module provides a JSON-RPC 2.0 server for editor integrations.
It supports stdio transport for Neovim integration.
"""

import argparse
import ast
import asyncio
import contextlib
import copy
import difflib
import json
import logging
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import PermissionMode
from .core import PoorCLICore, CoreEvent
from .exceptions import (
    ConfigurationError,
    PoorCLIError,
    PermissionDeniedError,
    get_error_code,
    log_context,
    set_log_context,
    setup_logger,
)

logger = setup_logger(__name__)
_MAX_ERROR_MESSAGE_LEN = 360


def _collapse_whitespace(text: str) -> str:
    """Normalize all whitespace runs to a single space."""
    return " ".join(text.split())


def _try_parse_mapping(text: str) -> Optional[Dict[str, Any]]:
    """Try parsing a string into a dictionary via JSON or Python literal syntax."""
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_reason(details: Any) -> Optional[str]:
    """Extract a provider reason code from nested details blocks, if present."""
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                reason = item.get("reason")
                if isinstance(reason, str) and reason.strip():
                    return _collapse_whitespace(reason)
                nested = _extract_reason(item.get("details"))
                if nested:
                    return nested
    return None


def _extract_structured_error_fields(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract normalized message, reason, and status fields from structured API payloads."""
    message: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None

    error_obj = payload.get("error")
    if isinstance(error_obj, dict):
        value = error_obj.get("message")
        if isinstance(value, str) and value.strip():
            message = _collapse_whitespace(value)

        value = error_obj.get("status")
        if isinstance(value, str) and value.strip():
            status = _collapse_whitespace(value)

        reason = _extract_reason(error_obj.get("details"))

    payload_message = payload.get("message")
    if isinstance(payload_message, str) and payload_message.strip():
        nested_payload = _try_parse_mapping(payload_message.strip())
        if nested_payload is not None:
            nested_message, nested_reason, nested_status = _extract_structured_error_fields(
                nested_payload
            )
            message = message or nested_message
            reason = reason or nested_reason
            status = status or nested_status
        elif message is None:
            message = _collapse_whitespace(payload_message)

    payload_status = payload.get("status")
    if status is None and isinstance(payload_status, str) and payload_status.strip():
        status = _collapse_whitespace(payload_status)

    return message, reason, status


def _extract_structured_payload(raw: str) -> Optional[Dict[str, Any]]:
    """Find and parse an embedded dict/JSON payload inside a verbose exception string."""
    index = raw.find("{")
    while index != -1:
        candidate = raw[index:].strip()
        parsed = _try_parse_mapping(candidate)
        if parsed is not None:
            return parsed
        index = raw.find("{", index + 1)
    return None


def _trim_embedded_payload(compact: str) -> str:
    """Drop common serialized error blob suffixes from a compacted error string."""
    for marker in (" {'message':", ' {"message":', " {'error':", ' {"error":'):
        marker_index = compact.find(marker)
        if marker_index != -1:
            return compact[:marker_index].strip()
    return compact


def _sanitize_exception_message(error: Exception) -> str:
    """Build a concise, user-facing exception message for JSON-RPC responses."""
    raw = str(error).strip()
    if not raw:
        return error.__class__.__name__

    compact = _collapse_whitespace(raw.replace("\\n", " ").replace("\\t", " "))
    message = _trim_embedded_payload(compact)

    payload = _extract_structured_payload(raw)
    if payload is not None:
        extracted_message, extracted_reason, extracted_status = _extract_structured_error_fields(
            payload
        )

        detail_parts: List[str] = []
        if extracted_message:
            detail_parts.append(extracted_message)
        if extracted_reason:
            detail_parts.append(f"({extracted_reason})")
        elif extracted_status:
            detail_parts.append(f"({extracted_status})")

        detail = " ".join(detail_parts).strip()
        if detail and detail.lower() not in message.lower():
            message = f"{message}: {detail}" if message else detail

    if len(message) > _MAX_ERROR_MESSAGE_LEN:
        message = f"{message[:_MAX_ERROR_MESSAGE_LEN - 3].rstrip()}..."
    return message


# =============================================================================
# JSON-RPC Message Types
# =============================================================================


@dataclass
class JsonRpcMessage:
    """JSON-RPC 2.0 message."""

    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JsonRpcMessage":
        """Create from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )

    @classmethod
    def from_json(cls, text: str) -> "JsonRpcMessage":
        """Parse from JSON string."""
        data = json.loads(text)
        return cls.from_dict(data)


class JsonRpcError:
    """JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    @classmethod
    def make_error(cls, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """Create an error object."""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return error


class InvalidParamsError(Exception):
    """Raised when JSON-RPC method params fail validation."""


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
        self.core = PoorCLICore()
        self.core.permission_callback = self._server_permission_callback
        self.handlers: Dict[str, Callable] = {}
        self.initialized = False
        self.permission_mode: str = "prompt"
        self.logger = setup_logger("poor_cli.server")
        self.session_id = f"server-{uuid.uuid4().hex[:8]}"
        set_log_context(session_id=self.session_id)
        self._running = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._client_streaming = False  # set True if client opts in during initialize
        self._pending_permissions: Dict[str, asyncio.Future] = {}  # promptId → Future[bool]

        self._register_handlers()

    async def _server_permission_callback(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """Server-side permission callback for core tool execution."""
        del tool_args  # Unused for default mode-based enforcement.

        try:
            permission_mode = PermissionMode(self.permission_mode)
        except ValueError:
            permission_mode = PermissionMode.PROMPT

        if permission_mode == PermissionMode.DANGER_FULL_ACCESS:
            return True

        if permission_mode == PermissionMode.PROMPT and tool_name in {
            "write_file",
            "edit_file",
            "delete_file",
            "bash",
            "apply_patch_unified",
            "json_yaml_edit",
            "format_and_lint",
        }:
            return False

        return True

    def _register_handlers(self) -> None:
        """Register JSON-RPC method handlers."""
        self.handlers = {
            "initialize": self.handle_initialize,
            "shutdown": self.handle_shutdown,
            "chat": self.handle_chat,
            "listProviders": self.handle_list_providers,
            "switchProvider": self.handle_switch_provider,
            "getConfig": self.handle_get_config,
            "setConfig": self.handle_set_config,
            "poor-cli/chat": self.handle_chat,
            "poor-cli/inlineComplete": self.handle_inline_complete,
            "poor-cli/applyEdit": self.handle_apply_edit,
            "poor-cli/readFile": self.handle_read_file,
            "poor-cli/executeCommand": self.handle_execute_command,
            "poor-cli/getTools": self.handle_get_tools,
            "poor-cli/switchProvider": self.handle_switch_provider,
            "poor-cli/getProviderInfo": self.handle_get_provider_info,
            "poor-cli/clearHistory": self.handle_clear_history,
            "poor-cli/listConfigOptions": self.handle_list_config_options,
            "poor-cli/setConfig": self.handle_set_config,
            "poor-cli/toggleConfig": self.handle_toggle_config,
            "poor-cli/listSessions": self.handle_list_sessions,
            "poor-cli/listHistory": self.handle_list_history,
            "poor-cli/searchHistory": self.handle_search_history,
            "poor-cli/listCheckpoints": self.handle_list_checkpoints,
            "poor-cli/createCheckpoint": self.handle_create_checkpoint,
            "poor-cli/restoreCheckpoint": self.handle_restore_checkpoint,
            "poor-cli/compareFiles": self.handle_compare_files,
            "poor-cli/exportConversation": self.handle_export_conversation,
            "poor-cli/cancelRequest": self.handle_cancel_request,
            "poor-cli/chatStreaming": self.handle_chat_streaming,
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
                    self.permission_mode = PermissionMode(str(requested_permission_mode)).value
                except ValueError as e:
                    raise InvalidParamsError(
                        "Invalid permissionMode. "
                        "Expected one of: prompt, auto-safe, danger-full-access."
                    ) from e

            # Client declares streaming support
            if params.get("streaming"):
                self._client_streaming = True

            await self.core.initialize(
                provider_name=params.get("provider"),
                model_name=params.get("model"),
                api_key=params.get("apiKey"),
            )
            self.initialized = True
            provider_info = self.core.get_provider_info()
            set_log_context(provider=provider_info.get("name"))

            return {
                "capabilities": {
                    "completionProvider": True,
                    "inlineCompletionProvider": True,
                    "chatProvider": True,
                    "chatStreamingProvider": True,
                    "fileOperations": True,
                    "permissionMode": self.permission_mode,
                    "providerInfo": provider_info,
                }
            }
        except ConfigurationError as e:
            raise ConfigurationError(f"Initialization failed: {e}") from e

    async def handle_shutdown(self, params: Dict[str, Any]) -> None:
        """Shutdown the server."""
        self.logger.info("Shutdown requested")
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

        response_text = await self.core.send_message_sync(
            message=message, context_files=context_files
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

        # Collect all chunks
        chunks = []
        async for chunk in self.core.inline_complete(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language,
        ):
            chunks.append(chunk)

        return {"completion": "".join(chunks), "isPartial": False}

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

        result = await self.core.apply_edit(
            file_path=file_path, old_text=old_text, new_text=new_text
        )

        success = not result.startswith("Error")

        return {"success": success, "message": result}

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

        Returns:
            output: Command output
            exitCode: Exit code (always 0 for now)
        """
        self._ensure_initialized()

        command = params.get("command", "")
        tool_args = {"command": command}

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

        return {"tools": self.core.get_available_tools()}

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

        await self.core.switch_provider(provider, model)

        return {"success": True, "provider": self.core.get_provider_info()}

    async def handle_get_provider_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current provider info.

        Returns:
            Provider info dict
        """
        self._ensure_initialized()
        return self.core.get_provider_info()

    async def handle_clear_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clear conversation history.

        Returns:
            success: Always true
        """
        self._ensure_initialized()
        await self.core.clear_history()
        return {"success": True}

    async def handle_list_providers(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List all available providers with their models.

        Returns:
            Dictionary of provider name -> {available, models, ...}
        """
        from .providers.provider_factory import ProviderFactory

        result: Dict[str, Any] = {}
        for name, cls in ProviderFactory.list_providers().items():
            info = ProviderFactory.get_provider_info(name) or {}
            # Provide default model suggestions per provider
            model_suggestions: Dict[str, list] = {
                "gemini": ["gemini-2.0-flash-exp", "gemini-1.5-pro"],
                "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
                "anthropic": ["claude-sonnet-4-20250514", "claude-3-haiku-20240307"],
                "claude": ["claude-sonnet-4-20250514", "claude-3-haiku-20240307"],
                "ollama": ["llama3", "codellama", "mistral", "phi3"],
            }
            result[name] = {
                "available": info.get("available", True),
                "models": model_suggestions.get(name, []),
            }
        return result

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
            "configFile": config_path,
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

            if key_path == "security.permission_mode":
                mode = self.core.config.security.permission_mode
                if isinstance(mode, PermissionMode):
                    self.permission_mode = mode.value
                else:
                    self.permission_mode = str(mode)

            self.core._config_manager.config = self.core.config
            self.core._config_manager.validate()
            self.core._config_manager.save()
        except Exception:
            self._set_config_value(key_path, old_value)
            if key_path == "security.permission_mode":
                mode = self.core.config.security.permission_mode
                self.permission_mode = mode.value if isinstance(mode, PermissionMode) else str(mode)
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

    def _get_repo_config(self):
        from .repo_config import get_repo_config

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

    def _flatten_config_values(self, value: Any, prefix: str, output: List[Dict[str, Any]]) -> None:
        """Flatten nested dict/list/scalars into a dot-path list."""
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

        output.append(
            {
                "path": prefix,
                "value": value,
                "type": value_type,
                "isBoolean": isinstance(value, bool),
            }
        )

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
        self.core.cancel_request()
        return {"success": True}

    async def _streaming_permission_callback(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> bool:
        """Interactive permission callback used during streaming chat.
        Sends permissionReq notification and waits for permissionRes."""
        prompt_id = str(uuid.uuid4())
        notification = JsonRpcMessage(
            method="poor-cli/permissionReq",
            params={
                "toolName": tool_name,
                "toolArgs": tool_args,
                "promptId": prompt_id,
            },
        )
        await self.write_message_stdio(notification)
        loop = asyncio.get_event_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending_permissions[prompt_id] = future
        try:
            return await asyncio.wait_for(future, timeout=300)  # 5 min timeout
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_permissions.pop(prompt_id, None)

    async def _handle_notification(self, message: JsonRpcMessage) -> None:
        """Handle incoming JSON-RPC notifications (no id)."""
        if message.method == "poor-cli/permissionRes":
            params = message.params or {}
            prompt_id = params.get("promptId", "")
            allowed = params.get("allowed", False)
            future = self._pending_permissions.get(prompt_id)
            if future and not future.done():
                future.set_result(allowed)
            elif not prompt_id and self._pending_permissions:
                # fallback: resolve the first pending permission
                for _pid, fut in list(self._pending_permissions.items()):
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
        request_id = params.get("requestId", "")

        # Install interactive permission callback for this streaming session
        prev_callback = self.core.permission_callback
        self.core.permission_callback = self._streaming_permission_callback

        try:
            accumulated_text = ""
            async for event in self.core.send_message_events(
                message=message,
                context_files=context_files,
                request_id=request_id,
            ):
                if event.type == "text_chunk":
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
                            "iterationIndex": event.data.get("iterationIndex", 0),
                            "iterationCap": event.data.get("iterationCap", 25),
                        },
                    )
                    await self.write_message_stdio(notification)
                elif event.type == "permission_request":
                    pass  # handled by _streaming_permission_callback already
                elif event.type == "cost_update":
                    notification = JsonRpcMessage(
                        method="poor-cli/costUpdate",
                        params={
                            "requestId": request_id,
                            "inputTokens": event.data.get("inputTokens", 0),
                            "outputTokens": event.data.get("outputTokens", 0),
                            "estimatedCost": event.data.get("estimatedCost", 0.0),
                        },
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
        finally:
            self.core.permission_callback = prev_callback

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

        permitted = await callback(tool_name, tool_args)
        if not permitted:
            raise PermissionDeniedError(tool_name=tool_name, permission_mode=self.permission_mode)

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
        """
        Read a JSON-RPC message from stdin.

        Uses the LSP-style Content-Length header protocol.

        Returns:
            Parsed message or None on EOF.
        """
        try:
            loop = asyncio.get_event_loop()
            stdin_reader = getattr(sys.stdin, "buffer", sys.stdin)

            # Read headers byte-by-byte so fragmented header chunks are handled correctly.
            header_buffer = b""
            header_delimiter = None
            while header_delimiter is None:
                chunk = await loop.run_in_executor(None, lambda: stdin_reader.read(1))
                if not chunk:
                    return None  # EOF
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                header_buffer += chunk

                if b"\r\n\r\n" in header_buffer:
                    header_delimiter = b"\r\n\r\n"
                elif b"\n\n" in header_buffer:
                    header_delimiter = b"\n\n"

            header_text, body_prefix = header_buffer.split(header_delimiter, 1)
            header_text_decoded = header_text.decode("ascii", errors="replace")

            content_length = 0
            for raw_line in header_text_decoded.splitlines():
                line = raw_line.strip()
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
                    break

            if content_length <= 0:
                return None

            # Read body until exact content-length is satisfied.
            body = body_prefix
            while len(body) < content_length:
                remaining = content_length - len(body)
                chunk = await loop.run_in_executor(
                    None, lambda size=remaining: stdin_reader.read(size)
                )
                if not chunk:
                    return None
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                body += chunk

            body = body[:content_length]
            return JsonRpcMessage.from_json(body.decode("utf-8"))

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Read error: {e}")
            return None

    async def write_message_stdio(self, message: JsonRpcMessage) -> None:
        """
        Write a JSON-RPC message to stdout.

        Uses the LSP-style Content-Length header protocol.

        Args:
            message: The message to write.
        """
        try:
            body = message.to_json().encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")

            stdout_writer = getattr(sys.stdout, "buffer", None)
            if stdout_writer is not None:
                stdout_writer.write(header)
                stdout_writer.write(body)
                stdout_writer.flush()
            else:
                # Fallback for tests or environments without binary stdio handles.
                sys.stdout.write((header + body).decode("utf-8"))
                sys.stdout.flush()

        except Exception as e:
            self.logger.error(f"Write error: {e}")

    async def _dispatch_and_respond(self, message: JsonRpcMessage) -> None:
        """Dispatch a request and write the response. Used for background tasks."""
        try:
            response = await self.dispatch(message)
            if message.id is not None:
                await self.write_message_stdio(response)
        except Exception as e:
            self.logger.exception(f"Error in background dispatch for {message.method}")

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

                if message is None:
                    self.logger.info("EOF received, shutting down")
                    break

                # Handle notifications (no id) — e.g. permissionRes
                if message.id is None:
                    await self._handle_notification(message)
                    continue

                # Streaming requests run concurrently so permission flow works
                if message.method == "poor-cli/chatStreaming":
                    asyncio.ensure_future(self._dispatch_and_respond(message))
                else:
                    response = await self.dispatch(message)
                    if message.id is not None:
                        await self.write_message_stdio(response)

            except Exception as e:
                self.logger.exception("Error in main loop")

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

        async for chunk in self.core.send_message(message=message, context_files=context_files):
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


class NgrokTunnel:
    """Helper for launching ngrok and extracting a public URL."""

    def __init__(self, target_addr: str):
        self.target_addr = target_addr
        self.process: Optional[asyncio.subprocess.Process] = None
        self.public_url: Optional[str] = None

    async def start(self, timeout_seconds: float = 12.0) -> Optional[str]:
        """Start ngrok and wait for a public HTTPS URL."""
        if shutil.which("ngrok") is None:
            logger.warning("ngrok not found in PATH; tunnel disabled")
            return None

        self.process = await asyncio.create_subprocess_exec(
            "ngrok",
            "http",
            self.target_addr,
            "--log=stdout",
            "--log-format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if self.process.stdout is None:
            logger.warning("ngrok stdout unavailable; tunnel URL could not be determined")
            return None

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            remaining = max(deadline - asyncio.get_event_loop().time(), 0.05)
            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            if not line:
                break

            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue

            url = None
            try:
                payload = json.loads(text)
                if isinstance(payload, dict):
                    url = payload.get("url")
                    if not url:
                        nested = payload.get("obj")
                        if isinstance(nested, dict):
                            url = nested.get("url")
            except json.JSONDecodeError:
                pass

            if isinstance(url, str) and url.startswith("https://"):
                self.public_url = url
                logger.info(f"ngrok tunnel ready: {url}")
                return url

        logger.warning("Timed out waiting for ngrok public URL")
        return None

    async def stop(self) -> None:
        """Terminate ngrok process if running."""
        if self.process is None:
            return

        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                with contextlib.suppress(Exception):
                    await self.process.wait()

        self.process = None


def _print_multiplayer_join_hints(
    ws_url: str,
    tokens: Dict[str, Dict[str, str]],
) -> None:
    """Print host-local room/token join instructions."""
    print("\npoor-cli multiplayer host is ready.", file=sys.stderr)
    print(f"WebSocket endpoint: {ws_url}", file=sys.stderr)
    print("", file=sys.stderr)
    for room_name in sorted(tokens.keys()):
        viewer_token = tokens[room_name].get("viewer", "")
        prompter_token = tokens[room_name].get("prompter", "")
        print(f"Room: {room_name}", file=sys.stderr)
        print(f"  viewer token:   {viewer_token}", file=sys.stderr)
        print(f"  prompter token: {prompter_token}", file=sys.stderr)
        print(
            f"  TUI join: poor-cli --remote-url {ws_url} --remote-room {room_name} --remote-token {prompter_token}",
            file=sys.stderr,
        )
        print(
            f"  Neovim: multiplayer={{ enabled=true, url='{ws_url}', room='{room_name}', token='{prompter_token}' }}",
            file=sys.stderr,
        )
        print("", file=sys.stderr)


async def _run_stdio_bridge(
    url: str,
    room: str,
    token: str,
) -> None:
    """Run a stdio <-> WebSocket JSON-RPC bridge."""
    try:
        import aiohttp
    except ImportError as e:
        raise RuntimeError(
            "Bridge mode requires aiohttp. Install dependencies with: pip install -r requirements.txt"
        ) from e

    io_server = PoorCLIServer()
    logger.info(f"Starting stdio bridge to {url} (room={room})")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, heartbeat=30) as ws:
            stdin_eof = asyncio.Event()

            async def _ws_to_stdio() -> None:
                async for message in ws:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        if message.type in {
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                        }:
                            break
                        continue

                    try:
                        payload = json.loads(message.data)
                    except json.JSONDecodeError:
                        logger.warning("Bridge received non-JSON websocket payload")
                        continue

                    if not isinstance(payload, dict):
                        logger.warning("Bridge received non-object websocket payload")
                        continue

                    rpc_msg = JsonRpcMessage.from_dict(payload)
                    await io_server.write_message_stdio(rpc_msg)

            async def _stdio_to_ws() -> None:
                while True:
                    rpc_msg = await io_server.read_message_stdio()
                    if rpc_msg is None:
                        stdin_eof.set()
                        break

                    if rpc_msg.method == "initialize":
                        params = dict(rpc_msg.params or {})
                        params.setdefault("room", room)
                        params.setdefault("inviteToken", token)
                        params.setdefault("clientName", "stdio-bridge")
                        rpc_msg.params = params

                    await ws.send_str(rpc_msg.to_json())

            ws_reader = asyncio.create_task(_ws_to_stdio(), name="poor-cli-bridge-ws-reader")
            stdio_reader = asyncio.create_task(_stdio_to_ws(), name="poor-cli-bridge-stdio-reader")

            try:
                await stdio_reader

                # Drain in-flight websocket responses/notifications briefly before shutdown.
                if stdin_eof.is_set():
                    drain_deadline = asyncio.get_event_loop().time() + 0.25
                    while not ws_reader.done() and asyncio.get_event_loop().time() < drain_deadline:
                        await asyncio.sleep(0.01)
                    await ws.close()

                await ws_reader
            finally:
                for task in (stdio_reader, ws_reader):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task


async def _run_multiplayer_host(
    bind_host: str,
    port: int,
    rooms: List[str],
    permission_mode: str,
    enable_ngrok: bool,
) -> None:
    """Run multiplayer WebSocket host mode."""
    from .multiplayer import MultiplayerHost

    host = MultiplayerHost(
        bind_host=bind_host,
        port=port,
        room_names=rooms,
        server_factory=PoorCLIServer,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
        default_permission_mode=permission_mode,
    )

    tunnel: Optional[NgrokTunnel] = None
    await host.start()
    base_ws_url = f"ws://{bind_host}:{port}/rpc"
    _print_multiplayer_join_hints(base_ws_url, host.get_room_tokens())

    if enable_ngrok:
        tunnel = NgrokTunnel(f"{bind_host}:{port}")
        public_https = await tunnel.start()
        if public_https:
            public_ws = public_https.replace("https://", "wss://", 1) + "/rpc"
            _print_multiplayer_join_hints(public_ws, host.get_room_tokens())
        else:
            logger.warning("ngrok helper failed; host is still running on local interface")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await host.stop()
        if tunnel is not None:
            await tunnel.stop()


def main() -> None:
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description="PoorCLI JSON-RPC Server for editor integration")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (for Neovim)")
    parser.add_argument("--host", action="store_true", help="Run multiplayer WebSocket host mode")
    parser.add_argument("--bind", default="127.0.0.1", help="Host bind address for --host mode")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Host port for --host mode (default: 8765)",
    )
    parser.add_argument(
        "--room",
        action="append",
        default=[],
        help="Multiplayer room name (repeatable in --host mode)",
    )
    parser.add_argument(
        "--permission-mode",
        default="prompt",
        choices=[mode.value for mode in PermissionMode],
        help="Default permission mode for multiplayer room engines",
    )
    parser.add_argument("--ngrok", action="store_true", help="Launch ngrok helper in --host mode")
    parser.add_argument("--bridge", action="store_true", help="Run stdio <-> WebSocket bridge mode")
    parser.add_argument("--url", help="WebSocket URL for --bridge mode (ws:// or wss://)")
    parser.add_argument("--token", help="Invite token for --bridge mode")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # Log to stderr to keep stdout clean for JSON-RPC
    )

    if args.host and args.bridge:
        raise SystemExit("Choose exactly one mode: either --host or --bridge (not both).")

    if args.bridge:
        if not args.url:
            raise SystemExit("--bridge requires --url")
        bridge_room = args.room[0] if args.room else ""
        if not bridge_room:
            raise SystemExit("--bridge requires --room <name>")
        if not args.token:
            raise SystemExit("--bridge requires --token")
        asyncio.run(_run_stdio_bridge(args.url, bridge_room, args.token))
        return

    if args.host:
        asyncio.run(
            _run_multiplayer_host(
                bind_host=args.bind,
                port=args.port,
                rooms=args.room,
                permission_mode=args.permission_mode,
                enable_ngrok=args.ngrok,
            )
        )
        return

    server = PoorCLIServer()
    # Default mode remains stdio for backward compatibility.
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
