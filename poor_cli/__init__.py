"""
poor-cli: A CLI tool for AI-powered task automation

Features:
- Multiple AI provider support (Gemini, OpenAI, Claude, Ollama)
- Async REPL interface with streaming
- Plan mode for previewing AI operations
- Checkpoint system for version control
- Diff preview before applying changes
- Transactional execution with automatic rollback
- Performance optimizations (caching, async operations, connection pooling)
- Security features (audit logging, command validation, encrypted API keys)
- Comprehensive error handling and recovery
"""

__version__ = "0.4.0"

from .repl_async import PoorCLIAsync
from .core import PoorCLICore
from .exceptions import PoorCLIError
from .checkpoint import CheckpointManager, Checkpoint
from .async_checkpoint import AsyncCheckpointManager
from .checkpoint_validation import CheckpointValidator
from .plan_mode import ExecutionPlan, PlanStep
from .plan_executor import PlanExecutor
from .transactional_plan import TransactionalPlanExecutor
from .diff_preview import DiffPreview
from .file_cache import FileCache, get_file_cache
from .audit_log import AuditLogger, get_audit_logger
from .command_validator import CommandValidator, get_command_validator
from .api_key_manager import APIKeyManager, get_api_key_manager

__all__ = [
    "PoorCLIAsync",
    "PoorCLICore",
    "PoorCLIError",
    "CheckpointManager",
    "AsyncCheckpointManager",
    "CheckpointValidator",
    "Checkpoint",
    "ExecutionPlan",
    "PlanStep",
    "PlanExecutor",
    "TransactionalPlanExecutor",
    "DiffPreview",
    "FileCache",
    "get_file_cache",
    "AuditLogger",
    "get_audit_logger",
    "CommandValidator",
    "get_command_validator",
    "APIKeyManager",
    "get_api_key_manager",
    "__version__"
]
