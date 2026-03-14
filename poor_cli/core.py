"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine used by the PoorCLI terminal client and
the Neovim plugin.
"""

import asyncio
import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Protocol, Tuple

from .audit_log import AuditEventType, AuditLogger, AuditSeverity
from .config import ConfigManager, Config
from .providers.base import BaseProvider, ProviderResponse, FunctionCall
from .providers.provider_factory import ProviderFactory
from .tools_async import ToolRegistryAsync, ToolOutcome
from .checkpoint import CheckpointManager
from .repo_config import RepoConfig, get_repo_config
from .context import ContextManager, get_context_manager
from .instructions import InstructionManager, InstructionSnapshot
from .mcp_client import MCPManager
from .policy_hooks import HookExecutionResult, PolicyHookManager
from .prompts import (
    build_fim_prompt as _build_fim_prompt,
    build_tool_calling_system_instruction,
)
from .exceptions import (
    PoorCLIError,
    ConfigurationError,
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


# ── CoreEvent: structured events yielded by the agentic loop ─────────

@dataclass
class CoreEvent:
    """Structured event emitted by the agentic loop."""
    type: str # text_chunk | tool_call_start | tool_result | permission_request | cost_update | progress | done
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def text_chunk(chunk: str, request_id: str = "") -> "CoreEvent":
        return CoreEvent(type="text_chunk", data={"chunk": chunk, "requestId": request_id})

    @staticmethod
    def tool_call_start(
        tool_name: str,
        tool_args: Dict[str, Any],
        call_id: str = "",
        iteration: int = 0,
        cap: int = 25,
        paths: Optional[List[str]] = None,
    ) -> "CoreEvent":
        return CoreEvent(type="tool_call_start", data={
            "toolName": tool_name, "toolArgs": tool_args, "callId": call_id,
            "iterationIndex": iteration, "iterationCap": cap,
            "paths": paths or [],
        })

    @staticmethod
    def tool_result(
        tool_name: str,
        result: str,
        call_id: str = "",
        iteration: int = 0,
        cap: int = 25,
        diff: str = "",
        paths: Optional[List[str]] = None,
        checkpoint_id: Optional[str] = None,
        changed: Optional[bool] = None,
        message: str = "",
    ) -> "CoreEvent":
        return CoreEvent(type="tool_result", data={
            "toolName": tool_name, "toolResult": result, "callId": call_id,
            "iterationIndex": iteration, "iterationCap": cap,
            "diff": diff,
            "paths": paths or [],
            "checkpointId": checkpoint_id,
            "changed": changed,
            "message": message,
        })

    @staticmethod
    def permission_request(
        tool_name: str,
        tool_args: Dict[str, Any],
        prompt_id: str = "",
        preview: Optional[Dict[str, Any]] = None,
    ) -> "CoreEvent":
        return CoreEvent(type="permission_request", data={
            "toolName": tool_name, "toolArgs": tool_args, "promptId": prompt_id,
            "preview": preview or {},
        })

    @staticmethod
    def cost_update(input_tokens: int = 0, output_tokens: int = 0, estimated_cost: float = 0.0) -> "CoreEvent":
        return CoreEvent(type="cost_update", data={
            "inputTokens": input_tokens, "outputTokens": output_tokens, "estimatedCost": estimated_cost,
        })

    @staticmethod
    def progress(phase: str, message: str, iteration: int = 0, cap: int = 25) -> "CoreEvent":
        return CoreEvent(type="progress", data={
            "phase": phase, "message": message, "iterationIndex": iteration, "iterationCap": cap,
        })

    @staticmethod
    def done(reason: str = "complete") -> "CoreEvent":
        return CoreEvent(type="done", data={"reason": reason})


class HistoryAdapter(Protocol):
    """History backend contract used by PoorCLICore."""

    def start_session(self, model: str) -> None: ...

    def add_message(self, role: str, content: str) -> None: ...

    def clear_history(self) -> None: ...


class RepoHistoryAdapter:
    """Repository-scoped history adapter backed by RepoConfig."""

    def __init__(self, repo_config: RepoConfig):
        self._repo_config = repo_config

    def start_session(self, model: str) -> None:
        self._repo_config.start_session(model=model)

    def add_message(self, role: str, content: str) -> None:
        self._repo_config.add_message(role=role, content=content)

    def clear_history(self) -> None:
        self._repo_config.clear_history()


class PoorCLICore:
    """
    Headless AI coding assistant engine.
    
    This is the core wrapper layer shared by supported clients:
    - Rust TUI (via JSON-RPC server)
    - Neovim plugin (via JSON-RPC server)
    
    Attributes:
        provider: The AI provider (Gemini, OpenAI, Claude, Ollama)
        tool_registry: Registry of available tools
        history_adapter: Conversation history backend
        checkpoint_manager: File checkpoint/undo system
        config: Configuration object
    """
    SUPPORTED_CLIENTS: Tuple[str, str] = ("cli", "neovim")
    
    def __init__(
        self,
        config_path: Optional[Path] = None,
        history_adapter: Optional[HistoryAdapter] = None,
    ):
        """
        Initialize PoorCLICore with optional config path.
        
        Args:
            config_path: Optional path to config file. If None, uses default.
            history_adapter: Optional history backend override.
        """
        self.provider: Optional[BaseProvider] = None
        self.tool_registry: Optional[ToolRegistryAsync] = None
        self.history_adapter: Optional[HistoryAdapter] = history_adapter
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.config: Optional[Config] = None
        self._config_manager: Optional[ConfigManager] = None
        self._config_path = config_path
        self._initialized = False
        self._system_instruction: Optional[str] = None
        self._instruction_manager: Optional[InstructionManager] = None
        self._hook_manager: Optional[PolicyHookManager] = None
        self._audit_logger: Optional[AuditLogger] = None
        self._mcp_manager: Optional[MCPManager] = None
        self._pending_events: List[CoreEvent] = []

        # Permission callback for file operations
        # Set this to a callable(tool_name: str, tool_args: dict) -> Awaitable[bool]
        self._permission_callback: Optional[Callable[..., Any]] = None

        # Context manager for intelligent context gathering
        self._context_manager: Optional[ContextManager] = None

        # Cancel event for mid-loop cancellation
        self._cancel_event: asyncio.Event = asyncio.Event()

        logger.info("PoorCLICore instance created")
    
    async def initialize(
        self,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> None:
        """
        Initialize the core engine with provider and tools.
        
        Args:
            provider_name: Provider to use (gemini, openai, anthropic, ollama).
                          If None, uses config default.
            model_name: Model to use. If None, uses config default.
            api_key: API key. If None, uses environment variable.
        
        Raises:
            ConfigurationError: If initialization fails.
        """
        try:
            logger.info("Initializing PoorCLICore...")
            repo_root = Path.cwd().resolve()
            
            # Load configuration
            self._config_manager = ConfigManager(self._config_path)
            self.config = self._config_manager.load()
            
            # Override config with provided values
            if provider_name:
                self.config.model.provider = provider_name
            if model_name:
                self.config.model.model_name = model_name
            
            # Get API key
            resolved_api_key = api_key
            if not resolved_api_key:
                resolved_api_key = self._config_manager.get_api_key(
                    self.config.model.provider
                )
            
            # Ollama doesn't require API key
            if not resolved_api_key and self.config.model.provider != "ollama":
                raise ConfigurationError(
                    f"No API key found for provider: {self.config.model.provider}. "
                    f"Set environment variable: "
                    f"{self.config.model.providers[self.config.model.provider].api_key_env_var}"
                )
            
            # Get provider config for additional settings
            provider_config = self._config_manager.get_provider_config(
                self.config.model.provider
            )
            extra_kwargs = {}
            if provider_config and provider_config.base_url:
                extra_kwargs["base_url"] = provider_config.base_url
            
            # Create provider via factory
            self.provider = ProviderFactory.create(
                provider_name=self.config.model.provider,
                api_key=resolved_api_key or "",
                model_name=self.config.model.model_name,
                **extra_kwargs
            )
            logger.info(f"Created {self.config.model.provider} provider")
            
            # Initialize tool registry
            self.tool_registry = ToolRegistryAsync()
            self._instruction_manager = InstructionManager(repo_root)
            self._hook_manager = PolicyHookManager(repo_root)
            self._audit_logger = AuditLogger(audit_dir=repo_root / ".poor-cli" / "audit")

            if self.config.mcp_servers:
                self._mcp_manager = MCPManager(self.config.mcp_servers)
                await self._mcp_manager.initialize()
                for declaration in self._mcp_manager.get_tool_declarations():
                    tool_name = declaration.get("name")
                    if not tool_name:
                        continue

                    async def _call_mcp_tool(
                        _tool_name: str = tool_name,
                        **kwargs: Any,
                    ) -> str:
                        if not self._mcp_manager:
                            raise PoorCLIError("MCP manager not initialized")
                        return await self._mcp_manager.execute_tool(_tool_name, kwargs)

                    self.tool_registry.register_external_tool(
                        tool_name,
                        _call_mcp_tool,
                        declaration,
                    )
            tool_declarations = self.tool_registry.get_tool_declarations()
            logger.info(f"Registered {len(tool_declarations)} tools")
            
            # Build system instruction
            self._system_instruction = build_tool_calling_system_instruction(str(repo_root))
            
            provider_capabilities = self.provider.get_capabilities()
            init_tools = (
                tool_declarations if provider_capabilities.supports_function_calling else []
            )
            if not provider_capabilities.supports_function_calling:
                logger.info(
                    "Provider %s/%s does not support function calling; initializing without tools",
                    self.config.model.provider,
                    self.config.model.model_name,
                )

            # Initialize provider with tools and system instruction
            await self.provider.initialize(
                tools=init_tools,
                system_instruction=self._system_instruction
            )
            
            # Initialize repository-backed history adapter if enabled
            if self.config.history.auto_save:
                if self.history_adapter is None:
                    self.history_adapter = RepoHistoryAdapter(
                        get_repo_config(
                            enable_legacy_history_migration=(
                                self.config.history.auto_migrate_legacy_history
                            )
                        )
                    )
                self.history_adapter.start_session(self.config.model.model_name)
                logger.info("History adapter initialized")
            
            # Initialize checkpoint manager if enabled
            if self.config.checkpoint.enabled:
                self.checkpoint_manager = CheckpointManager()
                logger.info("Checkpoint manager initialized")
            
            # Initialize context manager
            self._context_manager = get_context_manager()
            logger.info("Context manager initialized")

            await self._emit_policy_hooks(
                "session_start",
                {
                    "provider": self.config.model.provider,
                    "model": self.config.model.model_name,
                    "repoRoot": str(repo_root),
                },
            )
            self._log_audit_event(
                AuditEventType.SESSION_START,
                operation="session_start",
                details={
                    "provider": self.config.model.provider,
                    "model": self.config.model.model_name,
                    "repoRoot": str(repo_root),
                    "mcp": self.get_mcp_status(),
                },
            )
            
            self._initialized = True
            logger.info("PoorCLICore initialization complete")
            
        except ConfigurationError:
            raise
        except Exception as e:
            logger.exception("Failed to initialize PoorCLICore")
            raise ConfigurationError(f"Initialization failed: {e}")
    
    def cancel_request(self) -> None:
        """Signal cancellation of the current agentic loop."""
        self._cancel_event.set()

    @staticmethod
    def _stringify_tool_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {str(key): value for key, value in arguments.items()}

    @staticmethod
    def _current_git_branch(repo_root: Optional[Path] = None) -> str:
        try:
            output = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str((repo_root or Path.cwd()).resolve()),
                stderr=subprocess.DEVNULL,
                text=True,
            )
            branch = output.strip()
            return branch or "unknown"
        except Exception:
            return "unknown"

    def _log_audit_event(
        self,
        event_type: AuditEventType,
        *,
        operation: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        if not self._audit_logger:
            return
        try:
            self._audit_logger.log_event(
                event_type=event_type,
                operation=operation,
                target=target,
                details=details,
                severity=severity,
                success=success,
                error_message=error_message,
            )
        except Exception as error:
            logger.debug("Audit logging failed: %s", error)

    async def _emit_policy_hooks(
        self,
        event: str,
        payload: Dict[str, Any],
    ) -> List[HookExecutionResult]:
        if not self._hook_manager:
            return []
        results = await self._hook_manager.run(event, payload)
        for result in results:
            self._log_audit_event(
                AuditEventType.HOOK_DENY if result.blocked else AuditEventType.HOOK_ALLOW,
                operation=f"hook:{event}",
                target=result.hook.source_path,
                details=result.to_dict(),
                severity=AuditSeverity.WARNING if result.blocked else AuditSeverity.INFO,
                success=not result.blocked,
                error_message=result.stderr or None,
            )
        return results

    async def _record_user_prompt_submission(
        self,
        message: str,
        *,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        request_id: str = "",
    ) -> None:
        payload = {
            "message": message,
            "requestId": request_id,
            "contextFiles": context_files or [],
            "pinnedContextFiles": pinned_context_files or [],
            "contextBudgetTokens": context_budget_tokens,
        }
        await self._emit_policy_hooks("user_prompt_submitted", payload)

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
            target=",".join(self.tool_registry.inspect_mutation_targets(tool_name, tool_args))
            if self.tool_registry
            else None,
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
    ) -> InstructionSnapshot:
        manager = self._instruction_manager or InstructionManager(Path.cwd())
        return manager.build_snapshot(
            referenced_files or [],
            plan_mode_enabled=bool(self.config and self.config.plan_mode.enabled),
        )

    def _build_full_message(self, message: str, context_files: Optional[List[str]] = None) -> str:
        """Legacy sync helper retained for compatibility."""
        return message

    async def _select_context_files(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ):
        if not self._context_manager:
            return None
        return await self._context_manager.select_context_files(
            message=message,
            explicit_files=context_files or [],
            pinned_files=pinned_context_files or [],
            repo_root=str(Path.cwd()),
            max_files=12,
        )

    async def _build_context_message(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> str:
        """Build a backend-owned context message with excerpted files."""
        referenced_files: List[str] = []
        referenced_files.extend(context_files or [])
        referenced_files.extend(pinned_context_files or [])

        context_result = None
        if self._context_manager:
            context_result = await self._select_context_files(
                message=message,
                context_files=context_files,
                pinned_context_files=pinned_context_files,
                context_budget_tokens=context_budget_tokens,
            )
            if context_result is not None:
                referenced_files.extend(file_ctx.path for file_ctx in context_result.files)

        instruction_snapshot = self._inspect_instruction_snapshot(referenced_files)
        instruction_prefix = instruction_snapshot.render_prompt_prefix()

        if not self._context_manager or context_result is None or not context_result.files:
            if instruction_prefix:
                return f"{instruction_prefix}\n\nUser request: {message}"
            return message

        logger.info(context_result.message)
        context_message = await self._context_manager.build_context_message(
            message,
            context_result,
            max_tokens=context_budget_tokens,
        )
        if not instruction_prefix:
            return context_message
        return f"{instruction_prefix}\n\n{context_message}"

    async def preview_context(
        self,
        message: str = "",
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Preview backend-owned context selection without sending a chat turn."""
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        if not self._context_manager:
            return {"files": [], "totalTokens": 0, "truncated": False, "message": "Context manager unavailable"}
        return await self._context_manager.preview_context(
            message=message,
            explicit_files=context_files or [],
            pinned_files=pinned_context_files or [],
            repo_root=str(Path.cwd()),
            max_tokens=context_budget_tokens,
            max_files=12,
        )

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

    @staticmethod
    def _confidence_bucket(percent: int) -> str:
        """Map confidence percentage to one of five confidence categories."""
        bounded = max(0, min(percent, 100))
        for upper_bound, category in _CONFIDENCE_BANDS:
            if bounded <= upper_bound:
                return category
        return "Very High"

    @staticmethod
    def _extract_confidence_percent(response_text: str) -> Optional[int]:
        """Extract the model-reported confidence percentage when present."""
        matches = list(_CONFIDENCE_PERCENT_RE.finditer(response_text))
        if not matches:
            return None
        raw_percent = int(matches[-1].group(1))
        return max(0, min(raw_percent, 100))

    def _build_confidence_line(self, percent: int) -> str:
        """Build the normalized confidence line shown to users."""
        category = self._confidence_bucket(percent)
        return f"Confidence: {category} ({percent}%)"

    @staticmethod
    def _has_trailing_confidence_line(response_text: str) -> bool:
        """Check whether the final non-empty line already contains confidence output."""
        lines = response_text.splitlines()
        if not lines:
            return False
        return bool(_CONFIDENCE_LINE_RE.match(lines[-1].strip()))

    def _ensure_confidence_line(self, response_text: str) -> Tuple[str, str]:
        """
        Ensure every non-empty response ends with a confidence score line.

        Returns:
            Tuple of (final_text, appended_suffix). appended_suffix is empty when
            no new confidence text was added.
        """
        trimmed = response_text.rstrip()
        if not trimmed:
            return response_text, ""

        if self._has_trailing_confidence_line(trimmed):
            return trimmed, ""

        percent = self._extract_confidence_percent(trimmed)
        if percent is None:
            percent = _DEFAULT_CONFIDENCE_PERCENT

        confidence_line = self._build_confidence_line(percent)
        if trimmed.endswith(confidence_line):
            return trimmed, ""

        separator = "\n\n"
        appended_suffix = f"{separator}{confidence_line}"
        return f"{trimmed}{appended_suffix}", appended_suffix

    def _tool_result_text(self, result: Any) -> str:
        if isinstance(result, ToolOutcome):
            return result.to_json()
        return str(result)

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
        if self.tool_registry:
            return self.tool_registry.inspect_mutation_targets(tool_name, tool_args)
        return []

    @staticmethod
    def _tool_result_checkpoint_id(result: Any) -> Optional[str]:
        if isinstance(result, ToolOutcome):
            return result.checkpoint_id
        return None

    @staticmethod
    def _tool_result_changed(result: Any) -> Optional[bool]:
        if isinstance(result, ToolOutcome):
            return result.changed
        return None

    @staticmethod
    def _tool_result_message(result: Any) -> str:
        if isinstance(result, ToolOutcome):
            return result.message
        return ""

    @staticmethod
    def _normalize_permission_decision(decision: Any) -> Dict[str, Any]:
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

    async def _request_permission(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._permission_callback:
            return {"allowed": True, "approvedPaths": [], "approvedChunks": []}

        try:
            decision = await self._permission_callback(tool_name, tool_args, preview)
        except TypeError:
            decision = await self._permission_callback(tool_name, tool_args)
        return self._normalize_permission_decision(decision)

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

        targets = self.tool_registry.inspect_mutation_targets(tool_name, tool_args)
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

    async def _execute_tool_internal(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        targets = self.tool_registry.inspect_mutation_targets(tool_name, arguments)
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
            result = await self.tool_registry.execute_tool_raw(tool_name, arguments)
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
                "post_tool_use",
                {**post_payload, "success": False, "error": str(error)},
            )
            raise

        if isinstance(result, ToolOutcome):
            if checkpoint_id and not result.checkpoint_id:
                result.checkpoint_id = checkpoint_id
            if result.ok and result.changed and self._context_manager:
                for file_path in self._tool_result_paths(tool_name, arguments, result):
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
        return result

    async def send_message_events(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        request_id: str = "",
    ) -> AsyncIterator[CoreEvent]:
        """
        Send a message and yield CoreEvent objects (structured agentic events).

        This is the primary method for streaming clients. It yields tool_call_start,
        tool_result, text_chunk, cost_update, progress, and done events.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        self._cancel_event.clear()
        max_iterations = self.config.agentic.max_iterations if self.config else 25
        iteration = 0

        logger.info(f"Sending message (events): {message[:100]}...")
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            request_id=request_id,
        )
        full_message = await self._build_context_message(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )

        if self.history_adapter:
            self.history_adapter.add_message("user", message)

        try:
            accumulated_text = ""

            async for chunk in self.provider.send_message_stream(full_message):
                if self._cancel_event.is_set():
                    yield CoreEvent.done(reason="cancelled")
                    return

                if chunk.function_calls:
                    if chunk.metadata:
                        usage = chunk.metadata.get("usage", {})
                        if usage:
                            yield CoreEvent.cost_update(
                                input_tokens=usage.get("input_tokens", 0),
                                output_tokens=usage.get("output_tokens", 0),
                            )

                    tool_results = await self._handle_function_calls_events(chunk, iteration, max_iterations, request_id)
                    for ev in self._pending_events:
                        yield ev
                    self._pending_events = []

                    response = await self.provider.send_message(tool_results)
                    if response.content:
                        accumulated_text += response.content
                        yield CoreEvent.text_chunk(response.content, request_id)

                    while response.function_calls:
                        iteration += 1
                        if self._cancel_event.is_set():
                            yield CoreEvent.done(reason="cancelled")
                            return
                        if iteration >= max_iterations:
                            yield CoreEvent.done(reason="iteration_cap")
                            return

                        yield CoreEvent.progress("tool_loop", f"Iteration {iteration}/{max_iterations}", iteration, max_iterations)

                        tool_results = await self._handle_function_calls_events(response, iteration, max_iterations, request_id)
                        for ev in self._pending_events:
                            yield ev
                        self._pending_events = []

                        response = await self.provider.send_message(tool_results)
                        if response.content:
                            accumulated_text += response.content
                            yield CoreEvent.text_chunk(response.content, request_id)

                        if response.metadata:
                            usage = response.metadata.get("usage", {})
                            if usage:
                                yield CoreEvent.cost_update(
                                    input_tokens=usage.get("input_tokens", 0),
                                    output_tokens=usage.get("output_tokens", 0),
                                )

                    break

                elif chunk.content:
                    accumulated_text += chunk.content
                    yield CoreEvent.text_chunk(chunk.content, request_id)

            accumulated_text, confidence_suffix = self._ensure_confidence_line(accumulated_text)
            if confidence_suffix:
                yield CoreEvent.text_chunk(confidence_suffix, request_id)

            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            yield CoreEvent.done(reason="complete")
            logger.info(f"Message complete (events), {len(accumulated_text)} chars")

        except Exception as e:
            logger.exception("Error sending message (events)")
            raise PoorCLIError(f"Failed to send message: {e}")

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
        import difflib
        diff_lines = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        ))
        return "".join(diff_lines)

    async def _handle_function_calls_events(
        self,
        response: ProviderResponse,
        iteration: int,
        max_iterations: int,
        request_id: str,
    ) -> Any:
        """Handle function calls with auto-approve/deny guardrails and diff capture."""
        if not response.function_calls:
            return None

        self._pending_events: List[CoreEvent] = []
        tool_results = []

        for fc in response.function_calls:
            tool_name = fc.name
            tool_args = fc.arguments
            preview_payload: Optional[Dict[str, Any]] = None
            tool_paths = self.tool_registry.inspect_mutation_targets(tool_name, tool_args) if self.tool_registry else []

            self._pending_events.append(
                CoreEvent.tool_call_start(
                    tool_name,
                    tool_args,
                    fc.id,
                    iteration,
                    max_iterations,
                    paths=tool_paths,
                )
            )
            logger.info(f"Executing tool: {tool_name}")

            # 1. Check auto-approve/deny from config
            auto = self._check_auto_permission(tool_name, tool_args)
            if auto is False:
                result = "Operation denied by safety policy"
                self._audit_permission_decision(
                    tool_name,
                    tool_args,
                    allowed=False,
                    source="config:auto-deny",
                )
                self._pending_events.append(
                    CoreEvent.tool_result(
                        tool_name,
                        result,
                        fc.id,
                        iteration,
                        max_iterations,
                        paths=tool_paths,
                        changed=False,
                        message=result,
                    )
                )
                tool_results.append({"id": fc.id, "name": tool_name, "result": result})
                continue

            # 2. If not auto-approved, check interactive permission callback
            if auto is None and self._permission_callback:
                try:
                    if tool_name in _MUTATING_TOOLS and self.tool_registry:
                        try:
                            preview_payload = await self.preview_mutation(tool_name, tool_args)
                            preview_payload["requestId"] = request_id
                            tool_paths = preview_payload.get("paths") or tool_paths
                        except Exception as preview_error:
                            logger.warning(
                                "Failed to preview mutation for %s: %s",
                                tool_name,
                                preview_error,
                            )
                    self._pending_events.append(
                        CoreEvent.permission_request(
                            tool_name,
                            tool_args,
                            request_id,
                            preview=preview_payload,
                        )
                    )
                    permission = await self._request_permission(
                        tool_name,
                        tool_args,
                        preview_payload,
                    )
                    if not permission["allowed"]:
                        self._audit_permission_decision(
                            tool_name,
                            tool_args,
                            allowed=False,
                            source="interactive",
                            preview=preview_payload,
                        )
                        result = "Operation cancelled by user"
                        self._pending_events.append(
                            CoreEvent.tool_result(
                                tool_name,
                                result,
                                fc.id,
                                iteration,
                                max_iterations,
                                diff=(preview_payload or {}).get("diff", ""),
                                paths=tool_paths,
                                changed=False,
                                message=result,
                            )
                            )
                        tool_results.append({"id": fc.id, "name": tool_name, "result": result})
                        continue
                    self._audit_permission_decision(
                        tool_name,
                        tool_args,
                        allowed=True,
                        source="interactive",
                        preview=preview_payload,
                    )
                    if permission["approvedChunks"] or permission["approvedPaths"]:
                        try:
                            tool_args = await self._apply_permission_scope(
                                tool_name,
                                tool_args,
                                permission["approvedPaths"],
                                permission["approvedChunks"],
                            )
                            tool_paths = (
                                self.tool_registry.inspect_mutation_targets(tool_name, tool_args)
                                if self.tool_registry
                                else tool_paths
                            )
                        except Exception as scope_error:
                            result = f"Operation cancelled: {scope_error}"
                            self._pending_events.append(
                                CoreEvent.tool_result(
                                    tool_name,
                                    result,
                                    fc.id,
                                    iteration,
                                    max_iterations,
                                    diff=(preview_payload or {}).get("diff", ""),
                                    paths=tool_paths,
                                    changed=False,
                                    message=str(scope_error),
                                )
                            )
                            tool_results.append({"id": fc.id, "name": tool_name, "result": result})
                            continue
                except Exception as e:
                    logger.error(f"Permission callback error: {e}")
            elif auto is True:
                self._audit_permission_decision(
                    tool_name,
                    tool_args,
                    allowed=True,
                    source="config:auto-approve",
                )

            # 3. Execute the tool
            try:
                result = await self._execute_tool_internal(tool_name, tool_args)
            except Exception as e:
                result = f"Error: {e}"
                logger.error(f"Tool execution failed: {e}")

            result_text = self._tool_result_text(result)
            self._pending_events.append(
                CoreEvent.tool_result(
                    tool_name,
                    result_text,
                    fc.id,
                    iteration,
                    max_iterations,
                    diff=self._tool_result_diff(result),
                    paths=self._tool_result_paths(tool_name, tool_args, result),
                    checkpoint_id=self._tool_result_checkpoint_id(result),
                    changed=self._tool_result_changed(result),
                    message=self._tool_result_message(result),
                )
            )
            tool_results.append({"id": fc.id, "name": tool_name, "result": result_text})

        if not self.provider:
            return tool_results
        return self.provider.format_tool_results(tool_results)

    async def send_message(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Send a message and yield streaming text chunks.

        This method handles function calls internally and yields only text content.
        Legacy interface — streaming clients should use send_message_events().
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        logger.info(f"Sending message: {message[:100]}...")
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        full_message = await self._build_context_message(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )

        if self.history_adapter:
            self.history_adapter.add_message("user", message)

        try:
            accumulated_text = ""

            async for chunk in self.provider.send_message_stream(full_message):
                if chunk.function_calls:
                    tool_results = await self._handle_function_calls(chunk)
                    response = await self.provider.send_message(tool_results)
                    if response.content:
                        accumulated_text += response.content
                        yield response.content
                    while response.function_calls:
                        tool_results = await self._handle_function_calls(response)
                        response = await self.provider.send_message(tool_results)
                        if response.content:
                            accumulated_text += response.content
                            yield response.content
                    break
                elif chunk.content:
                    accumulated_text += chunk.content
                    yield chunk.content

            accumulated_text, confidence_suffix = self._ensure_confidence_line(accumulated_text)
            if confidence_suffix:
                yield confidence_suffix

            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            logger.info(f"Message complete, {len(accumulated_text)} chars")

        except Exception as e:
            logger.exception("Error sending message")
            raise PoorCLIError(f"Failed to send message: {e}")

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
            
            # Execute the tool
            try:
                result = await self._execute_tool_internal(tool_name, tool_args)
            except Exception as e:
                result = f"Error: {e}"
                logger.error(f"Tool execution failed: {e}")

            result_text = self._tool_result_text(result)
            tool_results.append({
                "id": fc.id,
                "name": tool_name,
                "result": result_text
            })
        
        if not self.provider:
            return tool_results

        # Delegate provider-specific formatting to provider adapters.
        return self.provider.format_tool_results(tool_results)

    async def send_message_sync(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a message and return complete response text.
        
        This is a non-streaming version that waits for the complete response.
        Handles function calls internally.
        
        Args:
            message: The message to send to the AI.
            context_files: Optional list of file paths to include as context.
        
        Returns:
            Complete response text from the AI.
        
        Raises:
            PoorCLIError: If not initialized or message sending fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Sending message (sync): {message[:100]}...")
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        
        full_message = await self._build_context_message(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        
        # Save to history
        if self.history_adapter:
            self.history_adapter.add_message("user", message)
        
        try:
            response = await self.provider.send_message(full_message)
            accumulated_text = response.content or ""
            
            # Handle function calls
            while response.function_calls:
                tool_results = await self._handle_function_calls(response)
                response = await self.provider.send_message(tool_results)
                if response.content:
                    accumulated_text += response.content
            
            accumulated_text, _ = self._ensure_confidence_line(accumulated_text)

            # Save assistant response to history
            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)
            
            logger.info(f"Message complete (sync), {len(accumulated_text)} chars")
            return accumulated_text
            
        except Exception as e:
            logger.exception("Error sending message (sync)")
            raise PoorCLIError(f"Failed to send message: {e}")

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

    def build_fim_prompt(
        self,
        code_before: str,
        code_after: str,
        instruction: str,
        file_path: str,
        language: str
    ) -> str:
        """
        Build a Fill-in-Middle (FIM) prompt for code completion.
        
        Args:
            code_before: Code before the cursor position.
            code_after: Code after the cursor position.
            instruction: Optional instruction for what to generate.
            file_path: Path to the current file.
            language: Programming language of the file.
        
        Returns:
            FIM prompt string for the AI.
        """
        import os
        filename = os.path.basename(file_path) if file_path else "unknown"
        
        # Determine provider for native FIM format selection
        provider_name = self.config.model.model_name if self.config else "generic"
        
        # Use the prompts module for consistent FIM formatting
        return _build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            filename=filename,
            language=language,
            provider=provider_name
        )

    async def inline_complete(
        self,
        code_before: str,
        code_after: str,
        instruction: str,
        file_path: str,
        language: str
    ) -> AsyncIterator[str]:
        """
        Generate inline code completion (FIM - Fill in Middle).
        
        This is the main method for Windsurf-like ghost text completion.
        
        Args:
            code_before: Code before the cursor position.
            code_after: Code after the cursor position.
            instruction: Optional instruction for what to generate.
            file_path: Path to the current file.
            language: Programming language of the file.
        
        Yields:
            Code completion chunks as they arrive.
        
        Raises:
            PoorCLIError: If not initialized or completion fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Inline complete for {file_path} ({language})")
        
        # Build FIM prompt
        prompt = self.build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language
        )
        
        try:
            # Stream the completion
            async for chunk in self.provider.send_message_stream(prompt):
                if chunk.content:
                    yield chunk.content
            
            logger.info("Inline completion finished")
            
        except Exception as e:
            logger.exception("Error in inline completion")
            raise PoorCLIError(f"Inline completion failed: {e}")

    @property
    def permission_callback(self) -> Optional[Callable[..., Any]]:
        """
        Get the permission callback for file operations.
        
        Returns:
            The permission callback function or None.
        """
        return self._permission_callback
    
    @permission_callback.setter
    def permission_callback(self, callback: Optional[Callable[..., Any]]) -> None:
        """
        Set the permission callback for file operations.
        
        The callback should be an async function that takes:
            - tool_name: str - Name of the tool being executed
            - tool_args: dict - Arguments to the tool
        
        And returns:
            - bool - True to allow, False to deny
        
        Args:
            callback: The permission callback function.
        """
        self._permission_callback = callback
        logger.info("Permission callback updated")

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

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get information about the current provider.
        
        Returns:
            Dict with keys: name, model, capabilities, supported_clients.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider or not self.config:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        capabilities = {}
        if hasattr(self.provider, 'capabilities') and self.provider.capabilities:
            caps = self.provider.capabilities
            capabilities = {
                "streaming": caps.supports_streaming,
                "function_calling": caps.supports_function_calling,
                "vision": caps.supports_vision,
                "max_context_tokens": caps.max_context_tokens,
            }
        
        return {
            "name": self.config.model.provider,
            "model": self.config.model.model_name,
            "capabilities": capabilities,
            "supported_clients": list(self.SUPPORTED_CLIENTS),
        }

    def inspect_instruction_stack(
        self,
        referenced_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return the active deterministic instruction stack."""
        return self._inspect_instruction_snapshot(referenced_files).to_dict()

    def get_policy_status(self) -> Dict[str, Any]:
        """Return repo-local policy and audit status."""
        hooks = self._hook_manager.status() if self._hook_manager else {
            "hooksDir": str(Path.cwd() / ".poor-cli" / "hooks"),
            "totalHooks": 0,
            "events": {},
        }
        return {
            "hooks": hooks,
            "audit": {
                "enabled": self._audit_logger is not None,
                "path": str(self._audit_logger.audit_dir) if self._audit_logger else "",
            },
        }

    def get_mcp_status(self) -> Dict[str, Any]:
        """Return MCP connectivity and tool registration status."""
        if self._mcp_manager is None:
            return {
                "configuredServers": 0,
                "connectedServers": 0,
                "toolCount": 0,
                "servers": {},
            }
        return self._mcp_manager.status()

    async def shutdown(self) -> None:
        """Release external resources owned by the core."""
        if self._mcp_manager is not None:
            await self._mcp_manager.shutdown()

    async def clear_history(self) -> None:
        """
        Clear conversation history.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info("Clearing history")
        
        if hasattr(self.provider, 'clear_history'):
            await self.provider.clear_history()
        
        if self.history_adapter:
            self.history_adapter.clear_history()

    async def compact_context(self, strategy: str) -> Dict[str, Any]:
        """Apply a context management strategy to reduce conversation size."""
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        history = self.get_history()
        messages_before = len(history)
        if strategy == "compact":
            return await self._compact_summarize(history, messages_before)
        elif strategy == "compress":
            return self._compact_compress(history, messages_before)
        elif strategy == "handoff":
            return await self._compact_handoff(history, messages_before)
        else:
            raise PoorCLIError(f"Unknown compaction strategy: {strategy}")

    async def _compact_summarize(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Summarize conversation in-place, re-seed provider."""
        conversation_text = self._history_to_text(history)
        if not conversation_text.strip():
            return {"strategy": "compact", "summary": "(empty history)", "messages_before": messages_before, "messages_after": 0}
        prompt = (
            "Summarize the following conversation concisely. "
            "Preserve key decisions, file paths, code changes, and current task state. "
            "Output only the summary, no preamble.\n\n"
            f"{conversation_text}"
        )
        response = await self.provider.send_message(prompt) # one-shot call outside the chat session
        summary = response.content.strip() if response.content else "(no summary generated)"
        await self.provider.clear_history()
        if self.history_adapter:
            self.history_adapter.clear_history()
        await self.provider.send_message(f"[Context from previous conversation]\n{summary}") # inject summary as context
        if self.history_adapter:
            self.history_adapter.add_message("user", f"[Context from previous conversation]\n{summary}")
        return {"strategy": "compact", "summary": summary, "messages_before": messages_before, "messages_after": 1}

    def _compact_compress(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Strip tool calls/results, keep user+assistant text only."""
        compressed = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("system", "tool", "function"): # skip non-conversation messages
                continue
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif "text" in part:
                            text_parts.append(str(part["text"]))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = "\n".join(text_parts)
            if not content or not content.strip():
                continue
            parts = msg.get("parts") # gemini uses 'parts' key
            if parts and not content:
                text_parts = [p for p in parts if isinstance(p, str)]
                content = "\n".join(text_parts)
            if role == "model":
                role = "assistant"
            if role in ("user", "assistant"):
                compressed.append({"role": role, "content": content})
        self.provider.set_history(compressed)
        if self.history_adapter:
            self.history_adapter.clear_history()
            for msg in compressed:
                self.history_adapter.add_message(msg["role"], msg["content"])
        return {"strategy": "compress", "summary": f"Kept {len(compressed)} text messages", "messages_before": messages_before, "messages_after": len(compressed)}

    async def _compact_handoff(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Generate summary, start completely new session."""
        conversation_text = self._history_to_text(history)
        if not conversation_text.strip():
            await self.clear_history()
            return {"strategy": "handoff", "summary": "(empty history)", "messages_before": messages_before, "messages_after": 0}
        prompt = (
            "Create a handoff summary for a new conversation thread. Include:\n"
            "- Current task and goal\n"
            "- Key decisions made\n"
            "- Files modified or relevant\n"
            "- Open items or next steps\n"
            "Be concise. Output only the summary.\n\n"
            f"{conversation_text}"
        )
        response = await self.provider.send_message(prompt)
        summary = response.content.strip() if response.content else "(no summary generated)"
        await self.clear_history()
        handoff_msg = f"[Handoff from previous session]\n{summary}" # seed new session with handoff context
        await self.provider.send_message(handoff_msg)
        if self.history_adapter:
            self.history_adapter.add_message("user", handoff_msg)
        return {"strategy": "handoff", "summary": summary, "messages_before": messages_before, "messages_after": 1}

    def _history_to_text(self, history: List[Dict[str, Any]]) -> str:
        """Convert history to readable text for summarization."""
        lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(str(part["text"]))
                content = "\n".join(text_parts)
            parts = msg.get("parts")
            if parts and not content:
                text_parts = [p for p in parts if isinstance(p, str)]
                content = "\n".join(text_parts)
            if content and content.strip():
                lines.append(f"{role}: {content[:2000]}") # cap per message
        return "\n\n".join(lines[-50:]) # last 50 messages max

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get conversation history in normalized format.
        
        Returns:
            List of dicts with 'role' and 'content' keys.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        history = []
        
        if hasattr(self.provider, 'get_history'):
            raw_history = self.provider.get_history()
            for entry in raw_history:
                if isinstance(entry, dict):
                    history.append({
                        "role": entry.get("role", "unknown"),
                        "content": entry.get("content", "")
                    })
        
        return history

    async def switch_provider(
        self,
        provider_name: str,
        model_name: Optional[str] = None
    ) -> None:
        """
        Switch to a different AI provider.
        
        Args:
            provider_name: Name of the provider to switch to.
            model_name: Optional model name. If None, uses provider default.
        
        Raises:
            ConfigurationError: If switch fails.
        """
        logger.info(f"Switching to provider: {provider_name}")
        
        # Get API key for new provider
        api_key = self._config_manager.get_api_key(provider_name)
        
        if not api_key and provider_name != "ollama":
            raise ConfigurationError(f"No API key found for provider: {provider_name}")
        
        # Determine model name
        if not model_name:
            provider_config = self.config.model.providers.get(provider_name)
            if provider_config:
                model_name = provider_config.default_model
            else:
                raise ConfigurationError(f"Unknown provider: {provider_name}")
        
        # Get provider config for additional settings
        provider_config = self._config_manager.get_provider_config(provider_name)
        extra_kwargs = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url
        
        # Create the candidate provider, but do not swap global state
        # until initialization succeeds. This avoids ending up on a broken
        # provider instance when initialization fails (e.g., Ollama unreachable).
        candidate_provider = ProviderFactory.create(
            provider_name=provider_name,
            api_key=api_key or "",
            model_name=model_name,
            **extra_kwargs
        )

        # Initialize provider with tools before committing the switch.
        tool_declarations = self.tool_registry.get_tool_declarations()
        provider_capabilities = candidate_provider.get_capabilities()
        init_tools = (
            tool_declarations if provider_capabilities.supports_function_calling else []
        )
        if not provider_capabilities.supports_function_calling:
            logger.info(
                "Provider %s/%s does not support function calling; switching without tools",
                provider_name,
                model_name,
            )
        await candidate_provider.initialize(
            tools=init_tools,
            system_instruction=self._system_instruction
        )

        # Commit provider + config only after successful initialization.
        self.provider = candidate_provider
        self.config.model.provider = provider_name
        self.config.model.model_name = model_name
        
        logger.info(f"Switched to {provider_name}/{model_name}")

    def set_system_instruction(self, instruction: str) -> None:
        """
        Update the system instruction.
        
        Note: Takes effect on next message, not retroactively.
        
        Args:
            instruction: New system instruction.
        """
        self._system_instruction = instruction
        logger.info("System instruction updated")

    @staticmethod
    def _checkpoint_metadata(
        checkpoint: Any,
        restored_files: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Normalize checkpoint metadata for API-style responses."""
        payload = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "created_at": checkpoint.created_at,
            "description": checkpoint.description,
            "operation_type": checkpoint.operation_type,
            "file_count": checkpoint.get_file_count(),
            "total_size_bytes": checkpoint.get_total_size(),
            "tags": checkpoint.tags,
        }
        if restored_files is not None:
            payload["restored_files"] = restored_files
        return payload

    async def create_checkpoint(
        self,
        file_paths: List[str],
        description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a checkpoint for the given files.
        
        Args:
            file_paths: List of file paths to checkpoint.
            description: Description of the checkpoint.
        
        Returns:
            Checkpoint metadata or None if checkpointing is disabled.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        if not self.checkpoint_manager:
            logger.warning("Checkpoint manager not enabled")
            return None
        
        logger.info(f"Creating checkpoint for {len(file_paths)} files")
        
        try:
            checkpoint = await asyncio.to_thread(
                self.checkpoint_manager.create_checkpoint,
                file_paths,
                description
            )
            self._log_audit_event(
                AuditEventType.CHECKPOINT_CREATE,
                operation="checkpoint:create",
                target=",".join(file_paths),
                details={
                    "checkpointId": checkpoint.checkpoint_id,
                    "description": description,
                    "filePaths": file_paths,
                },
            )
            return self._checkpoint_metadata(checkpoint)
        except Exception as e:
            logger.error(f"Checkpoint creation failed: {e}")
            raise PoorCLIError(f"Failed to create checkpoint: {e}")

    async def restore_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Restore a checkpoint.
        
        Args:
            checkpoint_id: ID of the checkpoint to restore.
        
        Returns:
            Checkpoint restore metadata.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        if not self.checkpoint_manager:
            logger.warning("Checkpoint manager not enabled")
            return {}
        
        logger.info(f"Restoring checkpoint: {checkpoint_id}")
        
        try:
            checkpoint = self.checkpoint_manager.get_checkpoint(checkpoint_id)
            if checkpoint is None:
                raise PoorCLIError(f"Checkpoint not found: {checkpoint_id}")

            restored_files = await asyncio.to_thread(
                self.checkpoint_manager.restore_checkpoint,
                checkpoint_id,
            )
            self._log_audit_event(
                AuditEventType.CHECKPOINT_RESTORE,
                operation="checkpoint:restore",
                target=checkpoint_id,
                details={
                    "checkpointId": checkpoint_id,
                    "restoredFiles": restored_files,
                },
            )
            return self._checkpoint_metadata(checkpoint, restored_files=restored_files)
        except Exception as e:
            logger.error(f"Checkpoint restore failed: {e}")
            raise PoorCLIError(f"Failed to restore checkpoint: {e}")
