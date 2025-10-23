"""
poor-cli: A CLI tool for AI-powered task automation

Features:
- Multiple AI provider support (Gemini, OpenAI, Claude, Ollama)
- Async REPL interface with streaming
- Plan mode for previewing AI operations
- Checkpoint system for version control
- Diff preview before applying changes
"""

__version__ = "0.3.0"

from .repl_async import PoorCLIAsync
from .exceptions import PoorCLIError
from .checkpoint import CheckpointManager, Checkpoint
from .plan_mode import ExecutionPlan, PlanStep
from .diff_preview import DiffPreview

__all__ = [
    "PoorCLIAsync",
    "PoorCLIError",
    "CheckpointManager",
    "Checkpoint",
    "ExecutionPlan",
    "PlanStep",
    "DiffPreview",
    "__version__"
]
