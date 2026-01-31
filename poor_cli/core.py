"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine that can be used by CLI, Neovim, VSCode, etc.
It separates the core AI functionality from any specific UI implementation.
"""

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from .config import ConfigManager, Config
from .providers.base import BaseProvider, ProviderResponse, FunctionCall
from .providers.provider_factory import ProviderFactory
from .tools_async import ToolRegistryAsync
from .checkpoint import CheckpointManager
from .history import HistoryManager
from .exceptions import (
    PoorCLIError,
    ConfigurationError,
    setup_logger,
)

logger = setup_logger(__name__)


class PoorCLICore:
    """
    Headless AI coding assistant engine.
    
    This is the core wrapper layer that can be used by any UI:
    - CLI (repl_async.py)
    - Neovim plugin (via JSON-RPC server)
    - VSCode extension (via HTTP server)
    - Any other integration
    
    Attributes:
        provider: The AI provider (Gemini, OpenAI, Claude, Ollama)
        tool_registry: Registry of available tools
        history_manager: Conversation history manager
        checkpoint_manager: File checkpoint/undo system
        config: Configuration object
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize PoorCLICore with optional config path.
        
        Args:
            config_path: Optional path to config file. If None, uses default.
        """
        self.provider: Optional[BaseProvider] = None
        self.tool_registry: Optional[ToolRegistryAsync] = None
        self.history_manager: Optional[HistoryManager] = None
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.config: Optional[Config] = None
        self._config_manager: Optional[ConfigManager] = None
        self._config_path = config_path
        self._initialized = False
        self._system_instruction: Optional[str] = None
        
        # Permission callback for file operations
        # Set this to a callable(tool_name: str, tool_args: dict) -> Awaitable[bool]
        self._permission_callback: Optional[Callable[[str, Dict], Any]] = None
        
        logger.info("PoorCLICore instance created")
