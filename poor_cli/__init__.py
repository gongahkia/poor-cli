"""
poor-cli: A CLI tool for AI-powered task automation

Features:
- Multiple AI provider support (Gemini, OpenAI, Claude, Ollama)
- Async REPL interface with streaming
- Plan mode for previewing AI operations
- Checkpoint system for version control
- Diff preview before applying changes
- Transactional execution with automatic rollback
- Performance optimizations (caching, async operations)
"""

__version__ = "0.3.0"

from .repl_async import PoorCLIAsync
from .exceptions import PoorCLIError
from .checkpoint import CheckpointManager, Checkpoint
from .async_checkpoint import AsyncCheckpointManager
from .checkpoint_validation import CheckpointValidator
from .plan_mode import ExecutionPlan, PlanStep
from .plan_executor import PlanExecutor
from .transactional_plan import TransactionalPlanExecutor
from .diff_preview import DiffPreview
from .file_cache import FileCache, get_file_cache

__all__ = [
    "PoorCLIAsync",
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
    "__version__"
]
