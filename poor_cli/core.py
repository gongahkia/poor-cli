"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine used by the PoorCLI terminal client and
the Neovim plugin.
"""

import asyncio
import hashlib
import inspect
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .audit_log import AuditEventType, AuditLogger
from .config import ConfigManager, Config
from .provider_probe import (
    normalize_routing_mode,
    probe_providers,
    resolve_routing_mode,
)
from .provider_catalog import KEYLESS_LOCAL_PROVIDER_NAMES
from .provider_fallback import ProviderFallbackManager
from .providers.base import BaseProvider
from .providers.capability import ProviderCapability, provider_has_capability
from .providers.provider_factory import ProviderFactory
from .run_history import RunHistoryManager
from .tools_async import ToolRegistryAsync
from .enhanced_tools import CORE_TOOL_GROUP, EnhancedToolRegistry
from .checkpoint import CheckpointManager
from .core_events import CoreEvent, HistoryAdapter, RepoHistoryAdapter
from .repo_config import get_repo_config
from .context import ContextManager, get_context_manager
from .context_assembly import ContextAssemblyOrchestrator
from .block_cache import BlockCacheSession
from .instructions import InstructionManager, InstructionSnapshot
from .context_contract import ContextContractManager
from .permission_engine import PermissionEngineMixin
from .mcp_client import MCPManager, discover_mcp_config
from .plan_analyzer import PlanAnalyzer
from .policy_hooks import PolicyHookManager
from .economy import (
    EconomySavingsTracker,
    EconomyTurnReport,
    resolve_output_verbosity,
)
from .token_budget_controller import (
    RuleBasedController,
    TokenBudgetState,
    TokenBudgetAction,
)
from .budget_logger import BudgetLogger
from .error_recovery import ErrorRecoveryManager
from .kv_cache_store import maybe_init_kv_cache, KVCacheStore
from .thinking_budget import ThinkingBudgetOptimizer
from .semantic_cache import (
    SemanticCache,
)
from .prompts import (
    build_tool_calling_system_instruction,
    detect_tone_from_user_memories,
)
from .skills import SkillLoadPlan
from .exceptions import (
    PoorCLIError,
    ConfigurationError,
    MissingAPIKeyError,
    setup_logger,
)
from .core_agent_loop import AgentLoop as AgentLoop
from .core_provider_info import ProviderInfoMixin
from .core_tool_dispatch import ToolDispatcher as ToolDispatcher
from .core_turn_lifecycle import TurnLifecycle as TurnLifecycle

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


class PoorCLICore(AgentLoop, ToolDispatcher, TurnLifecycle, PermissionEngineMixin, ProviderInfoMixin):
    """
    Headless AI coding assistant engine.
    
    This is the core wrapper layer shared by supported clients:
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
        self._provider_ready = False
        self._provider_init_lock: Optional[asyncio.Lock] = None
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
        self._mcp_initialized: bool = False
        self._mcp_init_lock: Optional[asyncio.Lock] = None
        self._active_tool_groups: Tuple[str, ...] = tuple()
        self._active_tool_names: set[str] = set()
        self._active_tool_declarations: List[Dict[str, Any]] = []
        self._plan_analyzer: PlanAnalyzer = PlanAnalyzer()
        self._pending_events: List[CoreEvent] = []
        self._tool_full_outputs: Dict[str, Dict[str, Any]] = {}
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
        # SBP1: per-provider cache telemetry.
        # Shape: {provider_name: {hits, misses, read_tokens, write_tokens, savings_usd}}
        self._session_provider_cache_stats: Dict[str, Dict[str, Any]] = {}
        self._task_input_tokens: int = 0
        self._task_output_tokens: int = 0
        self._task_cost_usd: float = 0.0
        self._task_cache_creation_input_tokens: int = 0
        self._task_cache_read_input_tokens: int = 0
        self._cost_warning_emitted: bool = False
        self._turn_economy: EconomyTurnReport = EconomyTurnReport()
        self._turn_cost_recorded: bool = False
        self._cost_turn_history: List[Dict[str, Any]] = []
        self._cost_tool_totals: Dict[str, Dict[str, Any]] = {}
        self._block_cache: BlockCacheSession = BlockCacheSession()

        self._context_assembly: ContextAssemblyOrchestrator = ContextAssemblyOrchestrator(self)
        self._context_compressor: Any = self._context_assembly.context_compressor
        self._tiered_compactor: Any = self._context_assembly.tiered_compactor

        # Working memory (MemGPT-style delta mode)
        self._working_memory_mgr: Optional[Any] = None # lazy init — WorkingMemoryManager

        # Architect/editor dual-model mode
        self._architect_mode = None
        try:
            agentic = getattr(self.config, "agentic", None) if self.config else None
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
        self._last_context_snapshot: Optional[Any] = None
        self._context_pinned_files: List[str] = []
        self._context_dropped_files: Set[str] = set()
        self._last_mutation_summary: Dict[str, Any] = {}
        self._last_fallback_summary: Dict[str, Any] = {}
        self._last_provider_error: str = ""
        self._last_run_id: Optional[str] = None
        self._resolved_routing_mode: str = "manual"
        self._provider_readiness_cache: Dict[str, Dict[str, Any]] = {}
        self._provider_probe_task: Optional[asyncio.Task] = None
        self._system_refresh_inputs: Optional[Tuple[str, ...]] = None
        self._perf_span_history: List[Dict[str, Any]] = []
        self._active_turn_diagnostics: Optional[Dict[str, Any]] = None
        self._tone_cache_index_hash: str = ""
        self._tone_cache_suffix: str = ""
        self._repo_root: Path = Path.cwd().resolve()
        self._last_compaction_status: Dict[str, Any] = {"state": "idle"}

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
            self._repo_root = repo_root
            init_started = time.monotonic()
            
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
            
            if not resolved_api_key and self.config.model.provider not in KEYLESS_LOCAL_PROVIDER_NAMES:
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
            provider_create_started = time.monotonic()
            self.provider = ProviderFactory.create(
                provider_name=self.config.model.provider,
                api_key=resolved_api_key or "",
                model_name=self.config.model.model_name,
                **extra_kwargs
            )
            self._record_perf_span(
                "core.initialize.provider_factory_create",
                (time.monotonic() - provider_create_started) * 1000.0,
                details={"provider": self.config.model.provider},
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
            audit_cfg = getattr(self.config, "audit", None)
            archive_dir = Path(getattr(audit_cfg, "archive_dir", ".poor-cli/audit/archive/")) if audit_cfg else repo_root / ".poor-cli" / "audit" / "archive"
            if not archive_dir.is_absolute():
                archive_dir = repo_root / archive_dir
            self._audit_logger = AuditLogger(
                audit_dir=repo_root / ".poor-cli",
                max_size_mb=getattr(audit_cfg, "max_size_mb", 100),
                max_rows_live=getattr(audit_cfg, "max_rows_live", 100000),
                max_age_days_live=getattr(audit_cfg, "max_age_days_live", 90),
                archive_chunk_size=getattr(audit_cfg, "archive_chunk_size", 10000),
                archive_dir=archive_dir,
            )

            mcp_servers = self.config.mcp_servers or discover_mcp_config(repo_root)
            if mcp_servers:
                registry_cfg = getattr(getattr(self.config, "mcp", None), "registry", None)
                self._mcp_manager = MCPManager(
                    mcp_servers,
                    repo_root=repo_root,
                    registry_autodiscover=bool(getattr(registry_cfg, "enabled", False)),
                )
                self._mcp_initialized = False
                self._mcp_init_lock = None
            self.tool_registry._core = self  # back-ref for compact/delegate tools
            tool_decl_started = time.monotonic()
            tool_declarations = await self._resolve_tool_declarations_for_groups([CORE_TOOL_GROUP])
            self._record_perf_span(
                "core.initialize.resolve_tool_declarations",
                (time.monotonic() - tool_decl_started) * 1000.0,
                details={"count": len(tool_declarations)},
            )
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
            if self.config.model.provider in KEYLESS_LOCAL_PROVIDER_NAMES:
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

            tone_suffix = self._tone_suffix_for_memory_index(memory_index)
            if tone_suffix:
                self._system_instruction += tone_suffix
            self._system_context_hash = hashlib.sha256(
                (self._system_instruction or "").encode("utf-8", errors="replace")
            ).hexdigest()

            # Lazy provider init: keep startup fast and defer provider session setup
            # (tool schema translation, remote warmup, etc.) to first model request.
            self._provider_ready = False
            self._provider_init_lock = None

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

            # Initialize repo knowledge graph (fully background refresh to keep init snappy)
            if self.config.repo_index.enabled:
                from .repo_graph import RepoGraph
                self._repo_graph = RepoGraph(repo_root)
                if self.config.repo_index.auto_index_on_start:
                    async def _refresh_repo_graph_bg(graph, incremental):
                        loop = asyncio.get_event_loop()
                        try:
                            mode = await loop.run_in_executor(None, graph.should_reindex)
                            if mode == "skip":
                                stats = graph.get_stats()
                                dir_count = graph._count_directories()
                                logger.info("Repo index (skipped): %s", stats)
                                self._pending_events.append(CoreEvent(
                                    type="progress", data={"phase": "repo_index", "message": (
                                        f"repo index up to date: {dir_count} directories, {stats['files']} files, "
                                        f"{stats['symbols']} symbols, {stats['edges']} edges"
                                    )},
                                ))
                                return
                            if mode == "full" or not incremental:
                                stats = await loop.run_in_executor(None, graph.build_index)
                            else:
                                stats = await loop.run_in_executor(None, graph.incremental_update)
                            logger.info("Repo index (%s): %s", mode, stats)
                        except Exception:
                            logger.debug("repo graph background refresh failed", exc_info=True)

                    self._repo_graph_task = asyncio.create_task(
                        _refresh_repo_graph_bg(self._repo_graph, self.config.repo_index.incremental)
                    )
                self._context_manager._repo_graph = self._repo_graph
            self._resolved_routing_mode = normalize_routing_mode(
                getattr(self.config.model, "routing_mode", "manual")
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
            self._schedule_provider_readiness_probe()
            try:
                self._gc_overflow_files()
            except Exception:
                pass
            self._record_perf_span(
                "core.initialize.total",
                (time.monotonic() - init_started) * 1000.0,
                details={"provider": self.config.model.provider, "model": self.config.model.model_name},
            )
            logger.info("PoorCLICore initialization complete")
            
        except ConfigurationError:
            raise
        except Exception as e:
            logger.exception("Failed to initialize PoorCLICore")
            raise ConfigurationError(f"Initialization failed: {e}")

    async def _ensure_provider_ready(
        self,
        *,
        force_reinitialize: bool = False,
        tool_declarations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        if not force_reinitialize and getattr(self, "_provider_ready", False):
            return
        if getattr(self, "_provider_init_lock", None) is None:
            self._provider_init_lock = asyncio.Lock()

        async with self._provider_init_lock:
            if not force_reinitialize and getattr(self, "_provider_ready", False):
                return
            declarations = (
                list(tool_declarations)
                if tool_declarations is not None
                else (
                    list(getattr(self, "_active_tool_declarations", []) or [])
                    or self._tool_declarations_for_shipping()
                )
            )
            if not provider_has_capability(self.provider, ProviderCapability.TOOL_CALLING):
                declarations = []
            started = time.monotonic()
            await self.provider.initialize(
                tools=declarations,
                system_instruction=self._system_instruction,
            )
            self._provider_ready = True
            self._record_perf_span(
                "core._ensure_provider_ready",
                (time.monotonic() - started) * 1000.0,
                details={
                    "force": bool(force_reinitialize),
                    "toolCount": len(declarations),
                },
            )

    def _schedule_provider_readiness_probe(self) -> None:
        if not self.config or not self._config_manager:
            return
        task = getattr(self, "_provider_probe_task", None)
        if task is not None and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._provider_probe_task = loop.create_task(self._probe_provider_readiness_background())

    async def _probe_provider_readiness_background(self) -> None:
        if not self.config or not self._config_manager:
            return
        try:
            loop = asyncio.get_running_loop()
            provider_status = await loop.run_in_executor(
                None,
                lambda: probe_providers(
                    self._config_manager, self.config,
                    allow_stale=False,
                    background_refresh=False,
                    force_refresh=True,
                ),
            )
        except Exception:
            logger.debug("provider readiness background probe failed", exc_info=True)
            return
        self._provider_readiness_cache = {
            name: dict(payload)
            for name, payload in provider_status.items()
        }
        ready = [name for name, status in provider_status.items() if status.get("ready")]
        avail = [
            name for name, status in provider_status.items()
            if status.get("available") and not status.get("ready")
        ]
        self._pending_events.append(CoreEvent(
            type="progress",
            data={
                "phase": "provider_probe",
                "message": f"providers: {', '.join(ready)} ready" + (f" | {', '.join(avail)} available" if avail else ""),
            },
        ))
        if self.config:
            self._resolved_routing_mode = resolve_routing_mode(
                getattr(self.config.model, "routing_mode", "manual"),
                provider_status,
            )

    def _tone_suffix_for_memory_index(
        self,
        memory_index: str,
        detect_tone_fn: Optional[Callable[[str], str]] = None,
    ) -> str:
        if not self._memory_manager:
            return ""
        index_hash = hashlib.sha256(
            str(memory_index or "").encode("utf-8", errors="replace")
        ).hexdigest()
        if index_hash == self._tone_cache_index_hash:
            return self._tone_cache_suffix
        tone_suffix = ""
        try:
            user_memories = self._memory_manager.list_all(type_filter="user")
            user_content = "\n".join(memory.content for memory in user_memories)
            detector = detect_tone_fn or detect_tone_from_user_memories
            tone_suffix = str(detector(user_content) or "")
        except Exception:
            tone_suffix = ""
        self._tone_cache_index_hash = index_hash
        self._tone_cache_suffix = tone_suffix
        return tone_suffix
    
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
            provider_status = dict(getattr(self, "_provider_readiness_cache", {}) or {})
            if not provider_status:
                self._schedule_provider_readiness_probe()
            ready = [p for p, s in provider_status.items() if s.get("ready")]
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

        if not resolved_api_key and resolved_provider not in KEYLESS_LOCAL_PROVIDER_NAMES:
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






























































    _COST_HISTORY_FILE = Path.home() / ".poor-cli" / "cost_history.json"















    # ── Economy: response cache ───────────────────────────────────────







    # ── Economy: context dedup ────────────────────────────────────────


    # ── Economy: diff-only reads ──────────────────────────────────────


    # ── Economy: idle auto-compact ────────────────────────────────────



    # ── Economy: economy_max_tokens ───────────────────────────────────






































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

        The callback MUST be a coroutine function with signature
        ``async (tool_name: str, tool_args: dict, preview: dict | None) -> dict``.
        Legacy sync callables should be wrapped via
        ``poor_cli.permission_engine._as_async`` at the registration site.
        """
        if callback is not None and not inspect.iscoroutinefunction(callback):
            raise TypeError(
                "permission_callback must be a coroutine function; "
                "wrap legacy sync callbacks via permission_engine._as_async"
            )
        self._permission_callback = callback
        try:
            from .browser_tool import set_browser_permission_callback
            set_browser_permission_callback(callback)
        except Exception:
            pass
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







    # get_provider_info, get_provider_readiness, get_routing_mode,
    # set_routing_mode now live in core_provider_info:ProviderInfoMixin.
