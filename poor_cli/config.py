"""
Configuration management for poor-cli

Handles loading, saving, and validating user configuration from YAML files.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field, fields
from enum import Enum
from poor_cli.exceptions import ConfigurationError, setup_logger
from poor_cli.provider_catalog import all_provider_entries, default_model_for_provider
from poor_cli.economy import EconomyConfig
from poor_cli.retry import RetryConfig
from poor_cli.circuit_breaker import CircuitBreakerConfig
from poor_cli.server.rate_limit import DEFAULT_RPC_RATE_LIMITS

logger = setup_logger(__name__)


class PermissionMode(str, Enum):
    """Permission behavior for potentially unsafe operations."""

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DONT_ASK = "dontAsk"

    # legacy values kept for backward compatibility
    PROMPT = "prompt"
    AUTO_SAFE = "auto-safe"
    DANGER_FULL_ACCESS = "danger-full-access"


_PERMISSION_MODE_ALIASES = {
    "default": PermissionMode.DEFAULT,
    "prompt": PermissionMode.PROMPT,
    "acceptedits": PermissionMode.ACCEPT_EDITS,
    "accept-edits": PermissionMode.ACCEPT_EDITS,
    "accept_edits": PermissionMode.ACCEPT_EDITS,
    "auto-safe": PermissionMode.AUTO_SAFE,
    "plan": PermissionMode.PLAN,
    "bypasspermissions": PermissionMode.BYPASS_PERMISSIONS,
    "bypass-permissions": PermissionMode.BYPASS_PERMISSIONS,
    "bypass_permissions": PermissionMode.BYPASS_PERMISSIONS,
    "dontask": PermissionMode.DONT_ASK,
    "dont-ask": PermissionMode.DONT_ASK,
    "dont_ask": PermissionMode.DONT_ASK,
    "danger-full-access": PermissionMode.DANGER_FULL_ACCESS,
}


def parse_permission_mode(raw_mode: Any) -> PermissionMode:
    """Parse permission mode with Claude-compatible aliases."""
    if isinstance(raw_mode, PermissionMode):
        return raw_mode
    if not isinstance(raw_mode, str):
        raise ConfigurationError("Invalid security.permission_mode type. Expected a string.")
    key = raw_mode.strip()
    if not key:
        raise ConfigurationError("Invalid security.permission_mode value.")
    try:
        return PermissionMode(key)
    except ValueError:
        normalized = key.replace(" ", "").lower()
        resolved = _PERMISSION_MODE_ALIASES.get(normalized)
        if resolved is not None:
            return resolved
        raise ConfigurationError(
            "Invalid security.permission_mode value. "
            "Expected one of: default, acceptEdits, plan, bypassPermissions, dontAsk, "
            "prompt, auto-safe, danger-full-access."
        )


@dataclass
class ProviderConfig:
    """Configuration for a specific provider"""
    name: str  # Provider name
    api_key_env_var: str  # Environment variable for API key
    default_model: str  # Default model to use
    enabled: bool = True  # Whether provider is available
    base_url: Optional[str] = None  # For providers like Ollama


@dataclass
class ModelConfig:
    """Configuration for AI model settings"""
    provider: str = "openai"  # Active provider: gemini, openai, anthropic, local OpenAI-compatible, etc.
    model_name: str = field(default_factory=lambda: default_model_for_provider("openai"))
    routing_mode: str = "manual"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 0.95
    top_k: int = 40
    prompt_caching: bool = True  # inject cache_control on Anthropic system/tools
    # tool-schema shipping strategy for LLM requests:
    #   "all"  — send every registered tool declaration (old behavior)
    #   "core" — send only the core group; extra groups must be activated
    #            explicitly via _activate_tool_groups before use. saves tokens
    #            per turn by trimming the tool menu.
    tool_schema_mode: str = "all"

    # Provider registry
    providers: Dict[str, ProviderConfig] = field(
        default_factory=lambda: {
            entry.name: ProviderConfig(
                name=entry.name,
                api_key_env_var=entry.env_var,
                default_model=entry.default_model,
                base_url=entry.base_url,
            )
            for entry in all_provider_entries()
        }
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelConfig':
        """Create ModelConfig from dictionary with proper provider deserialization"""
        # Make a copy to avoid modifying the input
        data = data.copy()

        # Extract providers data if present
        providers_data = data.pop("providers", None)

        # Create ModelConfig with other fields
        config = cls(**data)

        # Convert providers dict to ProviderConfig objects if provided
        if providers_data:
            merged = dict(config.providers)
            merged.update({
                name: ProviderConfig(**provider_dict) if isinstance(provider_dict, dict) else provider_dict
                for name, provider_dict in providers_data.items()
            })
            config.providers = merged

        return config


@dataclass
class HistoryConfig:
    """Configuration for conversation history"""
    max_turns: int = 50
    auto_save: bool = True
    save_directory: str = "~/.poor-cli/history"
    max_token_limit: int = 100000  # Context window limit
    auto_migrate_legacy_history: bool = True
    regenerate_temperature_bump: float = 0.2

    # History restoration settings
    restore_on_startup: bool = True  # Load previous session on startup
    max_messages_to_restore: int = 20  # How many messages to restore from previous session
    continue_last_session: bool = True  # Continue last session or start new one


@dataclass
class UIConfig:
    """Configuration for user interface"""
    theme: str = "github-light"
    show_token_count: bool = True
    enable_streaming: bool = True
    markdown_rendering: bool = True
    show_tool_calls: bool = True
    verbose_logging: bool = False
    crt_effect: bool = False


@dataclass
class PlanModeConfig:
    """Configuration for plan mode"""
    enabled: bool = True
    auto_plan_threshold: int = 2  # Auto-enable plan for operations affecting N+ files
    require_approval_for_high_risk: bool = True
    show_diff_in_plan: bool = True
    allow_step_modification: bool = True
    default_context_lines: int = 3  # Lines of context in diffs


BUDGET_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "quick_question": {
        "session_max_tokens": 5000,
        "session_max_cost_usd": 0.01,
        "task_max_tokens": 5000,
        "task_max_cost_usd": 0.01,
    },
    "code_review": {
        "session_max_tokens": 30000,
        "session_max_cost_usd": 0.10,
        "task_max_tokens": 15000,
        "task_max_cost_usd": 0.05,
    },
    "deep_refactor": {
        "session_max_tokens": 100000,
        "session_max_cost_usd": 0.50,
        "task_max_tokens": 50000,
        "task_max_cost_usd": 0.25,
    },
    "unlimited": {
        "session_max_tokens": 0,
        "session_max_cost_usd": 0.0,
        "task_max_tokens": 0,
        "task_max_cost_usd": 0.0,
    },
}


@dataclass
class CostGuardrailConfig:
    """Token budget and cost limits."""
    session_max_tokens: int = 0  # max total tokens per session (0 = unlimited)
    session_max_cost_usd: float = 0.0  # max estimated cost per session (0 = unlimited)
    task_max_tokens: int = 0  # max tokens per single task/exec run
    task_max_cost_usd: float = 0.0  # max cost per single task/exec run
    pause_on_limit: bool = True  # pause and prompt user instead of hard-stopping


@dataclass
class FallbackConfig:
    """Provider fallback chain for resilient execution."""
    enabled: bool = False
    chain: list = field(default_factory=list)  # e.g. ["gemini", "openai", "ollama"]
    retry_on_rate_limit: bool = True
    retry_on_server_error: bool = True
    max_fallback_attempts: int = 3
    prefer_cheaper: bool = True # sort fallback chain by cost (cheapest first)


@dataclass
class ProvidersPortabilityConfig:
    """MH9: enforce portability across providers — block stateful-API usage.

    When strict is True (default), provider adapters must NOT rely on any
    server-side state store that cannot be reconstructed from local history.
    This blocks OpenAI Responses API stateful calls, Anthropic Managed Agents,
    and similar lock-in patterns. See docs/HARNESS_PORTABILITY.md.

    Users who explicitly want the stateful variants (for latency, priced
    features, etc.) must flip strict=False and accept the lock-in trade-off.
    """
    strict: bool = True
    # per-provider opt-in overrides when strict is True — maps provider name to
    # a list of feature codes the user explicitly allowed (e.g. "openai_responses_stateful")
    allowed_stateful_features: Dict[str, list] = field(default_factory=dict)


@dataclass
class ContextCompressionConfig:
    """Context compression / summarization settings."""
    enabled: bool = True
    compress_after_turns: int = 12  # compress history older than N turns
    target_token_ratio: float = 0.3  # compress to ~30% of original tokens
    preserve_recent_turns: int = 8  # always keep last N turns uncompressed
    token_threshold_for_llm_compact: float = 0.8  # auto LLM compact at this fraction of model context
    auto_compact_threshold: float = 0.7  # auto compact when utilization exceeds this fraction
    auto_compact_target: float = 0.4  # compact down to this fraction of model context
    preserve_transcripts: bool = True  # save raw history before compaction
    transcript_dir: str = ".poor-cli/transcripts"  # relative to repo root


@dataclass
class ContextConfig:
    """Context assembly feature flags."""
    safe_pretokenization: bool = False  # v1 default off; v2 flip requires real-world parse/edit telemetry
    # CB1: send a diff against last-sent text instead of the full file when the
    # same (file_path, pinned_context_hash) re-appears within TTL. Default off
    # because diff-mode changes what the model sees; flip on after telemetry.
    diff_of_diff_cache: bool = False
    diff_of_diff_min_chars: int = 800   # only cache files larger than this
    diff_of_diff_ttl_seconds: float = 21600.0  # 6h — matches DiffCache default
    diff_of_diff_cache_path: str = ""   # override store path (tests + sandbox)


@dataclass
class OutputTruncationConfig:
    """Tool output truncation for context efficiency."""
    enabled: bool = True
    max_output_chars: int = 32000  # truncate tool output beyond this
    max_output_lines: int = 500  # truncate beyond this many lines
    show_truncation_notice: bool = True


@dataclass
class RtkLiteConfig:
    enabled: bool = True
    tiny_output_bytes: int = 300


@dataclass
class AgenticConfig:
    """Configuration for agentic loop behavior"""
    max_iterations: int = 25 # max tool-call round-trips per request
    max_parallel_tool_calls: int = 6  # cap for concurrent read-only tool calls
    max_tool_schema_tokens: int = 0  # cap schema tokens for prompt-level tool activation (0 = unlimited)
    max_tool_result_chars_per_turn: int = 60000  # cap tool-result payload per turn
    overflow_threshold_chars: int = 30000  # single result overflow to temp file
    overflow_dir: str = ".poor-cli/overflow"  # relative to repo root
    context_pressure_stop_ratio: float = 0.2  # stop if remaining context < 20%
    context_pressure_warn_ratio: float = 0.5  # warn if remaining context < 50%
    path_scoped_approval: bool = True  # remember approved write paths per session
    sub_agent_default_denied_tools: list = field(default_factory=lambda: [
        "write_file", "edit_file", "delete_file", "bash", "git_commit",
        "git_add", "apply_patch_unified", "move_file", "copy_file",
    ])
    auto_approve_tools: list = field(default_factory=lambda: [
        "read_file", "glob_files", "grep_files", "git_status_diff",
        "list_directory", "diff_files",
    ])
    deny_patterns: list = field(default_factory=lambda: [
        "rm -rf", "sudo", "chmod 777",
    ])
    sub_agent_max_depth: int = 2  # max sub-agent recursion depth
    sub_agent_max_iterations: int = 10  # max iterations per sub-agent
    sub_agent_timeout: float = 120.0  # sub-agent timeout in seconds
    auto_lint: bool = True  # run lint after file mutations and feed errors back to LLM
    auto_lint_timeout: int = 30  # lint command timeout in seconds
    architect_mode: bool = False  # dual-model: expensive for reasoning, cheap for editing
    architect_provider: str = "" # provider for reasoning (e.g. "anthropic")
    architect_model: str = "" # model for reasoning (e.g. "claude-sonnet-4-20250514")
    editor_provider: str = "" # provider for editing (e.g. "gemini")
    editor_model: str = "" # model for editing (e.g. "gemini-2.5-flash")
    auto_commit: bool = False # auto-commit file mutations with descriptive messages


@dataclass
class CheckpointConfig:
    """Configuration for checkpoint system"""
    enabled: bool = True  # Enable automatic checkpoints
    auto_checkpoint_before_write: bool = True
    auto_checkpoint_before_edit: bool = True
    auto_checkpoint_before_delete: bool = True
    max_checkpoints: int = 50  # Maximum checkpoints to keep
    checkpoint_on_session_start: bool = False  # Create checkpoint at start
    checkpoint_on_session_end: bool = False  # Create checkpoint at end
    max_age_hours: int = 0  # prune checkpoints older than N hours (0 = disabled)
    max_disk_mb: int = 0  # prune when total disk exceeds N MB (0 = disabled)


@dataclass
class DiffReviewConfig:
    mode: str = "review"
    layout: str = "unified"
    panel_position: str = "right"
    panel_width: int = 90
    auto_open: bool = True
    risky_paths: list = field(default_factory=lambda: [
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "/main\\.",
        "/__init__\\.",
    ])
    risky_line_threshold: int = 50


@dataclass
class AuditConfig:
    """Audit log rotation and archive settings."""
    max_size_mb: int = 100
    max_rows_live: int = 100000
    max_age_days_live: int = 90
    archive_chunk_size: int = 10000
    archive_dir: str = ".poor-cli/audit/archive/"


@dataclass
class SecurityConfig:
    """Configuration for security settings"""
    safe_commands: list = field(default_factory=lambda: [
        "pwd", "ls", "echo", "cat", "head", "tail",
        "grep", "find", "which", "whoami", "date"
    ])
    trusted_roots: list = field(default_factory=lambda: [])
    enforce_trusted_workspace: bool = True
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    require_permission_for_write: bool = True
    require_permission_for_bash: bool = True
    enable_bash_execution: bool = True
    max_bash_timeout_seconds: int = 60
    max_file_size_mb: int = 100
    allowed_file_extensions: list = field(default_factory=lambda: [])  # Empty = all allowed
    unicode_scanning: bool = True  # scan file content for dangerous unicode chars

    def to_dict(self) -> Dict[str, Any]:
        """Serialize security config with enum values."""
        data = asdict(self)
        data["permission_mode"] = self.permission_mode.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityConfig":
        """Create SecurityConfig with validated permission mode."""
        data = data.copy()
        raw_mode = data.get("permission_mode", PermissionMode.DEFAULT)
        mode = parse_permission_mode(raw_mode)

        data["permission_mode"] = mode
        return cls(**data)


@dataclass
class ToolConfig:
    """Configuration for tool behavior"""
    enable_git_tools: bool = True
    enable_file_tools: bool = True
    enable_network_tools: bool = True
    backup_before_edit: bool = True
    git_auto_detect: bool = True
    circuit_breakers: bool = True
    idempotency: bool = True
    auto_checkpoint: bool = True
    rate_limits: bool = True


@dataclass
class SandboxConfig:
    """Capability-based sandbox defaults."""

    default_preset: str = "workspace-write"
    persistent_allow_capabilities: list = field(default_factory=list)


@dataclass
class TasksConfig:
    """Background task runner settings."""

    enabled: bool = True
    auto_start_read_only: bool = True
    auto_start_workspace_write: bool = False
    inbox_limit: int = 20


@dataclass
class SkillsConfig:
    """Skill discovery settings."""

    search_paths: list = field(default_factory=list)


@dataclass
class RepoIndexConfig:
    """Repo knowledge-graph indexing settings."""
    enabled: bool = True
    auto_index_on_start: bool = True
    max_files: int = 10000
    incremental: bool = True


@dataclass
class KVCacheConfig:
    """Position-independent KV cache for local inference (vLLM/LMCache)."""
    enabled: bool = False # off by default
    backend: str = "lmcache" # "lmcache" or "vllm"
    cache_dir: str = ".poor-cli/kv_cache/"
    precompute_on_startup: bool = False
    max_cache_size_mb: int = 5000 # 5GB default cap
    ttl_seconds: int = 86400 # 24h
    vllm_api_base: str = "http://localhost:8000" # vLLM OpenAI-compat endpoint


@dataclass
class ResearchModuleConfig:
    """Feature flag for one research module."""
    enabled: bool = False


@dataclass
class ResearchConfig:
    """Research module flags. All default off."""
    latent_communication: ResearchModuleConfig = field(default_factory=ResearchModuleConfig)
    neural_code_encoder: ResearchModuleConfig = field(default_factory=ResearchModuleConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchConfig':
        def module_cfg(name: str) -> ResearchModuleConfig:
            raw = data.get(name, {})
            if isinstance(raw, bool):
                return ResearchModuleConfig(enabled=raw)
            if isinstance(raw, dict):
                return ResearchModuleConfig(**raw)
            return ResearchModuleConfig()
        return cls(
            latent_communication=module_cfg("latent_communication"),
            neural_code_encoder=module_cfg("neural_code_encoder"),
        )


@dataclass
class WorkflowConfig:
    """Workflow template defaults and overrides."""

    default_workflow: str = "implement"
    defaults: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class McpRegistryConfig:
    enabled: bool = False


@dataclass
class McpConfig:
    registry: McpRegistryConfig = field(default_factory=McpRegistryConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'McpConfig':
        if not isinstance(data, dict):
            return cls()
        registry_data = data.get("registry", {})
        registry = McpRegistryConfig(**registry_data) if isinstance(registry_data, dict) else McpRegistryConfig()
        return cls(registry=registry)


@dataclass
class Config:
    """Main configuration class"""
    model: ModelConfig = field(default_factory=ModelConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    tasks: TasksConfig = field(default_factory=TasksConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    plan_mode: PlanModeConfig = field(default_factory=PlanModeConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    diff_review: DiffReviewConfig = field(default_factory=DiffReviewConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    agentic: AgenticConfig = field(default_factory=AgenticConfig)
    cost_guardrails: CostGuardrailConfig = field(default_factory=CostGuardrailConfig)
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    providers_portability: ProvidersPortabilityConfig = field(default_factory=ProvidersPortabilityConfig)
    context_compression: ContextCompressionConfig = field(default_factory=ContextCompressionConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    output_truncation: OutputTruncationConfig = field(default_factory=OutputTruncationConfig)
    rtk_lite: RtkLiteConfig = field(default_factory=RtkLiteConfig)
    repo_index: RepoIndexConfig = field(default_factory=RepoIndexConfig)
    kv_cache: KVCacheConfig = field(default_factory=KVCacheConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    economy: EconomyConfig = field(default_factory=EconomyConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    rpc_rate_limits: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        key: dict(value) for key, value in DEFAULT_RPC_RATE_LIMITS.items()
    })

    # auto-feedback: run lint/test after file mutations
    _auto_feedback_enabled: bool = False

    # API keys stored separately (not in config file)
    api_keys: Dict[str, str] = field(default_factory=dict)
    mcp_servers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary, excluding API keys"""
        config_dict = {
            "model": asdict(self.model),
            "history": asdict(self.history),
            "ui": asdict(self.ui),
            "security": self.security.to_dict(),
            "tools": asdict(self.tools),
            "sandbox": asdict(self.sandbox),
            "tasks": asdict(self.tasks),
            "skills": asdict(self.skills),
            "workflow": asdict(self.workflow),
            "plan_mode": asdict(self.plan_mode),
            "checkpoint": asdict(self.checkpoint),
            "diff_review": asdict(self.diff_review),
            "audit": asdict(self.audit),
            "agentic": asdict(self.agentic),
            "cost_guardrails": asdict(self.cost_guardrails),
            "fallback": asdict(self.fallback),
            "providers_portability": asdict(self.providers_portability),
            "context_compression": asdict(self.context_compression),
            "context": asdict(self.context),
            "output_truncation": asdict(self.output_truncation),
            "rtk_lite": asdict(self.rtk_lite),
            "repo_index": asdict(self.repo_index),
            "kv_cache": asdict(self.kv_cache),
            "research": asdict(self.research),
            "mcp": asdict(self.mcp),
            "economy": asdict(self.economy),
            "retry": {k: v for k, v in asdict(self.retry).items() if k != "retryable_exceptions"},
            "circuit_breaker": asdict(self.circuit_breaker),
            "rpc_rate_limits": self.rpc_rate_limits,
            "mcp_servers": self.mcp_servers,
        }
        return config_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create config from dictionary"""
        return cls(
            model=ModelConfig.from_dict(data.get("model", {})),
            history=HistoryConfig(**data.get("history", {})),
            ui=UIConfig(**data.get("ui", {})),
            security=SecurityConfig.from_dict(data.get("security", {})),
            tools=ToolConfig(**data.get("tools", {})),
            sandbox=SandboxConfig(**data.get("sandbox", {})),
            tasks=TasksConfig(**data.get("tasks", {})),
            skills=SkillsConfig(**data.get("skills", {})),
            workflow=WorkflowConfig(**data.get("workflow", {})),
            plan_mode=PlanModeConfig(**data.get("plan_mode", {})),
            checkpoint=CheckpointConfig(**data.get("checkpoint", {})),
            diff_review=DiffReviewConfig(**data.get("diff_review", {})),
            audit=AuditConfig(**data.get("audit", {})),
            agentic=AgenticConfig(**data.get("agentic", {})),
            cost_guardrails=CostGuardrailConfig(**data.get("cost_guardrails", {})),
            fallback=FallbackConfig(**data.get("fallback", {})),
            context_compression=ContextCompressionConfig(**data.get("context_compression", {})),
            context=ContextConfig(**data.get("context", {})),
            output_truncation=OutputTruncationConfig(**data.get("output_truncation", {})),
            rtk_lite=RtkLiteConfig(**data.get("rtk_lite", {})),
            repo_index=RepoIndexConfig(**data.get("repo_index", {})),
            kv_cache=KVCacheConfig(**data.get("kv_cache", {})),
            research=ResearchConfig.from_dict(data.get("research", {})),
            mcp=McpConfig.from_dict(data.get("mcp", {})),
            economy=EconomyConfig(**data.get("economy", {})),
            retry=RetryConfig(**{k: v for k, v in data.get("retry", {}).items() if k != "retryable_exceptions"}),
            circuit_breaker=CircuitBreakerConfig(**data.get("circuit_breaker", {})),
            rpc_rate_limits=data.get(
                "rpc_rate_limits",
                {key: dict(value) for key, value in DEFAULT_RPC_RATE_LIMITS.items()},
            ),
            api_keys=data.get("api_keys", {}) if isinstance(data.get("api_keys", {}), dict) else {},
            mcp_servers=data.get("mcp_servers", {}),
        )


class ConfigManager:
    """Manages configuration loading, saving, and validation"""

    DEFAULT_CONFIG_DIR = Path.home() / ".poor-cli"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize config manager

        Args:
            config_path: Path to config file (defaults to ~/.poor-cli/config.yaml)
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_FILE
        self.config: Config = Config()

    def load(self) -> Config:
        """Load configuration from file

        Returns:
            Config object

        Raises:
            ConfigurationError: If config file is invalid
        """
        try:
            if not self.config_path.exists():
                logger.info(f"Config file not found at {self.config_path}, using defaults")
                self._create_default_config()
                return self.config

            logger.info(f"Loading configuration from {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None:
                logger.warning("Config file is empty, using defaults")
                return self.config

            self.config = Config.from_dict(data)
            self._apply_repo_overrides()

            # Expand paths
            self.config.history.save_directory = str(
                Path(self.config.history.save_directory).expanduser()
            )

            logger.info("Configuration loaded successfully")
            return self.config

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}")

    def _apply_repo_overrides(self) -> None:
        """Apply repository-local overrides from .poor-cli/config.yaml if present."""
        repo_config_path = Path.cwd() / ".poor-cli" / "config.yaml"
        if not repo_config_path.exists():
            return

        # trust check: skip repo config in untrusted repos
        try:
            from .trust import TrustManager
            if not TrustManager().is_trusted():
                logger.warning("untrusted repo — skipping .poor-cli/config.yaml (run /trust to enable)")
                return
        except Exception:
            pass # trust module unavailable, allow config

        try:
            with open(repo_config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None or not isinstance(data, dict):
                logger.warning("Repo config override file is empty or invalid, skipping")
                return

            self._deep_merge(self.config, data)
            logger.info(f"Applied repo-level config overrides from {repo_config_path}")
        except Exception as e:
            logger.warning(f"Failed to apply repo-level config overrides: {e}")

    @staticmethod
    def _deep_merge(config: Config, overrides: Dict[str, Any]) -> None:
        """Merge known top-level config sections into Config in-place."""
        valid_sections = {
            "model",
            "history",
            "ui",
            "security",
            "tools",
            "sandbox",
            "tasks",
            "skills",
            "workflow",
            "plan_mode",
            "checkpoint",
            "diff_review",
            "audit",
            "agentic",
            "cost_guardrails",
            "fallback",
            "context_compression",
            "context",
            "output_truncation",
            "kv_cache",
            "research",
            "mcp",
            "economy",
            "mcp_servers",
            "file_cache",
            "lsp",
            "latent_comm",
            "prompt_library",
            "rpc_rate_limits",
        }

        for section_name, section_overrides in overrides.items():
            if section_name not in valid_sections:
                logger.warning(f"Unknown repo override section: {section_name}")
                continue

            if section_name == "mcp_servers":
                if not isinstance(section_overrides, dict):
                    logger.warning("mcp_servers override must be a mapping, skipping")
                    continue
                merged = dict(config.mcp_servers)
                merged.update(section_overrides)
                config.mcp_servers = merged
                continue

            if section_name == "rpc_rate_limits":
                if not isinstance(section_overrides, dict):
                    logger.warning("rpc_rate_limits override must be a mapping, skipping")
                    continue
                config.rpc_rate_limits = section_overrides
                continue

            if not isinstance(section_overrides, dict):
                logger.warning(
                    f"Override section '{section_name}' must be a mapping, skipping"
                )
                continue

            section_obj = getattr(config, section_name, None)
            if section_obj is None:
                logger.warning(f"Missing config section '{section_name}', skipping")
                continue

            if hasattr(section_obj, "to_dict") and callable(section_obj.to_dict):
                merged_data: Dict[str, Any] = section_obj.to_dict()
            else:
                merged_data = asdict(section_obj)

            for key, value in section_overrides.items():
                if key not in merged_data:
                    logger.warning(f"Unknown key in {section_name} override: {key}")
                    continue
                merged_data[key] = value

            section_cls = section_obj.__class__
            if hasattr(section_cls, "from_dict") and callable(section_cls.from_dict):
                new_section = section_cls.from_dict(merged_data)
            else:
                new_section = section_cls(**merged_data)

            setattr(config, section_name, new_section)

    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file

        Args:
            config: Config object to save (uses current if None)

        Raises:
            ConfigurationError: If saving fails
        """
        try:
            if config:
                self.config = config

            # Create config directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict and save
            config_dict = self.config.to_dict()

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Configuration saved to {self.config_path}")

        except Exception as e:
            raise ConfigurationError(f"Failed to save config: {e}")

    def _create_default_config(self) -> None:
        """Create default configuration file"""
        try:
            logger.info("Creating default configuration file")
            self.save()
            logger.info(f"Default config created at {self.config_path}")
        except Exception as e:
            logger.warning(f"Failed to create default config: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation path

        Args:
            key_path: Dot-separated path (e.g., "model.temperature")
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        try:
            keys = key_path.split('.')
            value = self.config

            for key in keys:
                if hasattr(value, key):
                    value = getattr(value, key)
                else:
                    return default

            return value

        except Exception:
            return default

    def set(self, key_path: str, value: Any) -> None:
        """Set configuration value by dot-notation path

        Args:
            key_path: Dot-separated path (e.g., "model.temperature")
            value: Value to set

        Raises:
            ConfigurationError: If path is invalid
        """
        try:
            keys = key_path.split('.')
            obj = self.config

            # Navigate to parent object
            for key in keys[:-1]:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    raise ConfigurationError(f"Invalid config path: {key_path}")

            # Set the final value
            final_key = keys[-1]
            if hasattr(obj, final_key):
                setattr(obj, final_key, value)
            else:
                raise ConfigurationError(f"Invalid config key: {final_key}")

        except Exception as e:
            raise ConfigurationError(f"Failed to set config value: {e}")

    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self.config = Config()
        logger.info("Configuration reset to defaults")

    def validate(self) -> bool:
        """Validate current configuration

        Returns:
            True if valid

        Raises:
            ConfigurationError: If validation fails
        """
        # Validate model config
        if self.config.model.temperature < 0 or self.config.model.temperature > 2:
            raise ConfigurationError("Temperature must be between 0 and 2")

        if self.config.model.top_p < 0 or self.config.model.top_p > 1:
            raise ConfigurationError("top_p must be between 0 and 1")

        # Validate history config
        if self.config.history.max_turns < 1:
            raise ConfigurationError("max_turns must be at least 1")

        # Validate agentic config
        if self.config.agentic.max_iterations < 1:
            raise ConfigurationError("agentic.max_iterations must be at least 1")
        if self.config.agentic.max_parallel_tool_calls < 1:
            raise ConfigurationError("agentic.max_parallel_tool_calls must be at least 1")
        if self.config.agentic.max_parallel_tool_calls > 32:
            raise ConfigurationError("agentic.max_parallel_tool_calls must be at most 32")
        if self.config.agentic.max_tool_schema_tokens < 0:
            raise ConfigurationError("agentic.max_tool_schema_tokens must be non-negative")
        if self.config.agentic.max_tool_schema_tokens > 500000:
            raise ConfigurationError("agentic.max_tool_schema_tokens must be at most 500000")
        if self.config.agentic.max_tool_result_chars_per_turn < 1000:
            raise ConfigurationError("agentic.max_tool_result_chars_per_turn must be at least 1000")
        if self.config.agentic.max_tool_result_chars_per_turn > 500000:
            raise ConfigurationError("agentic.max_tool_result_chars_per_turn must be at most 500000")

        # Validate security config
        if self.config.security.max_file_size_mb < 1:
            raise ConfigurationError("max_file_size_mb must be at least 1")
        if self.config.security.max_bash_timeout_seconds < 1:
            raise ConfigurationError("max_bash_timeout_seconds must be at least 1")

        # Validate audit config
        if self.config.audit.max_size_mb < 0:
            raise ConfigurationError("audit.max_size_mb must be non-negative")
        if self.config.audit.max_rows_live < 1:
            raise ConfigurationError("audit.max_rows_live must be at least 1")
        if self.config.audit.max_age_days_live < 0:
            raise ConfigurationError("audit.max_age_days_live must be non-negative")
        if self.config.audit.archive_chunk_size < 1:
            raise ConfigurationError("audit.archive_chunk_size must be at least 1")

        logger.info("Configuration validated successfully")
        return True

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for provider from keyring, environment, or config

        Args:
            provider: Provider name (gemini, openai, anthropic, claude, ollama)

        Returns:
            API key or None
        """
        return self.get_api_key_info(provider)["key"]

    def get_api_key_info(self, provider: str) -> Dict[str, Optional[str]]:
        """Get API key plus non-secret source metadata."""
        provider = provider.lower()

        if provider == "claude":
            provider = "anthropic"

        provider_config = self.config.model.providers.get(provider)
        if not provider_config:
            logger.warning(f"Unknown provider: {provider}")
            return {"key": None, "source": "none", "env_var": None}

        env_var = provider_config.api_key_env_var
        from poor_cli.credentials import get_credential_store

        lookup = get_credential_store().get_with_source(
            provider,
            env_var=env_var,
            config_keys=getattr(self.config, "api_keys", {}),
        )
        if lookup.key:
            return {"key": lookup.key, "source": lookup.source, "env_var": env_var}

        try:
            secure_store_file = Path.home() / ".poor-cli" / "keys" / "encrypted_keys.json"
            if not secure_store_file.exists():
                return {"key": None, "source": "none", "env_var": env_var}

            from poor_cli.api_key_manager import get_api_key_manager

            key = get_api_key_manager().get_key(provider)
            if key:
                return {"key": key, "source": "legacy-encrypted", "env_var": env_var}
        except Exception as e:
            logger.debug(f"Secure key store lookup failed for {provider}: {e}")

        return {"key": None, "source": "none", "env_var": env_var}

    def get_provider_config(self, provider: str) -> Optional['ProviderConfig']:
        """Get configuration for a specific provider

        Args:
            provider: Provider name

        Returns:
            ProviderConfig or None
        """
        provider = provider.lower()
        if provider == "claude":
            provider = "anthropic"

        return self.config.model.providers.get(provider)

    def display_config(self) -> str:
        """Get formatted configuration display

        Returns:
            Formatted config string
        """
        config_dict = self.config.to_dict()
        return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


def get_config() -> Config:
    """Get current configuration"""
    return get_config_manager().config
