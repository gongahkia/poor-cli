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
import subprocess
import re
import threading
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Protocol, Tuple

from .audit_log import AuditEventType, AuditLogger, AuditSeverity
from .config import ConfigManager, Config
from .context_compressor import ContextCompressor
from .provider_probe import (
    normalize_routing_mode,
    probe_providers,
    resolve_routing_mode,
    suggested_privacy_posture,
)
from .provider_fallback import ProviderFallbackManager
from .providers.base import BaseProvider, ProviderResponse, FunctionCall, UsageMetadata
from .providers.provider_factory import ProviderFactory
from .run_history import RunHistoryManager, classify_error
from .tools_async import ToolRegistryAsync, ToolOutcome
from .enhanced_tools import CORE_TOOL_GROUP, MCP_GROUP_PREFIX, EnhancedToolRegistry
from .checkpoint import CheckpointManager
from .core_events import CoreEvent, HistoryAdapter, RepoHistoryAdapter
from .repo_config import RepoConfig, get_repo_config
from .context import ContextManager, get_context_manager, chars_per_token
from .instructions import InstructionManager, InstructionSnapshot
from .context_contract import ContextContractManager
from .context_optimizer import CompactionPolicy, TieredContextCompactor
from .context_engine import ContextEngineMixin
from .permission_engine import PermissionEngineMixin
from .mcp_client import MCPManager
from .plan_analyzer import PlanAnalyzer
from .policy_hooks import HookExecutionResult, PolicyHookManager
from .economy import (
    EconomySavingsTracker,
    EconomyTurnReport,
    classify_prompt_complexity,
    distill_prompt,
    apply_economy_preset,
    resolve_output_verbosity,
)
from .token_budget_controller import (
    RuleBasedController,
    TokenBudgetState,
    TokenBudgetAction,
    TurnOutcome as BudgetTurnOutcome,
    build_state_from_engine,
)
from .budget_logger import BudgetLogger
from .vision import detect_image_paths, build_multimodal_content_anthropic, build_multimodal_content_openai, build_multimodal_parts_gemini
from .error_recovery import ErrorRecoveryManager
from .kv_cache_store import maybe_init_kv_cache, build_cache_friendly_prompt, is_local_inference, KVCacheStore
from .thinking_budget import ThinkingBudgetOptimizer
from .semantic_cache import (
    SemanticCache,
    compute_context_hash,
    get_semantic_cache,
    reset_semantic_cache,
)
from .tool_output_filter import merge_filter_stats
from .prompts import (
    build_fim_prompt as _build_fim_prompt,
    build_tool_calling_system_instruction,
    detect_tone_from_user_memories,
    get_system_instruction,
)
from .skills import InstructionSkillContext, SkillLoadPlan, SkillRegistry
from .workflow_templates import get_workflow_template, list_workflow_templates
from .exceptions import (
    PoorCLIError,
    ConfigurationError,
    MissingAPIKeyError,
    APIRateLimitError,
    APIError,
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

from .core_provider_info import ProviderInfoMixin


class PoorCLICore(PermissionEngineMixin, ContextEngineMixin, ProviderInfoMixin):
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
    SUPPORTED_CLIENTS: Tuple[str, ...] = ("cli", "neovim")
    
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
        self._system_context_hash: Optional[str] = None
        self._approved_write_paths: set = set()
        self._instruction_manager: Optional[InstructionManager] = None
        self._context_contract: Optional[ContextContractManager] = None
        self._last_instruction_snapshot: Optional[InstructionSnapshot] = None
        self._last_instruction_skill_plan: Optional[SkillLoadPlan] = None
        self._hook_manager: Optional[PolicyHookManager] = None
        self._audit_logger: Optional[AuditLogger] = None
        self._mcp_manager: Optional[MCPManager] = None
        self._active_tool_groups: Tuple[str, ...] = tuple()
        self._active_tool_names: set[str] = set()
        self._active_tool_declarations: List[Dict[str, Any]] = []
        self._plan_analyzer: PlanAnalyzer = PlanAnalyzer()
        self._pending_events: List[CoreEvent] = []
        self._plan_callback: Optional[Callable[..., Any]] = None
        self._init_progress_callback: Optional[Callable[[str], None]] = None

        # Permission callback for file operations
        # Set this to a callable(tool_name: str, tool_args: dict) -> Awaitable[bool]
        self._permission_callback: Optional[Callable[..., Any]] = None

        # Context manager for intelligent context gathering
        self._context_manager: Optional[ContextManager] = None

        # Repo knowledge graph (initialized if repo_index.enabled)
        self._repo_graph: Any = None
        self._repo_graph_task: Optional[asyncio.Task] = None # background indexing task

        # Cancel events for in-flight request cancellation.
        self._cancel_event: threading.Event = threading.Event()
        self._cancel_events: Dict[str, threading.Event] = {}

        # Cost tracking for guardrails
        self._session_total_input_tokens: int = 0
        self._session_total_output_tokens: int = 0
        self._session_total_cost_usd: float = 0.0
        self._session_cache_creation_input_tokens: int = 0
        self._session_cache_read_input_tokens: int = 0
        self._session_provider_cache_hits: int = 0
        self._session_provider_cache_misses: int = 0
        self._session_estimated_cache_savings_usd: float = 0.0
        self._task_input_tokens: int = 0
        self._task_output_tokens: int = 0
        self._task_cost_usd: float = 0.0
        self._cost_warning_emitted: bool = False
        self._turn_economy: EconomyTurnReport = EconomyTurnReport()

        # Context compressor
        self._context_compressor: ContextCompressor = ContextCompressor()
        self._tiered_compactor: TieredContextCompactor = TieredContextCompactor()

        # Working memory (MemGPT-style delta mode)
        self._working_memory_mgr: Optional[Any] = None # lazy init — WorkingMemoryManager

        # Architect/editor dual-model mode
        self._architect_mode = None
        try:
            agentic = getattr(config, "agentic", None) if config else None
            if agentic and getattr(agentic, "architect_mode", False):
                from .architect_mode import ArchitectConfig, ArchitectMode
                arch_cfg = ArchitectConfig(
                    enabled=True,
                    architect_provider=getattr(agentic, "architect_provider", ""),
                    architect_model=getattr(agentic, "architect_model", ""),
                    editor_provider=getattr(agentic, "editor_provider", ""),
                    editor_model=getattr(agentic, "editor_model", ""),
                )
                self._architect_mode = ArchitectMode(arch_cfg)
        except Exception:
            pass

        # Model router for intelligent complexity-based routing
        self._model_router = None
        self._user_explicit_model: bool = False
        try:
            from .model_router import ModelRouter, RouterConfig
            self._model_router = ModelRouter(RouterConfig())
        except Exception:
            pass

        # Token budget controller (Phase 7A)
        self._budget_controller: RuleBasedController = RuleBasedController()
        self._budget_logger: BudgetLogger = BudgetLogger()
        self._thinking_optimizer: ThinkingBudgetOptimizer = ThinkingBudgetOptimizer()
        self._budget_state: Optional[TokenBudgetState] = None
        self._budget_action: Optional[TokenBudgetAction] = None
        self._turn_start_mono: float = 0.0
        self._turn_tool_call_count: int = 0
        self._recent_turn_failures: List[bool] = [] # last N turn success/fail

        # Error recovery suggestions
        self._error_recovery = ErrorRecoveryManager()
        # KV cache store for local inference (lazy-init in initialize())
        self._kv_cache_store: Optional[KVCacheStore] = None
        # Economy mode savings tracker + downshift state
        self._economy_tracker: EconomySavingsTracker = EconomySavingsTracker()
        self._original_model_name: Optional[str] = None
        self._downshifted: bool = False
        self._response_cache: Dict[str, Tuple[str, float]] = {} # prompt_hash -> (response, timestamp)
        self._semantic_cache: Optional[SemanticCache] = None
        self._last_context_hash: str = "" # context hash for semantic cache keying
        self._files_seen_in_session: Dict[str, str] = {} # path -> content hash for context dedup
        self._last_file_contents: Dict[str, str] = {} # path -> last read content for diff-only reads
        self._git_context_cache: Optional[Tuple[str, str]] = None # (git_state_hash, context_text)
        self._turn_tool_cache: Dict[str, str] = {} # per-turn cache for read-only tool results
        self._idle_compact_task: Optional[asyncio.TimerHandle] = None
        self._idle_loop: Optional[asyncio.AbstractEventLoop] = None
        self._auto_history_compact_task: Optional[asyncio.Task] = None
        self._sub_agent_depth: int = 0
        self._pending_llm_compression: Optional[asyncio.Task] = None # background LLM compression
        self._fallback_manager: Optional[ProviderFallbackManager] = None
        self._run_history: Optional[RunHistoryManager] = None
        self._last_context_preview: Dict[str, Any] = {}
        self._last_mutation_summary: Dict[str, Any] = {}
        self._last_fallback_summary: Dict[str, Any] = {}
        self._last_provider_error: str = ""
        self._last_run_id: Optional[str] = None
        self._resolved_routing_mode: str = "manual"
        self._last_compaction_status: Dict[str, Any] = {"state": "idle"}

        logger.info("PoorCLICore instance created")

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
            self.config.model.routing_mode = normalize_routing_mode(
                getattr(self.config.model, "routing_mode", "manual")
            )
            
            # Get API key
            resolved_api_key = api_key
            if not resolved_api_key:
                resolved_api_key = self._config_manager.get_api_key(
                    self.config.model.provider
                )
            
            # Ollama doesn't require API key
            if not resolved_api_key and self.config.model.provider != "ollama":
                raise MissingAPIKeyError(
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
            if self.config.model.provider in ("anthropic", "claude"):
                extra_kwargs["prompt_caching"] = getattr(self.config.model, "prompt_caching", True)

            # Create provider via factory
            self.provider = ProviderFactory.create(
                provider_name=self.config.model.provider,
                api_key=resolved_api_key or "",
                model_name=self.config.model.model_name,
                **extra_kwargs
            )
            logger.info(f"Created {self.config.model.provider} provider")
            
            # Initialize tool registry with output truncation config
            trunc_cfg = self.config.output_truncation
            self.tool_registry = EnhancedToolRegistry(
                config=self.config,
                checkpoint_manager=self.checkpoint_manager,
                output_max_chars=trunc_cfg.max_output_chars if trunc_cfg.enabled else 0,
                output_max_lines=trunc_cfg.max_output_lines if trunc_cfg.enabled else 0,
            )

            # Initialize fallback manager
            if self.config.fallback.enabled and self.config.fallback.chain:
                self._fallback_manager = ProviderFallbackManager(
                    self.config.fallback, self._config_manager
                )
            self._run_history = RunHistoryManager(repo_root)
            self._instruction_manager = InstructionManager(
                repo_root,
                skill_search_paths=self._configured_skill_search_paths(),
            )
            self._context_contract = ContextContractManager(
                repo_root=repo_root,
                instruction_manager=self._instruction_manager,
            )
            self._hook_manager = PolicyHookManager(repo_root)

            # persistent memory
            from .memory import MemoryManager
            self._memory_manager = MemoryManager()
            self._memory_manager.load()
            self._audit_logger = AuditLogger(audit_dir=repo_root / ".poor-cli" / "audit")

            if self.config.mcp_servers:
                self._mcp_manager = MCPManager(self.config.mcp_servers, repo_root=repo_root)
                await self._mcp_manager.initialize()
            self.tool_registry._core = self  # back-ref for compact/delegate tools
            tool_declarations = await self._resolve_tool_declarations_for_groups([CORE_TOOL_GROUP])
            self._active_tool_groups = (CORE_TOOL_GROUP,)
            self._active_tool_names = {
                str(declaration.get("name", "")).strip()
                for declaration in tool_declarations
                if str(declaration.get("name", "")).strip()
            }
            self._active_tool_declarations = list(tool_declarations)
            _deferred = self.tool_registry.get_deferred_tool_names()
            logger.info(
                "Registered %d initial tools, %d deferred",
                len(tool_declarations), len(_deferred),
            )
            
            # Build system instruction (provider-tuned for constrained models)
            terse = resolve_output_verbosity(self.config.economy) == "caveman"
            batched = getattr(self.config.economy, "prefer_batched_reads", False)
            _sandbox_preset = getattr(self.config.sandbox, "default_preset", "workspace-write")
            _plan = bool(self.config.plan_mode.enabled)
            # constrained providers get budget-aware pruning
            _max_sys = 0
            if self.config.model.provider == "ollama":
                _max_sys = 1000 # ~4k chars for small-context local models
            self._system_instruction = build_tool_calling_system_instruction(
                str(repo_root), provider=self.config.model.provider,
                terse_mode=terse, batched_reads=batched,
                sandbox_preset=_sandbox_preset,
                plan_mode=_plan,
                include_agent_tools=not _plan,
                max_system_tokens=_max_sys,
            )

            # inject persistent memory context
            memory_index = self._memory_manager.load_index()
            if memory_index:
                self._system_instruction += (
                    "\n\n## Persistent Memory\n"
                    "The following memories were saved in previous sessions. "
                    "Use memory_save/memory_search/memory_delete/memory_list tools to manage them.\n\n"
                    f"{memory_index}\n"
                )

            # adapt tone based on user profile from memory
            try:
                _user_memories = self._memory_manager.list_all(type_filter="user")
                _user_content = "\n".join(m.content for m in _user_memories)
                _tone = detect_tone_from_user_memories(_user_content)
                if _tone:
                    self._system_instruction += _tone
            except Exception:
                pass
            self._system_context_hash = hashlib.sha256(
                (self._system_instruction or "").encode("utf-8", errors="replace")
            ).hexdigest()

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

            # restore forked history if this session was created via fork
            fork_history = getattr(self, "_fork_history", None)
            if fork_history and self.provider:
                try:
                    self.provider.set_history(fork_history)
                    logger.info("restored %d forked history messages", len(fork_history))
                    del self._fork_history
                except Exception as exc:
                    logger.warning("failed to restore forked history: %s", exc)

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
            
            # Initialize checkpoint manager if enabled (with GC settings)
            if self.config.checkpoint.enabled:
                self.checkpoint_manager = CheckpointManager(
                    max_checkpoints=self.config.checkpoint.max_checkpoints,
                    max_age_hours=self.config.checkpoint.max_age_hours,
                    max_disk_mb=self.config.checkpoint.max_disk_mb,
                )
                if isinstance(self.tool_registry, EnhancedToolRegistry):
                    self.tool_registry.set_checkpoint_manager(self.checkpoint_manager)
                logger.info("Checkpoint manager initialized")
            
            # Initialize context manager
            self._context_manager = get_context_manager()
            logger.info("Context manager initialized")

            # Initialize KV cache for local inference (config-gated, lazy)
            try:
                self._kv_cache_store = await maybe_init_kv_cache(self.config)
            except Exception as e:
                logger.debug("kv cache init skipped: %s", e)

            # Initialize repo knowledge graph (lazy: index builds in background)
            if self.config.repo_index.enabled:
                from .repo_graph import RepoGraph
                self._repo_graph = RepoGraph(repo_root)
                if self.config.repo_index.auto_index_on_start:
                    reindex_mode = self._repo_graph.should_reindex()
                    if reindex_mode == "skip":
                        stats = self._repo_graph.get_stats()
                        dir_count = self._repo_graph._count_directories()
                        logger.info("Repo index (skipped): %s", stats)
                        self._pending_events.append(CoreEvent(
                            type="progress", data={"phase": "repo_index", "message": (
                                f"repo index up to date: {dir_count} directories, {stats['files']} files, "
                                f"{stats['symbols']} symbols, {stats['edges']} edges"
                            )},
                        ))
                    else:
                        async def _build_index_bg(graph, mode, incremental):
                            loop = asyncio.get_event_loop()
                            if mode == "full" or not incremental:
                                stats = await loop.run_in_executor(None, graph.build_index)
                            else:
                                stats = await loop.run_in_executor(None, graph.incremental_update)
                            logger.info("Repo index (%s): %s", mode, stats)
                        self._repo_graph_task = asyncio.create_task(
                            _build_index_bg(self._repo_graph, reindex_mode, self.config.repo_index.incremental)
                        )
                self._context_manager._repo_graph = self._repo_graph
            provider_status = self.get_provider_readiness()
            # emit provider probe results
            ready = [n for n, s in provider_status.items() if s.get("ready")]
            avail = [n for n, s in provider_status.items() if s.get("available") and not s.get("ready")]
            self._pending_events.append(CoreEvent(
                type="progress",
                data={"phase": "provider_probe", "message": f"providers: {', '.join(ready)} ready" + (f" | {', '.join(avail)} available" if avail else "")},
            ))
            self._resolved_routing_mode = resolve_routing_mode(
                self.config.model.routing_mode,
                provider_status,
            )

            await self._emit_policy_hooks(
                "session_start",
                {
                    "provider": self.config.model.provider,
                    "model": self.config.model.model_name,
                    "routingMode": self._resolved_routing_mode,
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
            try:
                self._gc_overflow_files()
            except Exception:
                pass
            logger.info("PoorCLICore initialization complete")
            
        except ConfigurationError:
            raise
        except Exception as e:
            logger.exception("Failed to initialize PoorCLICore")
            raise ConfigurationError(f"Initialization failed: {e}")
    
    def cancel_request(self, request_id: str = "") -> None:
        """Signal cancellation of the current agentic loop."""
        if request_id:
            event = self._cancel_events.get(request_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[request_id] = event
            event.set()
            return
        self._cancel_event.set()

    def _prepare_cancel_event(self, request_id: str = "") -> threading.Event:
        if request_id:
            event = self._cancel_events.get(request_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[request_id] = event
            event.clear()
            return event

        self._cancel_event.clear()
        return self._cancel_event

    def _clear_cancel_event(self, request_id: str = "") -> None:
        if request_id:
            self._cancel_events.pop(request_id, None)
            return
        self._cancel_event.clear()

    def _resolve_provider_config(
        self,
        provider_name: Optional[str],
        model_name: Optional[str],
        api_key: Optional[str] = None,
    ) -> Tuple[str, str, str, Dict[str, Any]]:
        if not self.config or not self._config_manager:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        resolved_provider = provider_name or self.config.model.provider
        resolved_model = model_name or self.config.model.model_name
        if self._resolved_routing_mode != "manual":
            from poor_cli.provider_catalog import select_provider_and_model
            ready = [p for p, s in (self.get_provider_readiness() or {}).items() if s.get("ready")]
            rp, rm = select_provider_and_model(self._resolved_routing_mode, ready)
            if rp and rm:
                resolved_provider, resolved_model = rp, rm
        if not resolved_model:
            provider_config = self.config.model.providers.get(resolved_provider)
            if provider_config:
                resolved_model = provider_config.default_model

        resolved_api_key = api_key
        if not resolved_api_key:
            resolved_api_key = self._config_manager.get_api_key(resolved_provider)

        if not resolved_api_key and resolved_provider != "ollama":
            raise ConfigurationError(
                f"No API key found for provider: {resolved_provider}. "
                f"Set environment variable: "
                f"{self.config.model.providers[resolved_provider].api_key_env_var}"
            )

        provider_config = self._config_manager.get_provider_config(resolved_provider)
        extra_kwargs: Dict[str, Any] = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url

        return resolved_provider, resolved_model, resolved_api_key or "", extra_kwargs

    async def _create_provider_instance(
        self,
        provider_name: Optional[str],
        model_name: Optional[str],
        *,
        api_key: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> BaseProvider:
        resolved_provider, resolved_model, resolved_api_key, extra_kwargs = self._resolve_provider_config(
            provider_name,
            model_name,
            api_key,
        )

        candidate_provider = ProviderFactory.create(
            provider_name=resolved_provider,
            api_key=resolved_api_key,
            model_name=resolved_model,
            **extra_kwargs,
        )
        await candidate_provider.initialize(
            tools=tools or [],
            system_instruction=system_instruction,
        )
        return candidate_provider

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

    def _should_request_plan_review(self, function_calls: List[FunctionCall]) -> bool:
        if not self.config or not self.config.plan_mode.enabled:
            return False

        high_risk_tools = {"delete_file", "bash", "move_file"}
        if any(call.name in high_risk_tools for call in function_calls):
            return True

        if len(function_calls) >= self.config.plan_mode.auto_plan_threshold:
            return True

        affected_files: set[str] = set()
        for call in function_calls:
            affected_files.update(self._inspect_tool_targets(call.name, call.arguments))
        return len(affected_files) >= self.config.plan_mode.auto_plan_threshold

    def _build_plan_payload(
        self,
        user_request: str,
        function_calls: List[FunctionCall],
    ) -> Dict[str, Any]:
        plan = self._plan_analyzer.create_plan_from_request(user_request)
        for call in function_calls:
            self._plan_analyzer.add_function_call_to_plan(
                plan,
                call.name,
                call.arguments,
            )

        steps = [step.description for step in plan.steps]
        summary = (
            f"{len(plan.steps)} step(s), risk={plan.overall_risk_level.value}, "
            f"files={len(plan.get_affected_files())}"
        )
        return {
            "planId": plan.plan_id,
            "summary": summary,
            "steps": steps,
            "originalRequest": user_request,
            "riskLevel": plan.overall_risk_level.value,
            "affectedFiles": plan.get_affected_files(),
        }

    async def _request_plan_review(
        self,
        user_request: str,
        function_calls: List[FunctionCall],
        request_id: str,
    ) -> bool:
        if not self._plan_callback or not self._should_request_plan_review(function_calls):
            return True

        payload = self._build_plan_payload(user_request, function_calls)
        payload["requestId"] = request_id
        self._pending_events.append(
            CoreEvent.plan_request(
                payload["summary"],
                payload["steps"],
                payload["originalRequest"],
                request_id=request_id,
            )
        )
        decision = await self._plan_callback(payload)
        return bool(decision)

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

    def _record_context_preview(self, preview: Dict[str, Any]) -> None:
        self._last_context_preview = dict(preview or {})

    def _record_mutation_summary(
        self,
        *,
        tool_name: str,
        result: Dict[str, Any],
    ) -> None:
        paths = result.get("paths") or []
        changed = result.get("changed")
        checkpoint_id = result.get("checkpointId")
        if not changed and not checkpoint_id:
            return
        active_provider = self.get_provider_info() if self._initialized else {}
        self._last_mutation_summary = {
            "intent": tool_name,
            "paths": paths,
            "checkpointId": checkpoint_id,
            "rollbackHint": f"/restore {checkpoint_id}" if checkpoint_id else "",
            "provider": {
                "name": active_provider.get("name", ""),
                "model": active_provider.get("model", ""),
                "routingMode": self.get_routing_mode() if self.config else "manual",
            },
            "fallback": dict(self._last_fallback_summary),
            "nextSuggestedAction": "/review" if paths else "/status",
        }

    def _provider_summary(self) -> Dict[str, Any]:
        if not self._initialized:
            return {}
        provider_info = self.get_provider_info()
        return {
            "name": provider_info.get("name", ""),
            "model": provider_info.get("model", ""),
            "routingMode": provider_info.get("routingMode", self.get_routing_mode()),
            "fallback": dict(self._last_fallback_summary),
            "lastError": self._last_provider_error,
        }

    @staticmethod
    def _cost_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "input_tokens": max(0, int(after.get("input_tokens", 0)) - int(before.get("input_tokens", 0))),
            "output_tokens": max(0, int(after.get("output_tokens", 0)) - int(before.get("output_tokens", 0))),
            "total_tokens": max(0, int(after.get("total_tokens", 0)) - int(before.get("total_tokens", 0))),
            "estimated_cost_usd": round(
                max(
                    0.0,
                    float(after.get("estimated_cost_usd", 0.0))
                    - float(before.get("estimated_cost_usd", 0.0)),
                ),
                6,
            ),
        }

    def _new_run_turn_diagnostics(self, *, max_iterations: int) -> Dict[str, Any]:
        return {
            "maxIterations": max(1, int(max_iterations)),
            "turnTransitions": [],
            "turnOrchestration": [],
            "compactionEvents": [],
            "promptLayers": {},
        }

    def _append_turn_transition(
        self,
        diagnostics: Optional[Dict[str, Any]],
        *,
        reason_code: str,
        iteration: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not diagnostics:
            return
        transitions = diagnostics.get("turnTransitions")
        if not isinstance(transitions, list):
            return
        payload: Dict[str, Any] = {
            "at": time.time(),
            "reasonCode": str(reason_code or "").strip() or "unspecified",
        }
        if iteration is not None:
            try:
                payload["iterationIndex"] = int(iteration)
            except (TypeError, ValueError):
                pass
        if details:
            payload["details"] = dict(details)
        transitions.append(payload)
        if len(transitions) > _MAX_RUN_TRANSITIONS:
            del transitions[:-_MAX_RUN_TRANSITIONS]

    def _append_turn_orchestration(
        self,
        diagnostics: Optional[Dict[str, Any]],
        *,
        iteration: int,
        call_count: int,
        concurrency_safe_count: int,
        sequential_count: int,
        max_parallel: int,
        plan_review: str,
        had_mutations: bool,
        auto_feedback_injected: bool,
        tool_names: List[str],
        tool_result_chars: int = 0,
        tool_result_chars_after_budget: int = 0,
        tool_result_budget_applied: bool = False,
        truncated_results: int = 0,
    ) -> None:
        if not diagnostics:
            return
        summaries = diagnostics.get("turnOrchestration")
        if not isinstance(summaries, list):
            return
        summaries.append(
            {
                "iterationIndex": max(0, int(iteration)),
                "callCount": max(0, int(call_count)),
                "concurrencySafeCount": max(0, int(concurrency_safe_count)),
                "sequentialCount": max(0, int(sequential_count)),
                "maxParallel": max(1, int(max_parallel)),
                "planReview": str(plan_review or "approved"),
                "hadMutations": bool(had_mutations),
                "autoFeedbackInjected": bool(auto_feedback_injected),
                "toolNames": [str(name) for name in tool_names if str(name).strip()],
                "toolResultChars": max(0, int(tool_result_chars)),
                "toolResultCharsAfterBudget": max(0, int(tool_result_chars_after_budget)),
                "toolResultBudgetApplied": bool(tool_result_budget_applied),
                "truncatedResultCount": max(0, int(truncated_results)),
            }
        )
        if len(summaries) > _MAX_RUN_TURN_SUMMARIES:
            del summaries[:-_MAX_RUN_TURN_SUMMARIES]

    @staticmethod
    def _extract_run_diagnostics(metadata: Any) -> Dict[str, Any]:
        payload = metadata if isinstance(metadata, dict) else {}
        transitions = payload.get("turnTransitions")
        if not isinstance(transitions, list):
            transitions = []
        orchestration = payload.get("turnOrchestration")
        if not isinstance(orchestration, list):
            orchestration = []
        compaction_events = payload.get("compactionEvents")
        if not isinstance(compaction_events, list):
            compaction_events = []
        prompt_layers = payload.get("promptLayers")
        if not isinstance(prompt_layers, dict):
            prompt_layers = {}
        return {
            "completionReasonCode": str(payload.get("completionReasonCode", "") or "").strip(),
            "turnTransitions": transitions,
            "turnOrchestration": orchestration,
            "compactionEvents": compaction_events,
            "promptLayers": prompt_layers,
            "maxIterations": int(payload.get("maxIterations", 0) or 0),
        }

    def _build_run_metadata_updates(
        self,
        *,
        request_id: str = "",
        diagnostics: Optional[Dict[str, Any]] = None,
        completion_reason_code: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        updates: Dict[str, Any] = {}
        if request_id:
            updates["requestId"] = request_id
        if diagnostics:
            transitions = diagnostics.get("turnTransitions")
            if isinstance(transitions, list):
                updates["turnTransitions"] = list(transitions)
            orchestration = diagnostics.get("turnOrchestration")
            if isinstance(orchestration, list):
                updates["turnOrchestration"] = list(orchestration)
            max_iterations = diagnostics.get("maxIterations")
            try:
                max_iterations_int = int(max_iterations)
            except (TypeError, ValueError):
                max_iterations_int = 0
            if max_iterations_int > 0:
                updates["maxIterations"] = max_iterations_int
            compaction_events = diagnostics.get("compactionEvents")
            if isinstance(compaction_events, list):
                updates["compactionEvents"] = list(compaction_events)
            prompt_layers = diagnostics.get("promptLayers")
            if isinstance(prompt_layers, dict):
                updates["promptLayers"] = dict(prompt_layers)
        if completion_reason_code:
            updates["completionReasonCode"] = str(completion_reason_code)
        if extra:
            updates.update(extra)
        return updates

    def _start_run_record(
        self,
        *,
        source_kind: str,
        source_id: str,
        artifact_dir: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._run_history:
            return None
        metadata = dict(metadata or {})
        retry_of_run_id = str(metadata.get("retryOfRunId", "")).strip() or None
        replay_of_run_id = str(metadata.get("replayOfRunId", "")).strip() or None
        record = self._run_history.start_run(
            source_kind=source_kind,
            source_id=source_id,
            artifact_dir=artifact_dir,
            metadata=metadata,
            retry_of_run_id=retry_of_run_id,
            replay_of_run_id=replay_of_run_id,
        )
        self._last_run_id = record.run_id
        return {"record": record, "cost_before": self.get_session_cost_summary()}

    def _finish_run_record(
        self,
        run_state: Optional[Dict[str, Any]],
        *,
        status: str,
        summary: str = "",
        error_message: str = "",
        checkpoint_id: Optional[str] = None,
        artifact_dir: str = "",
        metadata_updates: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not run_state or not self._run_history:
            return
        record = run_state["record"]
        cost_before = run_state["cost_before"]
        cost_after = self.get_session_cost_summary()
        self._run_history.finish_run(
            record.run_id,
            status=status,
            error_class=classify_error(error_message),
            artifact_dir=artifact_dir or record.artifact_dir,
            checkpoint_id=checkpoint_id,
            provider_summary=self._provider_summary(),
            cost_summary=self._cost_delta(cost_before, cost_after),
            summary=summary,
            metadata_updates=metadata_updates,
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

        # Resolve @mention context providers (@codebase, @diff, @terminal, @docs, @web)
        try:
            from .context_providers import resolve_mentions
            message, mention_blocks = await resolve_mentions(message, self)
            if mention_blocks:
                message = message + "\n\n" + "\n\n".join(mention_blocks)
        except Exception as e:
            logger.warning("context provider resolution failed: %s", e)

        # Inject git context for change-related queries
        git_keywords = {"commit", "change", "diff", "push", "merge", "rebase", "staged", "recent"}
        if any(kw in message.lower() for kw in git_keywords):
            git_ctx = self._git_context_summary_cached()
            if git_ctx:
                message = f"{message}\n\n[Git context]\n{git_ctx}"

        context_result = None
        if self._context_manager:
            await self._ensure_repo_graph() # wait briefly for background indexing
            context_result = await self._select_context_files(
                message=message,
                context_files=context_files,
                pinned_context_files=pinned_context_files,
                context_budget_tokens=context_budget_tokens,
            )
            if context_result is not None:
                referenced_files.extend(file_ctx.path for file_ctx in context_result.files)
                self._record_context_preview(
                    {
                        "selected": list(context_result.selected),
                        "excluded": list(context_result.excluded),
                        "totalTokens": context_result.total_tokens,
                        "truncated": context_result.truncated,
                        "message": context_result.message,
                        "budgetTokens": context_budget_tokens or getattr(self._context_manager, "max_tokens", 0),
                    }
                )
                # emit context selection summary
                n_sel = len(context_result.selected)
                n_exc = len(context_result.excluded)
                tokens = context_result.total_tokens
                trunc = " (truncated)" if context_result.truncated else ""
                # group by source
                sources: Dict[str, int] = {}
                for fc in context_result.files:
                    src = getattr(fc, "source", "auto")
                    sources[src] = sources.get(src, 0) + 1
                src_parts = ", ".join(f"{k}={v}" for k, v in sorted(sources.items()))
                self._pending_events.append(CoreEvent(
                    type="progress",
                    data={"phase": "context_selection", "message": f"context: {n_sel} files selected (~{tokens} tokens){trunc} [{src_parts}] | {n_exc} excluded"},
                ))

        skill_context = self._build_instruction_skill_context()
        skill_plan = SkillRegistry(
            getattr(self, "_repo_root", Path.cwd()),
            search_paths=self._configured_skill_search_paths(),
        ).build_instruction_plan(message, skill_context)
        instruction_snapshot = self._inspect_instruction_snapshot(
            referenced_files,
            user_prompt=message,
            skill_context=skill_context,
            skill_plan=skill_plan,
        )
        self._last_instruction_snapshot = instruction_snapshot
        self._last_instruction_skill_plan = skill_plan
        context_contract = getattr(self, "_context_contract", None)
        if context_contract:
            contract_snapshot = context_contract.build_snapshot(
                referenced_files=referenced_files,
                plan_mode_enabled=bool(self.config and self.config.plan_mode.enabled),
                instruction_snapshot=instruction_snapshot,
            )
            prompt_prefix = contract_snapshot.rendered_prompt_prefix
        else:
            prompt_prefix = instruction_snapshot.render_prompt_prefix()
        if self.provider:
            self.provider.update_prompt_prefix(prompt_prefix)

        # auto-surface relevant skills based on user prompt
        skill_hint = ""
        try:
            from .skill_surfacer import detect_relevant_skills, build_skill_hints
            _skill_reg = SkillRegistry(
                getattr(self, "_repo_root", Path.cwd()),
                search_paths=self._configured_skill_search_paths(),
            )
            _all_skills = _skill_reg.list_skills()
            _skill_names = [s.name for s in _all_skills]
            _matched = detect_relevant_skills(message, _skill_names)
            if _matched:
                _descs = {s.name: s.description for s in _all_skills}
                skill_hint = build_skill_hints(_matched, _descs) or ""
        except Exception:
            pass # skill surfacing is best-effort

        # inject agent todo list into context if non-empty
        todo_ctx = ""
        if self.tool_registry:
            todo_ctx = self.tool_registry.render_todos_for_context()
        if skill_hint:
            message = f"{skill_hint}\n\n{message}"
        if todo_ctx:
            message = f"{todo_ctx}\n\n{message}"

        if not self._context_manager or context_result is None or not context_result.files:
            return f"User request: {message}"

        logger.info(context_result.message)
        context_message = await self._context_manager.build_context_message(
            message,
            context_result,
            max_tokens=context_budget_tokens,
        )
        return context_message

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
        preview = await self._context_manager.preview_context(
            message=message,
            explicit_files=context_files or [],
            pinned_files=pinned_context_files or [],
            repo_root=str(Path.cwd()),
            max_tokens=context_budget_tokens,
            max_files=12,
        )
        self._record_context_preview(preview)
        return preview

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
        return self._inspect_tool_targets(tool_name, tool_args)

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

        try:
            decision = await self._permission_callback(tool_name, tool_args, preview)
        except TypeError:
            decision = await self._permission_callback(tool_name, tool_args)
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

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Rough cost estimation based on provider/model."""
        cost_per_1k_input = 0.0005  # conservative default
        cost_per_1k_output = 0.0015
        if self.config:
            provider = self.config.model.provider
            model = self.config.model.model_name
            from poor_cli.provider_catalog import get_model_tier
            tier = get_model_tier(provider, model)
            if tier:
                cost_per_1k_input = tier.cost_1k_in
                cost_per_1k_output = tier.cost_1k_out
            elif provider == "ollama":
                return 0.0
        return (input_tokens / 1000) * cost_per_1k_input + (output_tokens / 1000) * cost_per_1k_output

    def _track_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        """Accumulate session and per-task cost tracking."""
        est = self._estimate_cost(input_tokens, output_tokens)
        self._session_total_input_tokens += input_tokens
        self._session_total_output_tokens += output_tokens
        self._session_total_cost_usd += est
        self._session_cache_creation_input_tokens += cache_creation_input_tokens
        self._session_cache_read_input_tokens += cache_read_input_tokens
        if cache_read_input_tokens > 0:
            self._session_provider_cache_hits += 1
        elif input_tokens > 0 or cache_creation_input_tokens > 0:
            self._session_provider_cache_misses += 1
        if cache_read_input_tokens > 0:
            self._session_estimated_cache_savings_usd += self._estimate_cost(cache_read_input_tokens, 0)
        self._task_input_tokens += input_tokens
        self._task_output_tokens += output_tokens
        self._task_cost_usd += est

    def _check_cost_guardrails(self) -> Optional[str]:
        """Check if session or task cost/token limits are exceeded. Returns reason or None."""
        if not self.config:
            return None
        try:
            cg = self.config.cost_guardrails
            total_tokens = self._session_total_input_tokens + self._session_total_output_tokens
            max_tokens = getattr(cg, "session_max_tokens", 0) or 0
            max_cost = getattr(cg, "session_max_cost_usd", 0.0) or 0.0
            if max_tokens > 0 and total_tokens >= max_tokens:
                return f"Session token limit reached ({total_tokens}/{max_tokens})"
            if max_cost > 0 and self._session_total_cost_usd >= max_cost:
                return f"Session cost limit reached (${self._session_total_cost_usd:.4f}/${max_cost})"
            # per-task limits
            task_max = getattr(cg, "task_max_tokens", 0) or 0
            task_max_cost = getattr(cg, "task_max_cost_usd", 0.0) or 0.0
            task_tokens = self._task_input_tokens + self._task_output_tokens
            if task_max > 0 and task_tokens >= task_max:
                return f"Task token limit reached ({task_tokens}/{task_max})"
            if task_max_cost > 0 and self._task_cost_usd >= task_max_cost:
                return f"Task cost limit reached (${self._task_cost_usd:.4f}/${task_max_cost})"
        except (AttributeError, TypeError):
            pass
        return None

    def _check_cost_warning(self) -> Optional[str]:
        """Return warning message if approaching 80% of session limits, else None."""
        if not self.config or self._cost_warning_emitted:
            return None
        try:
            cg = self.config.cost_guardrails
            total_tokens = self._session_total_input_tokens + self._session_total_output_tokens
            max_tokens = getattr(cg, "session_max_tokens", 0) or 0
            max_cost = getattr(cg, "session_max_cost_usd", 0.0) or 0.0
            if max_tokens > 0 and total_tokens >= max_tokens * 0.8:
                self._cost_warning_emitted = True
                return f"Approaching session token limit ({total_tokens}/{max_tokens}, 80%)"
            if max_cost > 0 and self._session_total_cost_usd >= max_cost * 0.8:
                self._cost_warning_emitted = True
                return f"Approaching session cost limit (${self._session_total_cost_usd:.4f}/${max_cost}, 80%)"
        except (AttributeError, TypeError):
            pass
        return None

    def get_session_cost_summary(self) -> Dict[str, Any]:
        """Return current session cost/token totals."""
        input_tokens = getattr(self, "_session_total_input_tokens", 0)
        output_tokens = getattr(self, "_session_total_output_tokens", 0)
        cost_usd = getattr(self, "_session_total_cost_usd", 0.0)
        cache_create = getattr(self, "_session_cache_creation_input_tokens", 0)
        cache_read = getattr(self, "_session_cache_read_input_tokens", 0)
        cache_hits = getattr(self, "_session_provider_cache_hits", 0)
        cache_misses = getattr(self, "_session_provider_cache_misses", 0)
        cache_savings = getattr(self, "_session_estimated_cache_savings_usd", 0.0)
        total_requests = cache_hits + cache_misses
        hit_rate = round(cache_hits / total_requests * 100, 1) if total_requests else 0.0
        filter_stats = self.get_tool_filter_stats()
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated_cost_usd": round(cost_usd, 6),
            "tool_filtering": filter_stats,
            "tool_filtering_tokens_saved": filter_stats.get("tokens_saved", 0),
            "cache_creation_input_tokens": cache_create,
            "cache_read_input_tokens": cache_read,
            "cache_hit_count": cache_hits,
            "cache_miss_count": cache_misses,
            "cache_hit_rate_pct": hit_rate,
            "estimated_cache_savings_usd": round(cache_savings, 6),
            "request_count": total_requests,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
            "estimatedCost": round(cost_usd, 6),
            "toolFiltering": filter_stats,
            "toolFilteringTokensSaved": filter_stats.get("tokens_saved", 0),
            "cacheCreationInputTokens": cache_create,
            "cacheReadInputTokens": cache_read,
            "cacheHitCount": cache_hits,
            "cacheMissCount": cache_misses,
            "cacheHitRatePct": hit_rate,
            "estimatedCacheSavingsUSD": round(cache_savings, 6),
            "requestCount": total_requests,
        }

    def get_economy_savings(self) -> Dict[str, Any]:
        """Return accumulated economy savings summary."""
        tracker = getattr(self, "_economy_tracker", None)
        summary = tracker.get_summary() if tracker else {}
        sc = getattr(self, "_semantic_cache", None)
        if sc:
            summary["semantic_cache"] = sc.get_stats()
        return summary

    def get_budget_controller_stats(self) -> Dict[str, Any]:
        """Return token budget controller analytics."""
        stats = self._budget_controller.get_stats()
        stats["log_summary"] = self._budget_logger.summary()
        return stats

    def clear_semantic_cache(self) -> Dict[str, Any]:
        """Clear the semantic response cache."""
        if getattr(self, "_semantic_cache", None):
            removed = self._semantic_cache.invalidate_all()
            return {"cleared": removed}
        return {"cleared": 0, "note": "semantic cache not initialized"}

    def get_routing_stats(self) -> Dict[str, Any]:
        """Return model routing analytics."""
        if getattr(self, "_model_router", None):
            return self._model_router.get_routing_stats()
        return {"total_decisions": 0}

    def export_cost_report(self) -> Dict[str, Any]:
        """Export full session cost report for accounting."""
        return {
            "session": self.get_session_cost_summary(),
            "economy_savings": self._economy_tracker.get_summary() if getattr(self, "_economy_tracker", None) else {},
            "routing": self.get_routing_stats(),
            "tool_filtering": self.get_tool_filter_stats(),
            "context_breakdown": self.get_context_breakdown() if self.provider else {},
            "context_pressure": self.get_context_pressure() if self.provider else {},
            "cache_stats": self.get_cache_stats(),
            "model": {
                "provider": self.config.model.provider if self.config else "",
                "model_name": self.config.model.model_name if self.config else "",
                "economy_preset": self.config.economy.preset if self.config else "",
            },
        }

    def apply_budget_template(self, template_name: str) -> Dict[str, Any]:
        """Apply a named budget template to cost guardrails."""
        from .config import BUDGET_TEMPLATES
        values = BUDGET_TEMPLATES.get(template_name)
        if not values:
            return {"error": f"Unknown template. Available: {', '.join(BUDGET_TEMPLATES.keys())}"}
        if not self.config:
            return {"error": "not initialized"}
        for k, v in values.items():
            if hasattr(self.config.cost_guardrails, k):
                setattr(self.config.cost_guardrails, k, v)
        self._cost_warning_emitted = False # reset warning for new budget
        from dataclasses import asdict as _asdict
        return {"template": template_name, "guardrails": _asdict(self.config.cost_guardrails)}

    @staticmethod
    def list_budget_templates() -> Dict[str, Dict[str, Any]]:
        """Return all available budget templates."""
        from .config import BUDGET_TEMPLATES
        return dict(BUDGET_TEMPLATES)

    _COST_HISTORY_FILE = Path.home() / ".poor-cli" / "cost_history.json"

    def _persist_cost_history(self) -> None:
        """Append session cost summary to persistent cost history."""
        total = self._session_total_input_tokens + self._session_total_output_tokens
        if total == 0:
            return
        import datetime
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "provider": self.config.model.provider if self.config else "",
            "model": self.config.model.model_name if self.config else "",
            "input_tokens": self._session_total_input_tokens,
            "output_tokens": self._session_total_output_tokens,
            "cost_usd": round(self._session_total_cost_usd, 6),
            "cache_creation_input_tokens": self._session_cache_creation_input_tokens,
            "cache_read_input_tokens": self._session_cache_read_input_tokens,
            "cache_hit_count": self._session_provider_cache_hits,
            "cache_miss_count": self._session_provider_cache_misses,
            "estimated_cache_savings_usd": round(self._session_estimated_cache_savings_usd, 6),
            "economy_preset": self.config.economy.preset if self.config else "",
        }
        try:
            self._COST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            history: List[Dict[str, Any]] = []
            if self._COST_HISTORY_FILE.exists():
                history = json.loads(self._COST_HISTORY_FILE.read_text(encoding="utf-8"))
            history.append(entry)
            # keep last 500 entries
            if len(history) > 500:
                history = history[-500:]
            self._COST_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to persist cost history: %s", e)

    @staticmethod
    def get_cost_history(limit: int = 50) -> List[Dict[str, Any]]:
        """Load recent cost history entries."""
        path = Path.home() / ".poor-cli" / "cost_history.json"
        if not path.exists():
            return []
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            return history[-limit:]
        except Exception:
            return []

    def get_tokens_visualization(self, width: int = 50) -> Dict[str, Any]:
        """Return text-based context window bar chart."""
        bd = self.get_context_breakdown()
        total = bd.get("total_tokens", 0)
        max_ctx = bd.get("max_context_tokens", 1)
        free = max(0, max_ctx - total)
        def _bar(label: str, tokens: int) -> str:
            pct = tokens / max(max_ctx, 1)
            filled = max(1, int(pct * width)) if tokens > 0 else 0
            return f"[{label}: {'█' * filled}{' ' * (width - filled)}] {tokens:>7} tok ({pct*100:.1f}%)"
        bars = [
            _bar("sys ", bd.get("system_tokens", 0)),
            _bar("hist", bd.get("history_tokens", 0)),
            _bar("tool", bd.get("tool_result_tokens", 0)),
            _bar("free", free),
        ]
        return {"visualization": "\n".join(bars), "breakdown": bd}

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return tool cache + response cache + semantic cache stats."""
        tool_stats = self.tool_registry.get_tool_cache_stats() if self.tool_registry else {}
        provider_hits = getattr(self, "_session_provider_cache_hits", 0)
        provider_misses = getattr(self, "_session_provider_cache_misses", 0)
        provider_requests = provider_hits + provider_misses
        provider_hit_rate = round(provider_hits / provider_requests * 100, 1) if provider_requests else 0.0
        semantic_stats = self._semantic_cache.get_stats() if getattr(self, "_semantic_cache", None) else {}
        return {
            **tool_stats,
            "response_cache_entries": len(getattr(self, "_response_cache", {})),
            "response_cache_enabled": bool(self.config and self.config.economy.response_cache),
            "provider_cache_hits": provider_hits,
            "provider_cache_misses": provider_misses,
            "provider_cache_hit_rate_pct": provider_hit_rate,
            "provider_cache_creation_input_tokens": getattr(self, "_session_cache_creation_input_tokens", 0),
            "provider_cache_read_input_tokens": getattr(self, "_session_cache_read_input_tokens", 0),
            "provider_estimated_cache_savings_usd": round(
                getattr(self, "_session_estimated_cache_savings_usd", 0.0), 6
            ),
            "semantic_cache": semantic_stats,
            "file_cache": getattr(self, "_context_manager", None) and hasattr(self._context_manager, "_file_cache") and self._context_manager._file_cache.get_cache_info() or {},
        }

    def get_tool_filter_stats(self) -> Dict[str, int]:
        registry_stats = {}
        if self.tool_registry and hasattr(self.tool_registry, "get_output_filter_stats"):
            registry_stats = self.tool_registry.get_output_filter_stats()
        mcp_stats = {}
        mcp_manager = getattr(self, "_mcp_manager", None)
        if mcp_manager and hasattr(mcp_manager, "get_output_filter_stats"):
            mcp_stats = mcp_manager.get_output_filter_stats()
        return merge_filter_stats(registry_stats, mcp_stats)

    def get_context_pressure(self) -> Dict[str, Any]:
        """Return context window utilization metrics."""
        if not self.provider:
            return {"used_tokens": 0, "max_tokens": 0, "pressure_pct": 0, "strategy_hint": "ok"}
        cpt = self._cpt
        caps = self.provider.get_capabilities()
        max_ctx = caps.max_context_tokens
        try:
            history = self.provider.get_history()
            used = int(sum(len(str(m.get("content", ""))) for m in history) / cpt)
        except Exception:
            used = 0
        sys_tokens = self._static_prefix_tokens()
        total = used + sys_tokens
        pct = round(total / max(max_ctx, 1) * 100, 1)
        hint = "compress" if pct > 70 else ("warn" if pct > 50 else "ok")
        return {"used_tokens": total, "max_tokens": max_ctx, "pressure_pct": pct, "strategy_hint": hint}

    def get_context_breakdown(self) -> Dict[str, Any]:
        """Return token breakdown by category: system, history, tool results."""
        cpt = self._cpt
        sys_tokens = self._static_prefix_tokens()
        if not self.provider:
            return {"system_tokens": sys_tokens, "history_tokens": 0, "tool_result_tokens": 0,
                    "total_tokens": sys_tokens, "max_context_tokens": 0, "pressure_pct": 0, "turn_count": 0}
        try:
            history = self.provider.get_history()
        except Exception:
            history = []
        hist_tokens = 0
        tool_tokens = 0
        user_turns = 0
        for m in history:
            toks = int(len(str(m.get("content", ""))) / cpt)
            if m.get("role") in ("tool", "function"):
                tool_tokens += toks
            else:
                hist_tokens += toks
            if m.get("role") == "user":
                user_turns += 1
        caps = self.provider.get_capabilities()
        max_ctx = caps.max_context_tokens
        total = sys_tokens + hist_tokens + tool_tokens
        return {"system_tokens": sys_tokens, "history_tokens": hist_tokens,
                "tool_result_tokens": tool_tokens, "total_tokens": total,
                "max_context_tokens": max_ctx,
                "pressure_pct": round(total / max(max_ctx, 1) * 100, 1) if max_ctx else 0,
                "turn_count": user_turns}

    def get_compaction_status(self) -> Dict[str, Any]:
        payload = dict(getattr(self, "_last_compaction_status", {}) or {})
        if not payload:
            payload = {"state": "idle"}
        task = getattr(self, "_auto_history_compact_task", None)
        payload["backgroundActive"] = bool(task and not task.done())
        return payload

    def estimate_cost(self, message: str) -> Dict[str, Any]:
        """Estimate token cost of a message before sending (no API call)."""
        cpt = self._cpt
        sys_tokens = self._static_prefix_tokens()
        if self.provider:
            try:
                history = self.provider.get_history()
                hist_tokens = int(sum(len(str(m.get("content", ""))) for m in history) / cpt)
            except Exception:
                hist_tokens = 0
        else:
            hist_tokens = 0
        prompt_tokens = int(len(message) / cpt)
        total_input = sys_tokens + hist_tokens + prompt_tokens
        est_output = min(total_input, 4000)
        cost = self._estimate_cost(total_input, est_output)
        caps = self.provider.get_capabilities() if self.provider else None
        max_ctx = caps.max_context_tokens if caps else 0
        return {"estimated_input_tokens": total_input, "estimated_output_tokens": est_output,
                "estimated_cost_usd": round(cost, 6),
                "context_pressure_after_pct": round(total_input / max(max_ctx, 1) * 100, 1) if max_ctx else 0,
                "breakdown": {"system": sys_tokens, "history": hist_tokens, "prompt": prompt_tokens}}

    def compare_model_cost(self, target_provider: str, target_model: str) -> Dict[str, Any]:
        """Compare cost between current model and a target model."""
        if not self.config:
            return {"error": "not initialized"}
        from .provider_catalog import get_model_tier
        current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
        target_tier = get_model_tier(target_provider, target_model)
        if not current_tier or not target_tier:
            return {"error": "model tier not found in catalog"}
        ratio_in = target_tier.cost_1k_in / max(current_tier.cost_1k_in, 0.0001)
        ratio_out = target_tier.cost_1k_out / max(current_tier.cost_1k_out, 0.0001)
        proj_target = (self._session_total_input_tokens / 1000 * target_tier.cost_1k_in +
                       self._session_total_output_tokens / 1000 * target_tier.cost_1k_out)
        return {
            "current": {"provider": self.config.model.provider, "model": self.config.model.model_name,
                        "cost_1k_in": current_tier.cost_1k_in, "cost_1k_out": current_tier.cost_1k_out},
            "target": {"provider": target_provider, "model": target_model,
                       "cost_1k_in": target_tier.cost_1k_in, "cost_1k_out": target_tier.cost_1k_out},
            "input_cost_ratio": round(ratio_in, 2), "output_cost_ratio": round(ratio_out, 2),
            "session_cost_current_usd": round(self._session_total_cost_usd, 6),
            "session_cost_if_target_usd": round(proj_target, 6),
        }

    def set_economy_preset(self, preset: str) -> Dict[str, Any]:
        """Switch economy preset. Regenerates system instruction if verbosity/batched flags changed."""
        if not self.config:
            return {"error": "not initialized"}
        from dataclasses import asdict as _asdict
        old_verbosity = resolve_output_verbosity(self.config.economy)
        old_batched = self.config.economy.prefer_batched_reads
        apply_economy_preset(self.config.economy, preset)
        new_verbosity = resolve_output_verbosity(self.config.economy)
        new_batched = self.config.economy.prefer_batched_reads
        if (new_verbosity != old_verbosity or new_batched != old_batched) and self.provider:
            _sandbox_preset = getattr(self.config.sandbox, "default_preset", "workspace-write")
            _plan = bool(self.config.plan_mode.enabled)
            _max_sys = 1000 if self.config.model.provider == "ollama" else 0
            self._system_instruction = build_tool_calling_system_instruction(
                str(Path.cwd()), provider=self.config.model.provider,
                terse_mode=new_verbosity == "caveman", batched_reads=new_batched,
                sandbox_preset=_sandbox_preset, plan_mode=_plan,
                include_agent_tools=not _plan, max_system_tokens=_max_sys,
            )
        return _asdict(self.config.economy)

    def _maybe_apply_vision(self, message: str) -> Any:
        """Detect image paths and convert to multimodal payload if provider supports vision."""
        if not self.provider:
            return message
        caps = self.provider.get_capabilities()
        if not caps or not caps.supports_vision:
            return message
        images = detect_image_paths(message)
        if not images:
            return message
        provider_name = (self.config.model.provider if self.config else "").lower()
        if "anthropic" in provider_name or "claude" in provider_name:
            return build_multimodal_content_anthropic(message, images)
        elif "gemini" in provider_name or "google" in provider_name:
            return build_multimodal_parts_gemini(message, images)
        elif "openai" in provider_name or "gpt" in provider_name:
            return build_multimodal_content_openai(message, images)
        return message # fallback: send as plain text

    def _maybe_downshift_model(self, prompt: str) -> None:
        """Switch to a cheaper model for simple prompts or when approaching budget limit."""
        if not self.config or not self.provider:
            return
        eco = self.config.economy
        # budget-aware forced downshift: switch to cheapest regardless of complexity
        budget_pct = getattr(eco, "budget_downshift_pct", 0)
        if budget_pct > 0:
            cg = self.config.cost_guardrails
            max_cost = getattr(cg, "session_max_cost_usd", 0.0) or 0.0
            if max_cost > 0 and self._session_total_cost_usd >= max_cost * (budget_pct / 100):
                from .provider_catalog import get_downshift_model, get_model_tier
                result = get_downshift_model(self.config.model.provider)
                if result:
                    cheap_model_name, cheap_tier = result
                    if cheap_model_name != self.config.model.model_name:
                        current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
                        self._original_model_name = self.config.model.model_name
                        self._downshifted = True
                        self._turn_economy.downshifted = True
                        self._turn_economy.downshift_model = cheap_model_name
                        self.provider.switch_model(cheap_model_name)
                        if current_tier:
                            self._economy_tracker.record_downshift(
                                current_tier.cost_1k_in + current_tier.cost_1k_out,
                                cheap_tier.cost_1k_in + cheap_tier.cost_1k_out,
                            )
                        logger.info("Budget-aware downshift to %s (%.0f%% of budget used)", cheap_model_name, budget_pct)
                        return
        # use model router if available
        if self._model_router and self._model_router.enabled:
            decision = self._model_router.select_model(
                prompt=prompt,
                provider=self.config.model.provider,
                current_model=self.config.model.model_name,
                economy_preset=eco.preset,
                user_explicit_model=self._user_explicit_model,
            )
            self._economy_tracker.record_routing_decision(escalated=decision.escalated)
            self._turn_economy.routed = True
            self._turn_economy.routed_model = decision.selected_model
            self._turn_economy.routed_complexity = decision.complexity.value
            if decision.selected_model != self.config.model.model_name:
                from .provider_catalog import get_model_tier
                current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
                self._original_model_name = self.config.model.model_name
                self._downshifted = True
                self._turn_economy.downshifted = True
                self._turn_economy.downshift_model = decision.selected_model
                self.provider.switch_model(decision.selected_model)
                if current_tier:
                    new_tier = get_model_tier(self.config.model.provider, decision.selected_model)
                    if new_tier:
                        self._economy_tracker.record_downshift(
                            current_tier.cost_1k_in + current_tier.cost_1k_out,
                            new_tier.cost_1k_in + new_tier.cost_1k_out,
                        )
            return
        # fallback: legacy auto_downshift
        if not eco.auto_downshift:
            return
        if len(prompt) >= eco.downshift_threshold_chars:
            return
        if eco.downshift_exclude_tools:
            complexity = classify_prompt_complexity(prompt)
            if complexity != "simple":
                return
        from .provider_catalog import get_downshift_model, get_model_tier
        result = get_downshift_model(self.config.model.provider)
        if not result:
            return
        cheap_model_name, cheap_tier = result
        if cheap_model_name == self.config.model.model_name:
            return # already on cheapest
        current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
        self._original_model_name = self.config.model.model_name
        self._downshifted = True
        self._turn_economy.downshifted = True
        self._turn_economy.downshift_model = cheap_model_name
        self.provider.switch_model(cheap_model_name)
        if current_tier:
            self._economy_tracker.record_downshift(
                current_tier.cost_1k_in + current_tier.cost_1k_out,
                cheap_tier.cost_1k_in + cheap_tier.cost_1k_out,
            )

    def _restore_model(self) -> None:
        """Restore original model after a downshift."""
        if self._downshifted and self._original_model_name and self.provider:
            self.provider.switch_model(self._original_model_name)
            self._original_model_name = None
            self._downshifted = False

    # ── Economy: response cache ───────────────────────────────────────

    def _cache_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()

    def _cache_lookup(self, prompt: str) -> Optional[str]:
        """Return cached response if valid (exact match only), else None."""
        if not self.config or not self.config.economy.response_cache:
            return None
        key = self._cache_key(prompt)
        entry = self._response_cache.get(key)
        if entry is None:
            return None
        cached_text, ts = entry
        ttl = self.config.economy.response_cache_ttl
        if time.monotonic() - ts > ttl:
            del self._response_cache[key]
            return None
        return cached_text

    async def _semantic_cache_lookup(self, prompt: str, context_hash: str) -> Optional[str]:
        """Try semantic similarity cache. Returns cached response or None."""
        if self._prompt_likely_needs_tools(prompt):
            return None
        try:
            if self._semantic_cache is None:
                self._semantic_cache = get_semantic_cache()
            result = await self._semantic_cache.get(prompt, context_hash)
            if result:
                self._semantic_cache.record_savings(result.response)
                logger.info("semantic cache hit (sim=%.4f)", result.similarity)
                return result.response
        except Exception as e:
            logger.warning("semantic cache lookup failed: %s", e)
        return None

    async def _semantic_cache_store(self, prompt: str, context_hash: str, response: str) -> None:
        """Store response in semantic cache."""
        if self._prompt_likely_needs_tools(prompt):
            return
        try:
            if self._semantic_cache is None:
                self._semantic_cache = get_semantic_cache()
            model = self.provider.model_name if self.provider else ""
            await self._semantic_cache.put(prompt, context_hash, response, model_name=model)
        except Exception as e:
            logger.warning("semantic cache store failed: %s", e)

    def _cache_store(self, prompt: str, response: str) -> None:
        if not self.config or not self.config.economy.response_cache:
            return
        if self._prompt_likely_needs_tools(prompt): # skip caching mutation-likely prompts
            return
        key = self._cache_key(prompt)
        self._response_cache[key] = (response, time.monotonic())

    @staticmethod
    def _prompt_likely_needs_tools(prompt: str) -> bool:
        """Heuristic: return True if prompt likely triggers tool calls (unsafe to cache).

        Uses classify_prompt_complexity instead of raw keyword matching to avoid
        false positives on explanatory prompts like "what does the write function do?"
        """
        complexity = classify_prompt_complexity(prompt)
        return complexity != "simple"

    # ── Economy: context dedup ────────────────────────────────────────

    def _dedup_context_files(self, context_text: str) -> Tuple[str, int]:
        """Remove file content blocks already seen this session. Returns (deduped, tokens_saved)."""
        if not self.config or not (self.config.economy.context_dedup or self.config.economy.dedup_context):
            return context_text, 0
        lines = context_text.split("\n")
        output_lines: List[str] = []
        skipping = False
        current_path = ""
        tokens_saved = 0
        for line in lines:
            if line.startswith("--- file: ") or line.startswith("File: "):
                path = line.split(": ", 1)[-1].strip()
                content_hash = hashlib.md5(line.encode()).hexdigest()
                if path in self._files_seen_in_session and self._files_seen_in_session[path] == content_hash:
                    skipping = True
                    current_path = path
                    output_lines.append(f"{line} [already in context, skipped]")
                    continue
                else:
                    self._files_seen_in_session[path] = content_hash
                    skipping = False
            if skipping:
                tokens_saved += len(line) // 4
                continue
            output_lines.append(line)
        return "\n".join(output_lines), tokens_saved

    # ── Economy: diff-only reads ──────────────────────────────────────

    def _apply_diff_only_read(self, tool_name: str, tool_args: Dict[str, Any], result: str) -> str:
        """For read_file results, return only changed lines vs last read if diff_only_reads enabled."""
        if not self.config or not self.config.economy.diff_only_reads:
            return result
        if tool_name != "read_file":
            return result
        path = tool_args.get("file_path", "")
        if not path:
            return result
        previous = self._last_file_contents.get(path)
        self._last_file_contents[path] = result
        if previous is None:
            return result # first read — return full
        if previous == result:
            return f"[unchanged since last read: {path}]"
        diff = difflib.unified_diff(
            previous.splitlines(keepends=True),
            result.splitlines(keepends=True),
            fromfile=f"{path} (previous)",
            tofile=f"{path} (current)",
            n=3,
        )
        diff_text = "".join(diff)
        if not diff_text:
            return f"[unchanged since last read: {path}]"
        return f"[diff-only read: {path}]\n{diff_text}"

    # ── Economy: idle auto-compact ────────────────────────────────────

    def _reset_idle_compact_timer(self) -> None:
        """Reset the idle auto-compact timer."""
        if not self.config:
            return
        seconds = self.config.economy.idle_compact_seconds
        if seconds <= 0:
            return
        # cancel existing timer
        if self._idle_compact_task is not None:
            self._idle_compact_task.cancel()
            self._idle_compact_task = None
        try:
            loop = asyncio.get_running_loop()
            self._idle_loop = loop
            self._idle_compact_task = loop.call_later(seconds, self._idle_compact_fire)
        except RuntimeError:
            pass # no running loop

    def _idle_compact_fire(self) -> None:
        """Fired when idle timer expires — schedule compression."""
        if self._idle_loop is None or not self.provider:
            return
        async def _do_compact():
            try:
                cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
                if not cc_cfg or not getattr(cc_cfg, "enabled", False):
                    return
                history = self.provider.get_history()
                if len(history) <= 2:
                    return
                if self._context_compressor.should_compress(history, cc_cfg):
                    before = len(history)
                    compressed = self._context_compressor.compress(history, cc_cfg)
                    self.provider.set_history(compressed)
                    after = len(compressed)
                    logger.info("Idle auto-compact: %d -> %d messages", before, after)
            except Exception:
                pass
        self._idle_loop.create_task(_do_compact())

    # ── Economy: economy_max_tokens ───────────────────────────────────

    def _apply_economy_max_tokens(self) -> None:
        """Set economy output token cap on the provider if configured."""
        if not self.config or not self.provider:
            return
        cap = self.config.economy.economy_max_tokens
        if cap > 0:
            self.provider.economy_max_output_tokens = cap
        else:
            self.provider.economy_max_output_tokens = 0

    def _git_context_summary_cached(self) -> str:
        """Return git context, reusing cache when git state unchanged."""
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True, timeout=3,
            ).strip()
        except Exception:
            head = ""
        try:
            status = subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True, timeout=3,
            ).strip()[:500]
        except Exception:
            status = ""
        git_hash = hashlib.sha256(f"{head}|{status}".encode()).hexdigest()
        if self._git_context_cache and self._git_context_cache[0] == git_hash:
            return self._git_context_cache[1]
        text = self._git_context_summary()
        self._git_context_cache = (git_hash, text)
        return text

    @staticmethod
    def _git_context_summary() -> str:
        """Build git-aware context (staged diff + recent commits) for injection."""
        parts = []
        try:
            staged = subprocess.check_output(
                ["git", "diff", "--cached", "--stat"], stderr=subprocess.DEVNULL, text=True, timeout=5,
            ).strip()
            if staged:
                parts.append(f"Staged changes:\n{staged}")
        except Exception:
            pass
        try:
            log = subprocess.check_output(
                ["git", "log", "--oneline", "-5"], stderr=subprocess.DEVNULL, text=True, timeout=5,
            ).strip()
            if log:
                parts.append(f"Recent commits:\n{log}")
        except Exception:
            pass
        return "\n\n".join(parts)

    def _ensure_working_memory_mgr(self) -> Any:
        """Lazy-init WorkingMemoryManager."""
        if self._working_memory_mgr is not None:
            return self._working_memory_mgr
        try:
            from .working_memory import WorkingMemoryManager
            caps = self.provider.get_capabilities() if self.provider else None
            max_ctx = int(caps.max_context_tokens) if caps and caps.max_context_tokens else 100_000
            self._working_memory_mgr = WorkingMemoryManager(
                repo_root=getattr(self, "_repo_root", Path.cwd()),
                max_context_tokens=max_ctx,
            )
            self._working_memory_mgr.init_session()
        except Exception as e:
            logger.warning("working memory init failed: %s", e)
            self._working_memory_mgr = None
        return self._working_memory_mgr

    async def _ensure_repo_graph(self, timeout: float = 0.1) -> None:
        """Wait briefly for background repo graph indexing to complete."""
        if self._repo_graph_task and not self._repo_graph_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._repo_graph_task), timeout=timeout)
            except (asyncio.TimeoutError, Exception):
                pass # graph not ready yet, proceed without it

    async def _maybe_builtin_workspace_map(self, message: str) -> Optional[str]:
        stripped = str(message or "").strip()
        if not stripped.startswith("/workspace-map"):
            return None
        token_budget = 2000
        suffix = stripped[len("/workspace-map"):].strip()
        if suffix:
            try:
                token_budget = max(128, int(suffix.split()[0]))
            except ValueError:
                pass
        if self._repo_graph is None:
            return "[workspace-map unavailable: repo graph disabled]"
        await self._ensure_repo_graph(timeout=5.0)
        try:
            stats = self._repo_graph.get_stats()
        except Exception:
            stats = {"files": 0}
        if not stats.get("files"):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._repo_graph.build_index)
        return self._repo_graph.build_repo_map(token_budget=token_budget)

    @property
    def _cpt(self) -> float:
        """Chars-per-token ratio for current provider."""
        provider = self.config.model.provider if self.config else ""
        return chars_per_token(provider)

    def _static_prefix_tokens(self) -> int:
        """Estimate tokens consumed by stable provider prefix content."""
        cpt = self._cpt
        prefix = ""
        if self.provider and hasattr(self.provider, "get_prompt_prefix"):
            try:
                prefix = self.provider.get_prompt_prefix() or ""
            except Exception:
                prefix = ""
        return int((len(getattr(self, "_system_instruction", None) or "") + len(prefix)) / cpt)

    def _compute_token_breakdown(self) -> Tuple[int, int, int]:
        """Compute (system_tokens, history_tokens, tool_result_tokens) for current state."""
        cpt = self._cpt
        sys_tok = self._static_prefix_tokens()
        hist_tok = 0
        tool_tok = 0
        if self.provider:
            try:
                for m in self.provider.get_history():
                    toks = int(len(str(m.get("content", ""))) / cpt)
                    if m.get("role") in ("tool", "function"):
                        tool_tok += toks
                    else:
                        hist_tok += toks
            except Exception:
                pass
        return sys_tok, hist_tok, tool_tok

    def _check_context_pressure(self) -> Optional[str]:
        """Check if context window is under pressure. Returns reason string or None."""
        if not self.provider or not self.config:
            return None
        caps = self.provider.get_capabilities()
        max_ctx = caps.max_context_tokens
        if max_ctx <= 0:
            return None
        try:
            history = self.provider.get_history()
            current_tokens = int(sum(len(str(m.get("content", ""))) for m in history) / self._cpt)
        except Exception:
            return None
        current_tokens += self._static_prefix_tokens()
        remaining_ratio = max(0.0, 1.0 - (current_tokens / max_ctx))
        stop_ratio = getattr(self.config.agentic, "context_pressure_stop_ratio", 0.2)
        warn_ratio = getattr(self.config.agentic, "context_pressure_warn_ratio", 0.5)
        if remaining_ratio < stop_ratio:
            return "context_pressure"
        if remaining_ratio < warn_ratio:
            logger.warning("Context pressure: %.0f%% remaining (warn threshold %.0f%%)", remaining_ratio * 100, warn_ratio * 100)
        return None

    async def _auto_compress_on_pressure(self) -> Optional[str]:
        """Auto-compress if context pressure exceeds economy threshold. Returns strategy used or None."""
        if not self.config or not self.provider:
            return None
        threshold = getattr(self.config.economy, "auto_compress_pressure_pct", 0)
        if not threshold or threshold <= 0:
            return None
        pressure = self.get_context_pressure()
        if pressure["pressure_pct"] < threshold:
            return None
        cc_cfg = getattr(self.config, "context_compression", None)
        if not cc_cfg or not getattr(cc_cfg, "enabled", False):
            return None
        history = self.provider.get_history()
        if len(history) <= 4:
            return None
        _strip_chars = getattr(self.config.economy, "tool_strip_chars", 200)
        compressed = await self._context_compressor.compress_auto(
            history, cc_cfg, provider=self.provider, tool_strip_chars=_strip_chars,
        )
        if len(compressed) < len(history):
            self.provider.set_history(compressed)
            logger.info("Auto-compress on pressure (%.1f%%): %d -> %d messages",
                        pressure["pressure_pct"], len(history), len(compressed))
            return "auto_pressure"
        return None

    def _refresh_system_context(self) -> bool:
        """Rebuild system instruction if git/instruction state changed. Returns True if updated."""
        if not self._initialized or not self.provider or not self.config:
            return False
        terse = resolve_output_verbosity(self.config.economy) == "caveman"
        batched = getattr(self.config.economy, "prefer_batched_reads", False)
        repo_root = getattr(self, "_repo_root", Path.cwd())
        _sandbox_preset = getattr(self.config.sandbox, "default_preset", "workspace-write")
        _plan = bool(self.config.plan_mode.enabled)
        new_instruction = build_tool_calling_system_instruction(
            str(repo_root), provider=self.config.model.provider,
            terse_mode=terse, batched_reads=batched,
            sandbox_preset=_sandbox_preset,
            plan_mode=_plan,
            include_gh_tools=getattr(self.config.tools, "enable_git_tools", True),
            include_agent_tools=not _plan,
        )
        memory_index = self._memory_manager.load_index() if self._memory_manager else ""
        if memory_index:
            new_instruction += (
                "\n\n## Persistent Memory\n"
                "The following memories were saved in previous sessions.\n\n"
                f"{memory_index}\n"
            )
        try:
            if self._memory_manager:
                _user_memories = self._memory_manager.list_all(type_filter="user")
                _user_content = "\n".join(m.content for m in _user_memories)
                _tone = detect_tone_from_user_memories(_user_content)
                if _tone:
                    new_instruction += _tone
        except Exception:
            pass
        new_hash = hashlib.sha256(new_instruction.encode("utf-8", errors="replace")).hexdigest()
        if new_hash == self._system_context_hash:
            return False
        self._git_context_cache = None # git state changed, invalidate
        self._system_instruction = new_instruction
        self.provider.update_system_instruction(self._system_instruction)
        self._system_context_hash = new_hash
        context_contract = getattr(self, "_context_contract", None)
        if context_contract:
            context_contract.invalidate_cache()
        logger.debug("System context refreshed (hash=%s)", new_hash[:12])
        return True

    async def send_message_events(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        request_id: str = "",
        source_kind: str = "session",
        source_id: str = "",
        artifact_dir: str = "",
        run_metadata: Optional[Dict[str, Any]] = None,
        max_response_tokens: Optional[int] = None,
    ) -> AsyncIterator[CoreEvent]:
        """
        Send a message and yield CoreEvent objects (structured agentic events).

        This is the primary method for streaming clients. It yields tool_call_start,
        tool_result, text_chunk, cost_update, progress, and done events.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        self._turn_tool_cache.clear() # reset per-turn read-only tool cache
        self._task_input_tokens = 0 # reset per-task counters
        self._task_output_tokens = 0
        self._task_cost_usd = 0.0
        self._turn_economy = EconomyTurnReport()
        # per-turn output token cap
        _saved_max_output = None
        if max_response_tokens and max_response_tokens > 0 and self.provider:
            _saved_max_output = getattr(self.provider, "economy_max_output_tokens", 0)
            self.provider.economy_max_output_tokens = max_response_tokens
        self._refresh_system_context()

        # Check cost guardrails before processing
        cost_reason = self._check_cost_guardrails()
        if cost_reason:
            yield CoreEvent.text_chunk(f"[Cost guardrail] {cost_reason}", request_id)
            yield CoreEvent.done(reason="cost_limit")
            return

        cancel_event = self._prepare_cancel_event(request_id)
        max_iterations = self.config.agentic.max_iterations if self.config else 25
        iteration = 0
        if self._context_manager:
            self._context_manager.advance_turn()
        turn_diagnostics = self._new_run_turn_diagnostics(max_iterations=max_iterations)
        resolved_source_id = str(source_id or request_id or "session").strip() or "session"
        self._append_turn_transition(
            turn_diagnostics,
            reason_code="run_started",
            iteration=0,
            details={
                "sourceKind": source_kind,
                "sourceId": resolved_source_id,
            },
        )
        run_state = self._start_run_record(
            source_kind=source_kind,
            source_id=resolved_source_id,
            artifact_dir=artifact_dir,
            metadata=run_metadata,
        )
        last_checkpoint_id: Optional[str] = None

        logger.info(f"Sending message (events): {message[:100]}...")
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            request_id=request_id,
        )
        builtin_workspace_map = await self._maybe_builtin_workspace_map(message)
        if builtin_workspace_map is not None:
            if self.history_adapter:
                self.history_adapter.add_message("user", message)
                self.history_adapter.add_message("model", builtin_workspace_map)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="builtin_command",
                iteration=0,
                details={"command": "/workspace-map"},
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=builtin_workspace_map or "workspace map",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="builtin_command",
                ),
            )
            yield CoreEvent.text_chunk(builtin_workspace_map, request_id)
            yield CoreEvent.done(reason="builtin_command")
            return
        full_message = await self._build_context_message(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        await self._activate_tools_for_prompt(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
        )
        turn_diagnostics["promptLayers"] = {
            "userPromptChars": len(message or ""),
            "fullMessageChars": len(full_message or ""),
            "explicitContextFileCount": len(context_files or []),
            "pinnedContextFileCount": len(pinned_context_files or []),
            "selectedContextFileCount": len(
                (self._last_context_preview.get("selected") if isinstance(self._last_context_preview, dict) else [])
                or []
            ),
            "gitContextInjected": "[Git context]" in (full_message or ""),
        }

        # Economy: context dedup — strip file blocks already in session
        try:
            if self.config and (self.config.economy.context_dedup or self.config.economy.dedup_context):
                full_message, dedup_saved = self._dedup_context_files(full_message)
                if dedup_saved > 0:
                    self._economy_tracker.record_dedup(dedup_saved)
                    self._turn_economy.dedup_tokens_saved += dedup_saved
        except (AttributeError, TypeError) as e:
            logger.warning("economy context_dedup failed: %s", e)

        # Economy: prompt distillation
        try:
            eco = self.config.economy if self.config else None
            if eco and eco.prompt_distill:
                tokens_before = len(full_message) // 4
                full_message, tokens_saved = distill_prompt(full_message, "", eco)
                if tokens_saved > 0:
                    self._economy_tracker.record_distillation(tokens_before, tokens_before - tokens_saved)
                    self._turn_economy.distillation_tokens_saved += tokens_saved
        except (AttributeError, TypeError) as e:
            logger.warning("economy prompt_distill failed: %s", e)

        # Economy: smart model downshift for simple prompts
        try:
            self._maybe_downshift_model(message)
        except Exception as e:
            logger.warning("economy model_downshift failed: %s", e)

        # Economy: apply output token cap
        try:
            self._apply_economy_max_tokens()
        except Exception as e:
            logger.warning("economy max_tokens cap failed: %s", e)

        # Token budget controller: observe state and decide action
        self._turn_start_mono = time.monotonic()
        self._turn_tool_call_count = 0
        try:
            eco = self.config.economy if self.config else None
            preset = eco.preset if eco else "balanced"
            cp = self.get_context_pressure() if self.provider else {}
            complexity_str = self._turn_economy.routed_complexity or "simple"
            recent_5 = self._recent_turn_failures[-5:]
            recent_fails = sum(1 for f in recent_5 if f)
            self._budget_state = build_state_from_engine(
                complexity_str=complexity_str,
                context_pressure_pct=float(cp.get("pressure_pct", 0)),
                turn_number=iteration,
                economy_preset=preset,
                provider=self.config.model.provider if self.config else "",
                model_tier=self._turn_economy.routed_model or "balanced",
                recent_failures=recent_fails,
                recent_turns=max(len(recent_5), 1),
            )
            self._budget_action = self._budget_controller.decide(self._budget_state)
            # apply data-driven thinking budget override
            try:
                self._budget_action = self._thinking_optimizer.suggest_action_override(
                    self._budget_state, self._budget_action
                )
            except Exception as e:
                logger.warning("thinking_optimizer override failed: %s", e)
            # wire thinking budget to provider
            if self.provider:
                self.provider.economy_max_thinking_tokens = self._budget_action.max_thinking_tokens
            logger.info(
                "budget_controller: tier=%s thinking=%d output=%d compress=%.2f compact=%s",
                self._budget_action.model_tier,
                self._budget_action.max_thinking_tokens,
                self._budget_action.max_output_tokens,
                self._budget_action.compression_ratio,
                self._budget_action.should_compact,
            )
        except Exception as e:
            logger.warning("budget controller decide failed: %s", e)
            self._budget_state = None
            self._budget_action = None

        # Economy: reset idle auto-compact timer
        try:
            self._reset_idle_compact_timer()
        except Exception as e:
            logger.warning("economy idle_compact_timer failed: %s", e)

        # Working memory: delta-mode substitution
        try:
            wm_mgr = self._ensure_working_memory_mgr()
            if wm_mgr and wm_mgr.memory is not None:
                history_tokens = len(full_message) // 4
                active_files: Dict[str, str] = {}
                if self._context_manager:
                    for fc in getattr(self._context_manager, "_last_selected_files", []):
                        p = getattr(fc, "path", None)
                        c = getattr(fc, "content", None)
                        if p and c:
                            active_files[str(p)] = c
                tool_results = getattr(self, "_last_tool_results", None)
                caps = self.provider.get_capabilities() if self.provider else None
                max_ctx = int(caps.max_context_tokens) if caps and caps.max_context_tokens else 100_000
                pressure = history_tokens / max_ctx if max_ctx > 0 else 0.0
                delta_prompt, wm_metrics = wm_mgr.pre_turn(
                    user_message=message,
                    current_files=active_files,
                    context_pressure=pressure,
                    full_history_tokens=history_tokens,
                    tool_results=tool_results,
                )
                if delta_prompt: # delta mode active — substitute prompt
                    full_message = delta_prompt
                    self._pending_events.append(CoreEvent(
                        type="progress",
                        data={
                            "phase": "working_memory",
                            "message": f"delta mode: ~{wm_metrics.tokens_saved} tokens saved ({wm_metrics.savings_pct:.0f}%)",
                        },
                    ))
        except Exception as e:
            logger.warning("working memory pre-turn failed: %s", e)

        # Economy: compute context hash for semantic cache keying
        # PRD 004: fold in system-prompt and tool-schema fingerprints so edits
        # to either invalidate previously-cached answers.
        tool_schema_hash = None
        try:
            decls = getattr(self, "_active_tool_declarations", None)
            if decls:
                tool_schema_hash = hashlib.sha256(
                    json.dumps(decls, sort_keys=True, default=str).encode("utf-8", errors="replace")
                ).hexdigest()
        except Exception:
            tool_schema_hash = None
        self._last_context_hash = compute_context_hash(
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            model_name=self.provider.model_name if self.provider else "",
            system_prompt_hash=getattr(self, "_system_context_hash", None),
            tool_schema_hash=tool_schema_hash,
        )

        # Economy: response cache lookup (exact match, then semantic)
        cached_response = None
        try:
            cached_response = self._cache_lookup(full_message)
        except Exception as e:
            logger.warning("economy cache_lookup failed: %s", e)
        if cached_response is None:
            try:
                cached_response = await self._semantic_cache_lookup(message, self._last_context_hash)
            except Exception as e:
                logger.warning("semantic cache_lookup failed: %s", e)
        if cached_response is not None:
            self._economy_tracker.record_cache_hit()
            self._turn_economy.cache_hit = True
            yield CoreEvent.text_chunk(cached_response, request_id)
            savings = self._economy_tracker.get_summary()
            if any(v for v in savings.values()):
                yield CoreEvent.economy_savings(savings)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="cache_hit",
                iteration=0,
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary="cache hit",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="cache_hit",
                ),
            )
            self._restore_model()
            yield CoreEvent.done(reason="cache_hit")
            return

        if self.history_adapter:
            self.history_adapter.add_message("user", message)

        # Apply pending background LLM compression from previous turn
        try:
            if self._pending_llm_compression and self._pending_llm_compression.done() and self.provider:
                compressed = self._pending_llm_compression.result()
                if compressed:
                    self.provider.set_history(compressed)
                    logger.info("Applied deferred LLM compression: %d messages", len(compressed))
                self._pending_llm_compression = None
        except Exception as e:
            logger.warning("deferred LLM compression failed: %s", e)
            self._pending_llm_compression = None

        # Compress conversation context if configured and threshold exceeded
        try:
            cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
            eco_compress = getattr(self.config.economy, "compress_after_turns", 0) if self.config else 0
            if cc_cfg and eco_compress > 0: # economy preset overrides compression threshold
                from dataclasses import replace as _dc_replace
                cc_cfg = _dc_replace(cc_cfg, compress_after_turns=eco_compress) # copy, don't mutate shared config
            if cc_cfg and getattr(cc_cfg, "enabled", False) and self.provider:
                history = self.provider.get_history()
                if self._context_compressor.should_compress(history, cc_cfg):
                    before = len(history)
                    from .context_compressor import CompactionStrategy
                    strategy = self._context_compressor.select_strategy(history, cc_cfg)
                    if strategy == CompactionStrategy.LLM:
                        # apply instant non-LLM compression now, defer LLM to background
                        compressed = self._context_compressor.compress(history, cc_cfg)
                        self.provider.set_history(compressed)
                        after = len(compressed)
                        self._pending_llm_compression = asyncio.create_task(
                            self._context_compressor.compress_with_llm(history, cc_cfg, self.provider)
                        )
                    else:
                        _strip_chars = getattr(self.config.economy, "tool_strip_chars", 200) if self.config else 200
                        compressed = await self._context_compressor.compress_auto(
                            history, cc_cfg, provider=self.provider,
                            tool_strip_chars=_strip_chars,
                        )
                        self.provider.set_history(compressed)
                        after = len(compressed)
                    logger.info("Compressed conversation context: %d -> %d messages", before, after)
                    compaction_events = turn_diagnostics.get("compactionEvents")
                    if isinstance(compaction_events, list):
                        compaction_events.append(
                            {
                                "strategy": "compress",
                                "messagesBefore": before,
                                "messagesAfter": after,
                            }
                        )
                    self._pending_events.append(CoreEvent(
                        type="progress",
                        data={"phase": "compression", "message": f"context compressed: {before} \u2192 {after} messages ({100 - after * 100 // max(before, 1)}% reduction)"},
                    ))
        except (AttributeError, TypeError) as e:
            logger.warning("context compression failed: %s", e)

        # Auto LLM compaction when token usage exceeds threshold
        try:
            cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
            if cc_cfg and getattr(cc_cfg, "enabled", False) and self.provider:
                threshold_ratio = getattr(cc_cfg, "token_threshold_for_llm_compact", 0.8)
                if threshold_ratio > 0:
                    caps = self.provider.get_capabilities()
                    max_ctx = caps.max_context_tokens
                    total_used = self._session_total_input_tokens + self._session_total_output_tokens
                    if max_ctx > 0 and total_used > max_ctx * threshold_ratio:
                        history = self.provider.get_history()
                        msgs_before = len(history)
                        if msgs_before > 2: # only compact if enough history
                            result = await self._compact_summarize(history, msgs_before)
                            logger.info("Auto LLM compact triggered: %s", result)
                            compaction_events = turn_diagnostics.get("compactionEvents")
                            if isinstance(compaction_events, list):
                                compaction_events.append(
                                    {
                                        "strategy": str(result.get("strategy", "llm_compact") or "llm_compact"),
                                        "messagesBefore": msgs_before,
                                        "messagesAfter": int(result.get("messages_after", 0) or 0),
                                    }
                                )
                            self._pending_events.append(CoreEvent(
                                type="progress",
                                data={"phase": "llm_compact", "message": f"auto LLM compact: {msgs_before} \u2192 {result.get('messages_after', 0)} messages"},
                            ))
        except (AttributeError, TypeError) as e:
            logger.warning("auto LLM compaction failed: %s", e)

        try:
            accumulated_text = ""

            def _observe_event(event: CoreEvent) -> None:
                nonlocal last_checkpoint_id
                if event.type != "tool_result":
                    return
                checkpoint_id = event.data.get("checkpointId")
                if checkpoint_id:
                    last_checkpoint_id = str(checkpoint_id)
                self._record_mutation_summary(
                    tool_name=str(event.data.get("toolName", "")),
                    result=event.data,
                )
                tool_name = event.data.get("toolName", "")
                if tool_name in ("write_todos", "update_todo") and self.tool_registry:
                    todos = self.tool_registry._todos
                    completed = sum(1 for t in todos if t.get("status") == "completed")
                    self._pending_events.append(CoreEvent.todo_update(todos, completed, len(todos)))

            # KV cache: reorder context for cache-friendly prefix (local inference only)
            if self._kv_cache_store and isinstance(full_message, str) and is_local_inference(self.config.model.provider if self.config else ""):
                try:
                    ctx_files = [(fc.path, fc.content) for fc in getattr(self._context_manager, "_last_selected_files", []) if hasattr(fc, "path") and hasattr(fc, "content")]
                    if ctx_files:
                        full_message = build_cache_friendly_prompt(ctx_files, message, store=self._kv_cache_store)
                except Exception as e:
                    logger.debug("kv cache prompt reorder skipped: %s", e)
            provider_message = self._maybe_apply_vision(full_message) # multimodal if images detected
            async for chunk in self.provider.send_message_stream(provider_message):
                if cancel_event.is_set():
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="cancelled",
                        iteration=iteration,
                    )
                    self._finish_run_record(
                        run_state,
                        status="cancelled",
                        summary="cancelled",
                        error_message="cancelled",
                        checkpoint_id=last_checkpoint_id,
                        artifact_dir=artifact_dir,
                        metadata_updates=self._build_run_metadata_updates(
                            request_id=request_id,
                            diagnostics=turn_diagnostics,
                            completion_reason_code="cancelled",
                        ),
                    )
                    yield CoreEvent.done(reason="cancelled")
                    return

                if chunk.function_calls:
                    self._turn_tool_call_count += len(chunk.function_calls)
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="provider_requested_tools",
                        iteration=iteration,
                        details={"callCount": len(chunk.function_calls)},
                    )
                    # extract usage from structured UsageMetadata or metadata dict
                    u = chunk.usage
                    _sys, _hist, _tool = self._compute_token_breakdown()
                    if u:
                        self._track_cost(
                            u.input_tokens,
                            u.output_tokens,
                            cache_creation_input_tokens=u.cache_creation_input_tokens,
                            cache_read_input_tokens=u.cache_read_input_tokens,
                        )
                        yield CoreEvent.cost_update(
                            input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                            cache_creation_input_tokens=u.cache_creation_input_tokens,
                            cache_read_input_tokens=u.cache_read_input_tokens,
                            cumulative_input_tokens=self._session_total_input_tokens,
                            cumulative_output_tokens=self._session_total_output_tokens,
                            system_tokens=_sys, history_tokens=_hist, tool_result_tokens=_tool,
                        )
                    elif chunk.metadata:
                        usage = chunk.metadata.get("usage", {})
                        if usage:
                            self._track_cost(
                                usage.get("input_tokens", 0),
                                usage.get("output_tokens", 0),
                                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
                                cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
                            )
                            yield CoreEvent.cost_update(
                                input_tokens=usage.get("input_tokens", 0),
                                output_tokens=usage.get("output_tokens", 0),
                                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
                                cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
                                cumulative_input_tokens=self._session_total_input_tokens,
                                cumulative_output_tokens=self._session_total_output_tokens,
                                system_tokens=_sys, history_tokens=_hist, tool_result_tokens=_tool,
                            )
                    # emit context pressure alongside cost update
                    _total_ctx = _sys + _hist + _tool
                    _max_ctx = self.provider.get_capabilities().max_context_tokens if self.provider else 0
                    if _max_ctx > 0:
                        _pct = round(_total_ctx / _max_ctx * 100, 1)
                        yield CoreEvent.context_pressure(_total_ctx, _max_ctx, _pct)
                        # auto-compress if pressure exceeds threshold
                        try:
                            _compress_result = await self._auto_compress_on_pressure()
                            if _compress_result:
                                yield CoreEvent.progress("auto_compress", f"Context auto-compressed ({_compress_result})")
                        except Exception:
                            pass

                    tool_results = await self._handle_function_calls_events(
                        chunk,
                        iteration,
                        max_iterations,
                        request_id,
                        message,
                        turn_diagnostics=turn_diagnostics,
                    )
                    for ev in self._pending_events:
                        _observe_event(ev)
                        yield ev
                    self._pending_events = []

                    response, stream_events = await self._stream_and_collect(tool_results, request_id)
                    for ev in stream_events:
                        _observe_event(ev)
                        yield ev
                        if ev.type == "text_chunk":
                            accumulated_text += ev.data["chunk"]

                    while response.function_calls:
                        iteration += 1
                        if cancel_event.is_set():
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="cancelled",
                                iteration=iteration,
                            )
                            self._finish_run_record(
                                run_state,
                                status="cancelled",
                                summary="cancelled",
                                error_message="cancelled",
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="cancelled",
                                ),
                            )
                            yield CoreEvent.done(reason="cancelled")
                            return
                        if iteration >= max_iterations:
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="iteration_cap_reached",
                                iteration=iteration,
                            )
                            self._finish_run_record(
                                run_state,
                                status="failed",
                                summary="iteration cap reached",
                                error_message="iteration cap reached",
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="iteration_cap",
                                ),
                            )
                            yield CoreEvent.done(reason="iteration_cap")
                            return

                        # Context pressure check
                        pressure_reason = self._check_context_pressure()
                        if pressure_reason:
                            self._append_turn_transition(turn_diagnostics, reason_code="context_pressure", iteration=iteration)
                            self._finish_run_record(
                                run_state, status="stopped", summary="context pressure",
                                checkpoint_id=last_checkpoint_id, artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id, diagnostics=turn_diagnostics,
                                    completion_reason_code="context_pressure",
                                ),
                            )
                            yield CoreEvent.done(reason="context_pressure")
                            return

                        # Economy: tool call budget enforcement
                        eco_budget = getattr(self.config.economy, "tool_call_budget", 0) if self.config else 0
                        if eco_budget > 0 and iteration >= eco_budget:
                            self._economy_tracker.record_tool_calls_avoided(max_iterations - iteration)
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="economy_tool_budget_reached",
                                iteration=iteration,
                                details={"budget": int(eco_budget)},
                            )
                            self._finish_run_record(
                                run_state,
                                status="completed",
                                summary="economy tool budget reached",
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="economy_tool_budget",
                                ),
                            )
                            yield CoreEvent.text_chunk(f"\n[Economy] Tool call budget reached ({eco_budget})", request_id)
                            yield CoreEvent.economy_savings(self._economy_tracker.get_summary())
                            yield CoreEvent.done(reason="economy_tool_budget")
                            self._restore_model()
                            return

                        yield CoreEvent.progress("tool_loop", f"Iteration {iteration}/{max_iterations}", iteration, max_iterations)

                        tool_results = await self._handle_function_calls_events(
                            response,
                            iteration,
                            max_iterations,
                            request_id,
                            message,
                            turn_diagnostics=turn_diagnostics,
                        )
                        for ev in self._pending_events:
                            _observe_event(ev)
                            yield ev
                        self._pending_events = []

                        response, stream_events = await self._stream_and_collect(tool_results, request_id)
                        for ev in stream_events:
                            _observe_event(ev)
                            yield ev
                            if ev.type == "text_chunk":
                                accumulated_text += ev.data["chunk"]

                        # Emit 80% budget warning if approaching limits
                        cost_warning = self._check_cost_warning()
                        if cost_warning:
                            yield CoreEvent.text_chunk(f"\n[Budget warning] {cost_warning}", request_id)
                        # Check cost guardrails mid-loop
                        cost_reason = self._check_cost_guardrails()
                        if cost_reason:
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="cost_guardrail_triggered",
                                iteration=iteration,
                                details={"reason": str(cost_reason)},
                            )
                            self._finish_run_record(
                                run_state,
                                status="failed",
                                summary=cost_reason,
                                error_message=cost_reason,
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="cost_limit",
                                ),
                            )
                            yield CoreEvent.text_chunk(f"\n[Cost guardrail] {cost_reason}", request_id)
                            yield CoreEvent.done(reason="cost_limit")
                            return

                    break

                else:
                    thinking = getattr(chunk, "thinking_content", None)
                    if thinking:
                        yield CoreEvent.thinking_chunk(thinking, request_id)
                    if chunk.content:
                        accumulated_text += chunk.content
                        yield CoreEvent.text_chunk(chunk.content, request_id)
                        # live estimated token count per chunk
                        est_out = len(accumulated_text) // 4
                        yield CoreEvent.cost_update(
                            output_tokens=est_out,
                            is_estimate=True,
                            cumulative_input_tokens=self._session_total_input_tokens,
                            cumulative_output_tokens=self._session_total_output_tokens + est_out,
                        )

            accumulated_text, confidence_suffix = self._ensure_confidence_line(accumulated_text)
            if confidence_suffix:
                yield CoreEvent.text_chunk(confidence_suffix, request_id)

            # emit final confidence score so the client can display it
            _conf_pct = self._extract_confidence_percent(accumulated_text) or _DEFAULT_CONFIDENCE_PERCENT
            yield CoreEvent.cost_update(
                confidence_percent=_conf_pct,
                confidence_category=self._confidence_bucket(_conf_pct),
            )

            # architect mode: if architect responded with a plan, switch to editor for next turn
            if self._architect_mode and self._architect_mode.enabled and accumulated_text:
                if self._architect_mode.should_switch_to_editor(accumulated_text):
                    try:
                        await self._architect_mode.switch_to_editor(self, accumulated_text)
                    except Exception as e:
                        logger.warning("architect->editor switch failed: %s", e)
                elif self._architect_mode.phase == "editor":
                    try:
                        await self._architect_mode.reset_to_architect(self)
                    except Exception as e:
                        logger.warning("editor->architect reset failed: %s", e)

            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            # Working memory: post-turn update (confusion detection + memory persist)
            try:
                wm_mgr = self._working_memory_mgr
                if wm_mgr and accumulated_text:
                    history_text = ""
                    if self.history_adapter:
                        history_text = "\n".join(
                            f"{m.get('role','')}: {str(m.get('content',''))[:200]}"
                            for m in (self.get_history() if self._initialized and self.provider else [])
                        )
                    wm_mgr.post_turn(accumulated_text, history_text)
            except Exception as e:
                logger.warning("working memory post-turn failed: %s", e)

            self._append_turn_transition(
                turn_diagnostics,
                reason_code="completed",
                iteration=iteration,
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=accumulated_text or "completed",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="complete",
                ),
            )

            # Economy: store response in cache (exact + semantic)
            try:
                self._cache_store(full_message, accumulated_text)
            except Exception:
                pass
            try:
                await self._semantic_cache_store(message, self._last_context_hash, accumulated_text)
            except Exception:
                pass

            try:
                queued = self._schedule_auto_compaction()
                if queued:
                    yield CoreEvent.progress(
                        "auto_compact",
                        "auto compact queued"
                        f" ({queued.get('utilization_before_pct', 0)}% -> {queued.get('target_utilization_pct', 0)}%)",
                    )
            except Exception as e:
                logger.warning("auto compact scheduling failed: %s", e)

            # Token budget controller: observe outcome and log
            try:
                if self._budget_state and self._budget_action:
                    elapsed = time.monotonic() - self._turn_start_mono
                    task_ok = bool(accumulated_text and len(accumulated_text) > 10)
                    outcome = BudgetTurnOutcome(
                        task_succeeded=task_ok,
                        user_retried=False,
                        total_tokens_used=self._task_input_tokens + self._task_output_tokens,
                        input_tokens=self._task_input_tokens,
                        output_tokens=self._task_output_tokens,
                        response_time_seconds=round(elapsed, 2),
                        tool_calls_made=self._turn_tool_call_count,
                    )
                    self._budget_controller.observe(self._budget_state, self._budget_action, outcome)
                    self._budget_logger.log(self._budget_state, self._budget_action, outcome)
                    self._recent_turn_failures.append(not task_ok)
                    if len(self._recent_turn_failures) > 10:
                        self._recent_turn_failures = self._recent_turn_failures[-10:]
            except Exception as e:
                logger.warning("budget controller observe failed: %s", e)

            # Economy: emit savings summary and restore model
            savings = self._economy_tracker.get_summary()
            if any(v for v in savings.values()):
                yield CoreEvent.economy_savings(savings)
            # emit per-turn economy report
            from dataclasses import asdict as _turn_asdict
            _report = _turn_asdict(self._turn_economy)
            if any(v for v in _report.values()):
                yield CoreEvent.economy_turn_report(_report)
            self._restore_model()
            # restore per-turn output cap
            if _saved_max_output is not None and self.provider:
                self.provider.economy_max_output_tokens = _saved_max_output

            yield CoreEvent.done(reason="complete")
            logger.info(f"Message complete (events), {len(accumulated_text)} chars")

        except (APIRateLimitError, APIError) as e:
            self._last_provider_error = str(e)
            # Attempt provider fallback on rate-limit / server errors
            if self._fallback_manager and self.provider:
                previous_provider = self.config.model.provider if self.config else ""
                fallback_provider = await self._fallback_manager.try_fallback(
                    previous_provider,
                    e,
                    tools=self._tool_declarations_for_shipping(),
                    system_instruction=self._system_instruction,
                )
                if fallback_provider:
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="fallback_switch",
                        details={
                            "from": previous_provider,
                            "to": fallback_provider.get_provider_name(),
                        },
                    )
                    self._last_fallback_summary = {
                        "from": previous_provider,
                        "to": fallback_provider.get_provider_name(),
                        "reason": str(e),
                    }
                    logger.info("Falling back to %s", fallback_provider.get_provider_name())
                    yield CoreEvent.text_chunk(
                        f"[Fallback] Switching to {fallback_provider.get_provider_name()}\n", request_id
                    )
                    self.provider = fallback_provider
                    # Retry with fallback provider (non-recursive, single retry)
                    try:
                        async for chunk in self.provider.send_message_stream(full_message):
                            if chunk.content:
                                accumulated_text += chunk.content
                                yield CoreEvent.text_chunk(chunk.content, request_id)
                        self._append_turn_transition(
                            turn_diagnostics,
                            reason_code="completed",
                            iteration=iteration,
                            details={"viaFallback": True},
                        )
                        self._finish_run_record(
                            run_state,
                            status="completed",
                            summary=accumulated_text or "completed",
                            checkpoint_id=last_checkpoint_id,
                            artifact_dir=artifact_dir,
                            metadata_updates=self._build_run_metadata_updates(
                                request_id=request_id,
                                diagnostics=turn_diagnostics,
                                completion_reason_code="complete",
                            ),
                        )
                        yield CoreEvent.done(reason="complete")
                        return
                    except Exception as fallback_err:
                        self._last_provider_error = str(fallback_err)
                        logger.error("Fallback provider also failed: %s", fallback_err)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="provider_error",
                iteration=iteration,
                details={"message": str(e)},
            )
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="provider_error",
                ),
            )
            suggestions = self._error_recovery.get_suggestions(e)
            if suggestions:
                hint = self._error_recovery.format_suggestions(suggestions)
                yield CoreEvent.text_chunk(f"\n{hint}", request_id)
            raise PoorCLIError(f"Failed to send message: {e}")
        except Exception as e:
            logger.exception("Error sending message (events)")
            self._last_provider_error = str(e)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="exception",
                iteration=iteration,
                details={"message": str(e)},
            )
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="exception",
                ),
            )
            raise PoorCLIError(f"Failed to send message: {e}")
        finally:
            self._clear_cancel_event(request_id)
            # always restore per-turn output cap, even on exception
            if _saved_max_output is not None and self.provider:
                self.provider.economy_max_output_tokens = _saved_max_output

    async def _stream_and_collect(
        self,
        message: Any,
        request_id: str = "",
    ) -> Tuple["ProviderResponse", List["CoreEvent"]]:
        """Stream a provider call, collecting events and building a response."""
        accumulated_text = ""
        accumulated_chars = 0
        _chunk_count = 0
        function_calls: Optional[List[FunctionCall]] = None
        metadata: Dict[str, Any] = {}
        events: List[CoreEvent] = []
        last_usage: Optional[UsageMetadata] = None
        async for chunk in self.provider.send_message_stream(message):
            if chunk.usage:
                last_usage = chunk.usage
            if chunk.function_calls:
                function_calls = chunk.function_calls
                if chunk.metadata:
                    metadata = chunk.metadata
            else:
                thinking = getattr(chunk, "thinking_content", None)
                if thinking:
                    events.append(CoreEvent.thinking_chunk(thinking, request_id))
                if chunk.content:
                    accumulated_text += chunk.content
                    accumulated_chars += len(chunk.content)
                    _chunk_count += 1
                    events.append(CoreEvent.text_chunk(chunk.content, request_id))
                    # throttled live estimated cost (every 10 chunks to reduce noise)
                    if _chunk_count % 10 == 0:
                        est_output = accumulated_chars // 4
                        events.append(CoreEvent.cost_update(
                            output_tokens=est_output,
                            is_estimate=True,
                            cumulative_input_tokens=self._session_total_input_tokens,
                            cumulative_output_tokens=self._session_total_output_tokens + est_output,
                        ))
        # reconcile with actual usage at stream end
        actual_in = 0
        actual_out = 0
        cache_create = 0
        cache_read = 0
        if last_usage:
            actual_in = last_usage.input_tokens
            actual_out = last_usage.output_tokens
            cache_create = last_usage.cache_creation_input_tokens
            cache_read = last_usage.cache_read_input_tokens
        if not actual_in and not actual_out and metadata:
            usage = metadata.get("usage", {})
            if usage:
                actual_in = usage.get("input_tokens", 0)
                actual_out = usage.get("output_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
        if actual_in or actual_out:
            self._track_cost(
                actual_in,
                actual_out,
                cache_creation_input_tokens=cache_create,
                cache_read_input_tokens=cache_read,
            )
            events.append(CoreEvent.cost_update(
                input_tokens=actual_in,
                output_tokens=actual_out,
                cache_creation_input_tokens=cache_create,
                cache_read_input_tokens=cache_read,
                cumulative_input_tokens=self._session_total_input_tokens,
                cumulative_output_tokens=self._session_total_output_tokens,
            ))
        elif accumulated_chars > 0:
            # no actual usage available, finalize with estimate
            est_output = accumulated_chars // 4
            self._track_cost(0, est_output)
            events.append(CoreEvent.cost_update(
                output_tokens=est_output,
                is_estimate=True,
                cumulative_input_tokens=self._session_total_input_tokens,
                cumulative_output_tokens=self._session_total_output_tokens,
            ))
        response = ProviderResponse(
            content=accumulated_text,
            function_calls=function_calls,
            metadata=metadata,
        )
        return response, events

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

    @staticmethod
    def _total_tool_result_chars(tool_results: List[Dict[str, Any]]) -> int:
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
        capabilities = self.provider.get_capabilities()
        tools = (
            list(tool_declarations)
            if tool_declarations is not None
            else (
                list(self._active_tool_declarations)
                if self._active_tool_declarations
                else self._tool_declarations_for_shipping()
            )
        )
        if not capabilities.supports_function_calling:
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

    async def send_message(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        source_kind: str = "session",
        source_id: str = "",
        artifact_dir: str = "",
        run_metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Send a message and yield streaming text chunks.

        This method handles function calls internally and yields only text content.
        Legacy interface — streaming clients should use send_message_events().
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")

        logger.info(f"Sending message: {message[:100]}...")
        run_state = self._start_run_record(
            source_kind=source_kind,
            source_id=str(source_id or "session").strip() or "session",
            artifact_dir=artifact_dir,
            metadata=run_metadata,
        )
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        builtin_workspace_map = await self._maybe_builtin_workspace_map(message)
        if builtin_workspace_map is not None:
            if self.history_adapter:
                self.history_adapter.add_message("user", message)
                self.history_adapter.add_message("model", builtin_workspace_map)
            self._finish_run_record(
                run_state,
                status="completed",
                summary=builtin_workspace_map or "workspace map",
                artifact_dir=artifact_dir,
            )
            yield builtin_workspace_map
            return
        full_message = await self._build_context_message(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        await self._activate_tools_for_prompt(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
        )

        if self.history_adapter:
            self.history_adapter.add_message("user", message)

        try:
            accumulated_text = ""
            max_iterations = self.config.agentic.max_iterations if self.config else 25
            iteration = 0
            last_checkpoint_id: Optional[str] = None

            async for chunk in self.provider.send_message_stream(full_message):
                if chunk.function_calls:
                    tool_results = await self._handle_function_calls_events(
                        chunk,
                        iteration,
                        max_iterations,
                        request_id="",
                        user_request=message,
                    )
                    for ev in self._pending_events:
                        if ev.type == "tool_result":
                            checkpoint_id = ev.data.get("checkpointId")
                            if checkpoint_id:
                                last_checkpoint_id = str(checkpoint_id)
                            self._record_mutation_summary(
                                tool_name=str(ev.data.get("toolName", "")),
                                result=ev.data,
                            )
                    self._pending_events = []
                    response = await self.provider.send_message(tool_results)
                    if response.content:
                        accumulated_text += response.content
                        yield response.content
                    while response.function_calls:
                        iteration += 1
                        if iteration >= max_iterations:
                            break
                        tool_results = await self._handle_function_calls_events(
                            response,
                            iteration,
                            max_iterations,
                            request_id="",
                            user_request=message,
                        )
                        for ev in self._pending_events:
                            if ev.type == "tool_result":
                                checkpoint_id = ev.data.get("checkpointId")
                                if checkpoint_id:
                                    last_checkpoint_id = str(checkpoint_id)
                                self._record_mutation_summary(
                                    tool_name=str(ev.data.get("toolName", "")),
                                    result=ev.data,
                                )
                        self._pending_events = []
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

            self._finish_run_record(
                run_state,
                status="completed",
                summary=accumulated_text or "completed",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
            )
            try:
                self._schedule_auto_compaction()
            except Exception as e:
                logger.warning("auto compact scheduling failed: %s", e)

            logger.info(f"Message complete, {len(accumulated_text)} chars")

        except Exception as e:
            logger.exception("Error sending message")
            self._last_provider_error = str(e)
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                artifact_dir=artifact_dir,
            )
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

    async def send_message_sync(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        source_kind: str = "session",
        source_id: str = "",
        artifact_dir: str = "",
        run_metadata: Optional[Dict[str, Any]] = None,
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
        run_state = self._start_run_record(
            source_kind=source_kind,
            source_id=str(source_id or "session").strip() or "session",
            artifact_dir=artifact_dir,
            metadata=run_metadata,
        )
        max_iterations = self.config.agentic.max_iterations if self.config else 25
        turn_diagnostics = self._new_run_turn_diagnostics(max_iterations=max_iterations)
        self._append_turn_transition(
            turn_diagnostics,
            reason_code="run_started",
            iteration=0,
            details={
                "sourceKind": source_kind,
                "sourceId": str(source_id or "session").strip() or "session",
            },
        )
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        builtin_workspace_map = await self._maybe_builtin_workspace_map(message)
        if builtin_workspace_map is not None:
            if self.history_adapter:
                self.history_adapter.add_message("user", message)
                self.history_adapter.add_message("model", builtin_workspace_map)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="builtin_command",
                iteration=0,
                details={"command": "/workspace-map"},
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=builtin_workspace_map or "workspace map",
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    diagnostics=turn_diagnostics,
                    completion_reason_code="builtin_command",
                ),
            )
            return builtin_workspace_map
        
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
            iteration = 0
            last_checkpoint_id: Optional[str] = None
            iteration_cap_reached = False
            
            # Handle function calls
            while response.function_calls:
                self._append_turn_transition(
                    turn_diagnostics,
                    reason_code="provider_requested_tools",
                    iteration=iteration,
                    details={"callCount": len(response.function_calls)},
                )
                if iteration >= max_iterations:
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="iteration_cap_reached",
                        iteration=iteration,
                    )
                    iteration_cap_reached = True
                    break
                tool_results = await self._handle_function_calls_events(
                    response,
                    iteration,
                    max_iterations,
                    request_id="",
                    user_request=message,
                    turn_diagnostics=turn_diagnostics,
                )
                for ev in self._pending_events:
                    if ev.type == "tool_result":
                        checkpoint_id = ev.data.get("checkpointId")
                        if checkpoint_id:
                            last_checkpoint_id = str(checkpoint_id)
                        self._record_mutation_summary(
                            tool_name=str(ev.data.get("toolName", "")),
                            result=ev.data,
                        )
                self._pending_events = []
                response = await self.provider.send_message(tool_results)
                if response.content:
                    accumulated_text += response.content
                iteration += 1
            
            accumulated_text, _ = self._ensure_confidence_line(accumulated_text)

            # Save assistant response to history
            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            completion_reason = "iteration_cap" if iteration_cap_reached else "complete"
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="completed" if not iteration_cap_reached else "iteration_cap_reached",
                iteration=iteration,
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=accumulated_text or "completed",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    diagnostics=turn_diagnostics,
                    completion_reason_code=completion_reason,
                ),
            )
            try:
                self._schedule_auto_compaction()
            except Exception as e:
                logger.warning("auto compact scheduling failed: %s", e)
            
            logger.info(f"Message complete (sync), {len(accumulated_text)} chars")
            return accumulated_text
            
        except Exception as e:
            logger.exception("Error sending message (sync)")
            self._last_provider_error = str(e)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="exception",
                details={"message": str(e)},
            )
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    diagnostics=turn_diagnostics,
                    completion_reason_code="exception",
                ),
            )
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
        language: str,
        *,
        request_id: str = "",
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
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

        cancel_event = self._prepare_cancel_event(request_id)
        logger.info(f"Inline complete for {file_path} ({language})")

        prompt = self.build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language
        )

        completion_provider = self.provider
        try:
            if provider_name or model_name:
                completion_provider = await self._create_provider_instance(
                    provider_name,
                    model_name,
                    tools=[],
                    system_instruction=get_system_instruction("inline"),
                )

            async for chunk in completion_provider.send_message_stream(prompt):
                if cancel_event.is_set():
                    return
                if chunk.content:
                    yield chunk.content

            logger.info("Inline completion finished")

        except Exception as e:
            logger.exception("Error in inline completion")
            raise PoorCLIError(f"Inline completion failed: {e}")
        finally:
            self._clear_cancel_event(request_id)

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

    @property
    def plan_callback(self) -> Optional[Callable[..., Any]]:
        """Get the plan review callback for execution gating."""
        return self._plan_callback

    @plan_callback.setter
    def plan_callback(self, callback: Optional[Callable[..., Any]]) -> None:
        """Set the async plan review callback."""
        self._plan_callback = callback
        logger.info("Plan callback updated")

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

    # get_provider_info, get_provider_readiness, get_routing_mode,
    # set_routing_mode now live in core_provider_info:ProviderInfoMixin.

    def list_workflow_templates(self) -> List[Dict[str, Any]]:
        if not self.config:
            return list_workflow_templates()
        templates = list_workflow_templates()
        defaults = getattr(getattr(self.config, "workflow", None), "defaults", {}) or {}
        if not isinstance(defaults, dict):
            return templates
        merged: List[Dict[str, Any]] = []
        for template in templates:
            override = defaults.get(template["name"], {})
            if isinstance(override, dict):
                merged.append({**template, **override})
            else:
                merged.append(template)
        return merged

    def get_workflow_template(self, name: str) -> Optional[Dict[str, Any]]:
        template = get_workflow_template(name)
        if template is None:
            return None
        defaults = getattr(getattr(self.config, "workflow", None), "defaults", {}) if self.config else {}
        override = defaults.get(template["name"], {}) if isinstance(defaults, dict) else {}
        if isinstance(override, dict):
            template = {**template, **override}
        return template

    def get_last_run_id(self) -> Optional[str]:
        return self._last_run_id

    def list_runs(
        self,
        *,
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        if not self._run_history:
            return []
        payloads: List[Dict[str, Any]] = []
        for record in self._run_history.list_runs(
            source_kind=source_kind,
            source_id=source_id,
            limit=limit,
        ):
            payload = record.to_dict()
            diagnostics = self._extract_run_diagnostics(payload.get("metadata", {}))
            payload["diagnostics"] = diagnostics
            payload["completionReasonCode"] = diagnostics.get("completionReasonCode", "")
            payload["transitionCount"] = len(diagnostics.get("turnTransitions", []))
            payload["turnCount"] = len(diagnostics.get("turnOrchestration", []))
            payloads.append(payload)
        return payloads

    def build_status_view(self) -> Dict[str, Any]:
        provider_info = self.get_provider_info() if self._initialized else {}
        provider_status = self.get_provider_readiness()
        recent_runs = self.list_runs(limit=5)
        active_runs = [run for run in recent_runs if run.get("status") == "running"]
        last_run = recent_runs[0] if recent_runs else None
        last_mutation = dict(self._last_mutation_summary)
        last_context = dict(self._last_context_preview)
        trusted_security = {
            "trustedWorkspaceBoundary": bool(
                getattr(getattr(self.config, "security", None), "enforce_trusted_workspace", True)
            ),
            "trustedRoots": list(
                getattr(getattr(self.config, "security", None), "trusted_roots", []) or []
            ),
        }
        return {
            "session": {
                "initialized": bool(self._initialized),
                "provider": provider_info.get("name", ""),
                "model": provider_info.get("model", ""),
                "routingMode": self.get_routing_mode(),
                "permissionMode": getattr(
                    getattr(getattr(self.config, "security", None), "permission_mode", None),
                    "value",
                    str(getattr(getattr(self.config, "security", None), "permission_mode", "")),
                ),
            },
            "trust": {
                "sandboxPreset": getattr(getattr(self.config, "sandbox", None), "default_preset", ""),
                "policy": self.get_policy_status(),
                "audit": self.get_policy_status().get("audit", {}),
                "mcp": self.get_mcp_status(),
                "security": trusted_security,
                "checkpointing": bool(getattr(getattr(self.config, "checkpoint", None), "enabled", False)),
            },
            "provider": {
                "active": provider_info,
                "readiness": provider_status,
                "fallback": dict(self._last_fallback_summary),
                "lastError": self._last_provider_error,
                "privacyPosture": suggested_privacy_posture(provider_status),
            },
            "context": {
                "lastPreview": last_context,
                "pressure": self.get_context_pressure() if self.provider else {},
                "compaction": self.get_compaction_status(),
            },
            "runs": {
                "recent": recent_runs,
                "activeCount": len(active_runs),
                "lastRun": last_run,
                "lastRunDiagnostics": (last_run or {}).get("diagnostics", {}),
            },
            "collaboration": {},
            "recovery": {
                "cost": self.get_session_cost_summary(),
                "lastMutation": last_mutation,
            },
        }

    def build_doctor_report(self) -> Dict[str, Any]:
        status_view = self.build_status_view()
        provider_status = status_view["provider"]["readiness"]
        checks: List[Dict[str, Any]] = []
        ready_provider_count = len([payload for payload in provider_status.values() if payload.get("ready")])
        checks.append(
            {
                "id": "providers",
                "title": "Provider readiness",
                "status": "ok" if ready_provider_count else "degraded",
                "message": f"{ready_provider_count} provider(s) ready",
                "action": "Run `/setup`, `/api-key status`, or switch to `ollama` private mode.",
            }
        )
        checks.append(
            {
                "id": "sandbox",
                "title": "Execution safety",
                "status": "warning"
                if status_view["trust"]["sandboxPreset"] == "full-access"
                else "ok",
                "message": f"Sandbox preset `{status_view['trust']['sandboxPreset']}`",
                "action": "Prefer `review-only` or `workspace-write` for normal coding sessions.",
            }
        )
        checks.append(
            {
                "id": "routing",
                "title": "Routing mode",
                "status": "ok",
                "message": f"Routing mode `{status_view['session']['routingMode']}`",
                "action": "Use `private` to force Ollama-only routing when local privacy matters.",
            }
        )
        checks.append(
            {
                "id": "context",
                "title": "Context visibility",
                "status": "ok" if status_view["context"]["lastPreview"] else "warning",
                "message": "Context explanation available"
                if status_view["context"]["lastPreview"]
                else "No context preview captured yet",
                "action": "Run `/context explain` or preview context before a large request.",
            }
        )
        checks.append(
            {
                "id": "recovery",
                "title": "Recovery state",
                "status": "ok",
                "message": "Checkpointing enabled"
                if status_view["trust"]["checkpointing"]
                else "Checkpointing disabled",
                "action": "Enable checkpoints for safer mutation-heavy sessions.",
            }
        )
        overall = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
        return {
            "summary": {
                "overall": overall,
                "routingMode": status_view["session"]["routingMode"],
                "privacyPosture": status_view["provider"]["privacyPosture"],
                "readyProviderCount": ready_provider_count,
            },
            "checks": checks,
            "statusView": status_view,
        }

    def inspect_instruction_stack(
        self,
        referenced_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return the active deterministic instruction stack."""
        if not referenced_files and self._last_instruction_snapshot is not None:
            return self._last_instruction_snapshot.to_dict()
        snapshot = self._inspect_instruction_snapshot(
            referenced_files,
            skill_context=self._build_instruction_skill_context(),
            skill_plan=self._last_instruction_skill_plan,
        )
        self._last_instruction_snapshot = snapshot
        return snapshot.to_dict()

    def get_policy_status(self) -> Dict[str, Any]:
        """Return repo-local policy and audit status."""
        hooks = self._hook_manager.status() if self._hook_manager else {
            "hooksDir": str(Path.cwd() / ".poor-cli" / "hooks"),
            "totalHooks": 0,
            "supportedSchemaVersions": [1],
            "validationErrors": [],
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
        # flush budget controller logs
        try:
            self._budget_logger.close()
        except Exception:
            pass
        # persist session cost to history
        self._persist_cost_history()
        # emit session_end hook
        try:
            await self._emit_policy_hooks("session_end", {
                "inputTokens": getattr(self, "_session_total_input_tokens", 0),
                "outputTokens": getattr(self, "_session_total_output_tokens", 0),
            })
        except Exception:
            pass
        # clean up headless browser if used
        try:
            from .browser_tool import shutdown_browser
            await shutdown_browser()
        except Exception:
            pass
        # auto-save memorable patterns from this session
        if self.provider and self._initialized:
            try:
                from .auto_memory import auto_save_session_memories
                history = self.provider.get_history()
                if history:
                    saved = await auto_save_session_memories(history, provider=self.provider)
                    if saved:
                        logger.info("auto-saved %d memories on shutdown", len(saved))
            except Exception as exc:
                logger.debug("auto-memory on shutdown failed: %s", exc)
        if self._mcp_manager is not None:
            await self._mcp_manager.shutdown()
        # cancel background tasks
        for task in (self._repo_graph_task, self._pending_llm_compression, self._auto_history_compact_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._repo_graph_task = None
        self._pending_llm_compression = None
        self._auto_history_compact_task = None
        # close pooled HTTP session in tool registry
        if self.tool_registry and hasattr(self.tool_registry, "close"):
            try:
                await self.tool_registry.close()
            except Exception:
                pass

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

    def _resolve_tiered_compaction_mode(self, strategy: str) -> str:
        requested = str(strategy or "compact").strip().lower() or "compact"
        if requested in {"gentle", "aggressive", "balanced"}:
            return requested
        preset = str(getattr(getattr(self.config, "economy", None), "preset", "balanced") or "balanced").strip().lower()
        if requested == "auto":
            pressure_pct = float(self.get_context_pressure().get("pressure_pct", 0) or 0)
            if pressure_pct >= 85:
                return "aggressive"
        if preset == "frugal":
            return "aggressive"
        if preset == "quality":
            return "gentle"
        return "balanced"

    def _resolve_auto_compaction_settings(self) -> Tuple[float, float]:
        cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
        eco_cfg = getattr(self.config, "economy", None) if self.config else None
        threshold = float(getattr(cc_cfg, "auto_compact_threshold", 0.7) or 0.0)
        target = float(getattr(cc_cfg, "auto_compact_target", 0.4) or 0.0)
        eco_threshold = float(getattr(eco_cfg, "auto_compress_pressure_pct", 0.0) or 0.0)
        if eco_threshold > 0:
            threshold = eco_threshold / 100.0
        elif str(getattr(eco_cfg, "preset", "") or "").strip().lower() == "quality":
            threshold = 0.0
        return max(0.0, threshold), max(0.0, target)

    def _record_compaction_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        recorded = dict(payload or {})
        recorded["timestamp"] = time.time()
        self._last_compaction_status = recorded
        return recorded

    async def _summarize_compaction_chunk(
        self,
        messages: List[Dict[str, Any]],
        draft_summary: str,
        policy: CompactionPolicy,
    ) -> str:
        del policy
        if not self.provider:
            return draft_summary
        conversation_text = self._history_to_text(messages)
        if not conversation_text.strip():
            return draft_summary
        prompt = (
            "Summarize the following conversation chunk into this exact structure:\n"
            "## Session Summary (turns 1-N)\n"
            "- User asked: ...\n"
            "- Files modified/referenced: ...\n"
            "- Key decisions: ...\n"
            "- Tool outcomes: ...\n"
            "- Unresolved: ...\n"
            "- Dropped noise lessons: ...\n"
            "Be factual and terse. Keep concrete file paths.\n\n"
            f"Draft summary:\n{draft_summary}\n\n"
            f"Conversation:\n{conversation_text}"
        )
        response = await self.provider.send_message(prompt)
        rendered = response.content.strip() if response and response.content else ""
        return rendered or draft_summary

    async def _compact_tiered_context(
        self,
        history: List[Dict[str, Any]],
        messages_before: int,
        *,
        strategy: str,
        trigger: str,
        allow_model_summary: bool,
    ) -> Dict[str, Any]:
        self._save_transcript(history)
        mode = self._resolve_tiered_compaction_mode(strategy)
        if not history:
            return self._record_compaction_status(
                {
                    "state": "done",
                    "strategy": "compact",
                    "mode": mode,
                    "trigger": trigger,
                    "summary": "(empty history)",
                    "messages_before": messages_before,
                    "messages_after": 0,
                    "tokens_before": 0,
                    "tokens_after": 0,
                    "removed_tokens": 0,
                    "tier_counts": {},
                    "pruned_turns": 0,
                    "pruning_summary": "",
                    "pruning_reasons": {},
                    "pruning_sidecar_path": None,
                }
            )
        max_ctx = 0
        if self.provider:
            try:
                max_ctx = int(self.provider.get_capabilities().max_context_tokens or 0)
            except Exception:
                max_ctx = 0
        threshold, target = self._resolve_auto_compaction_settings()
        callback = self._summarize_compaction_chunk if allow_model_summary else None
        result = await self._tiered_compactor.compact(
            history,
            max_tokens=max_ctx,
            mode=mode,
            economy_preset=str(getattr(getattr(self.config, "economy", None), "preset", "balanced") or "balanced"),
            trigger=trigger,
            summary_callback=callback,
            auto_compact_threshold=threshold,
            auto_compact_target=target,
        )
        pruning_sidecar_path = self._save_pruning_sidecar(result.pruned_turns)
        if self.provider:
            self.provider.set_history(result.history)
        if self.history_adapter:
            self.history_adapter.clear_history()
            for message in result.history:
                self.history_adapter.add_message(message["role"], message["content"])
        if result.pruning_summary:
            if not isinstance(getattr(self, "_pending_events", None), list):
                self._pending_events = []
            self._pending_events.append(
                CoreEvent(
                    type="progress",
                    data={"phase": "history_pruning", "message": result.pruning_summary},
                )
            )
        return self._record_compaction_status(
            {
                "state": "done",
                "strategy": "compact",
                "mode": result.mode,
                "trigger": trigger,
                "summary": result.summary,
                "messages_before": result.messages_before,
                "messages_after": result.messages_after,
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "removed_tokens": result.removed_tokens,
                "tier_counts": result.tier_counts,
                "utilization_before_pct": round(result.utilization_before * 100, 1),
                "utilization_after_pct": round(result.utilization_after * 100, 1),
                "pruned_turns": result.pruned_count,
                "pruning_summary": result.pruning_summary,
                "pruning_reasons": result.pruning_reasons,
                "pruning_sidecar_path": pruning_sidecar_path,
            }
        )

    async def _run_auto_compaction(self) -> Optional[Dict[str, Any]]:
        if not self.provider:
            return None
        history = self.provider.get_history()
        if len(history) <= 4:
            return None
        return await self._compact_tiered_context(
            history,
            len(history),
            strategy="auto",
            trigger="auto",
            allow_model_summary=False,
        )

    def _schedule_auto_compaction(self) -> Optional[Dict[str, Any]]:
        if not self.config or not self.provider:
            return None
        cc_cfg = getattr(self.config, "context_compression", None)
        if not cc_cfg or not getattr(cc_cfg, "enabled", False):
            return None
        threshold, target = self._resolve_auto_compaction_settings()
        if threshold <= 0 or target <= 0:
            return None
        pressure = self.get_context_pressure()
        pressure_ratio = float(pressure.get("pressure_pct", 0) or 0) / 100.0
        if pressure_ratio < threshold:
            return None
        task = getattr(self, "_auto_history_compact_task", None)
        if task and not task.done():
            return None
        queued = self._record_compaction_status(
            {
                "state": "queued",
                "strategy": "compact",
                "mode": self._resolve_tiered_compaction_mode("auto"),
                "trigger": "auto",
                "utilization_before_pct": round(pressure_ratio * 100, 1),
                "target_utilization_pct": round(target * 100, 1),
            }
        )
        loop = asyncio.get_running_loop()
        self._auto_history_compact_task = loop.create_task(self._run_auto_compaction())

        def _done_callback(task_obj: asyncio.Task) -> None:
            try:
                completed = task_obj.result()
            except Exception as exc:
                logger.warning("auto compaction failed: %s", exc)
                self._record_compaction_status(
                    {
                        "state": "error",
                        "strategy": "compact",
                        "mode": queued.get("mode", "balanced"),
                        "trigger": "auto",
                        "error": str(exc),
                    }
                )
                return
            if completed:
                logger.info(
                    "Auto compact: %d -> %d messages",
                    int(completed.get("messages_before", 0) or 0),
                    int(completed.get("messages_after", 0) or 0),
                )

        self._auto_history_compact_task.add_done_callback(_done_callback)
        return queued

    async def compact_context(self, strategy: str) -> Dict[str, Any]:
        """Apply a context management strategy to reduce conversation size."""
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        history = self.get_history()
        messages_before = len(history)
        if strategy in {"auto", "compact", "gentle", "aggressive", "balanced"}:
            result = await self._compact_tiered_context(
                history,
                messages_before,
                strategy=strategy,
                trigger="manual",
                allow_model_summary=True,
            )
        elif strategy == "compress":
            result = self._compact_compress(history, messages_before)
        elif strategy == "handoff":
            result = await self._compact_handoff(history, messages_before)
        else:
            raise PoorCLIError(f"Unknown compaction strategy: {strategy}")
        # reset working memory after compaction — delta state is stale
        try:
            if self._working_memory_mgr:
                summary = result.get("summary", "") if isinstance(result, dict) else ""
                self._working_memory_mgr.reset(new_summary=summary)
                logger.info("working memory reset after compact (%s)", strategy)
        except Exception as e:
            logger.warning("working memory reset failed: %s", e)
        return result

    def _save_transcript(self, history: List[Dict[str, Any]]) -> Optional[str]:
        """Save raw history to disk before compaction. Returns transcript path or None."""
        if not self.config or not getattr(self.config.context_compression, "preserve_transcripts", True):
            return None
        transcript_dir = Path.cwd() / getattr(self.config.context_compression, "transcript_dir", ".poor-cli/transcripts")
        try:
            transcript_dir.mkdir(parents=True, exist_ok=True)
            import json as _json
            import uuid as _uuid
            session_id = getattr(self, "_last_run_id", None) or _uuid.uuid4().hex[:12]
            ts = time.strftime("%Y%m%dT%H%M%S")
            filename = f"{session_id}_{ts}.json"
            dest = transcript_dir / filename
            import tempfile as _tf
            fd, tmp = _tf.mkstemp(dir=str(transcript_dir), suffix=".tmp")
            try:
                data = _json.dumps(history, indent=None, default=str).encode()
                os.write(fd, data)
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
            logger.info("Saved pre-compaction transcript: %s (%d messages)", dest, len(history))
            return str(dest)
        except Exception as exc:
            logger.warning("Failed to save transcript: %s", exc)
            return None

    def _save_pruning_sidecar(self, pruned_turns: List[Dict[str, Any]]) -> Optional[str]:
        """Save pruned turns for later recovery."""
        if not pruned_turns:
            return None
        transcript_root = ".poor-cli/transcripts"
        if self.config and getattr(self.config, "context_compression", None):
            transcript_root = getattr(self.config.context_compression, "transcript_dir", transcript_root)
        sidecar_dir = Path.cwd() / transcript_root / "pruned"
        try:
            sidecar_dir.mkdir(parents=True, exist_ok=True)
            session_id = getattr(self, "_last_run_id", None) or hashlib.sha1(str(time.time()).encode()).hexdigest()[:12]
            ts = time.strftime("%Y%m%dT%H%M%S")
            filename = f"{session_id}_{ts}_pruned.json"
            dest = sidecar_dir / filename
            payload = {
                "runId": getattr(self, "_last_run_id", None),
                "createdAt": ts,
                "turns": pruned_turns,
            }
            import tempfile as _tf
            fd, tmp = _tf.mkstemp(dir=str(sidecar_dir), suffix=".tmp")
            try:
                data = json.dumps(payload, indent=None, default=str).encode()
                os.write(fd, data)
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
            logger.info("Saved pruning sidecar: %s (%d turns)", dest, len(pruned_turns))
            return str(dest)
        except Exception as exc:
            logger.warning("Failed to save pruning sidecar: %s", exc)
            return None

    async def _compact_summarize(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Summarize conversation in-place, re-seed provider."""
        self._save_transcript(history)
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
        self._save_transcript(history)
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
        self._save_transcript(history)
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
        self._user_explicit_model = True

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
            await self._emit_policy_hooks(
                "checkpoint_restored",
                {
                    "checkpointId": checkpoint_id,
                    "restoredFiles": restored_files,
                },
            )
            return self._checkpoint_metadata(checkpoint, restored_files=restored_files)
        except Exception as e:
            logger.error(f"Checkpoint restore failed: {e}")
            raise PoorCLIError(f"Failed to restore checkpoint: {e}")
