"""
Enhanced input handling with prompt_toolkit
Provides smart history and file path autocomplete
"""

import os
from pathlib import Path
from typing import Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import PathCompleter, Completer, Completion
from prompt_toolkit.formatted_text import HTML


class EnhancedInputManager:
    """Manages enhanced input with history and autocompletion"""

    def __init__(self, history_file: Optional[str] = None):
        """Initialize the enhanced input manager

        Args:
            history_file: Path to history file. If None, uses default location.
        """
        # Set up history file
        if history_file is None:
            config_dir = Path.home() / ".poor-cli"
            config_dir.mkdir(exist_ok=True)
            history_file = str(config_dir / "prompt_history.txt")

        self.history_file = history_file

        # Create prompt session with file history
        self.session = PromptSession(
            history=FileHistory(history_file)
        )

    async def get_input(self, prompt_text: str = "> ", enable_completer: bool = False) -> str:
        """Get user input with history navigation

        Args:
            prompt_text: The prompt to display
            enable_completer: Whether to enable file path completion

        Returns:
            User input string
        """
        # Set up completer if requested
        completer = None
        if enable_completer:
            completer = PathCompleter(expanduser=True)

        # Get input with history support
        try:
            # prompt_toolkit's prompt() is synchronous, but we can call it from async context
            result = await self.session.prompt_async(
                HTML(f"<ansicyan>{prompt_text}</ansicyan>"),
                completer=completer,
                complete_while_typing=True if completer else False,
            )
            return result
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+D or Ctrl+C
            raise

    def get_input_sync(self, prompt_text: str = "> ", enable_completer: bool = False) -> str:
        """Get user input synchronously (for non-async contexts)

        Args:
            prompt_text: The prompt to display
            enable_completer: Whether to enable file path completion

        Returns:
            User input string
        """
        # Set up completer if requested
        completer = None
        if enable_completer:
            completer = PathCompleter(expanduser=True)

        # Get input with history support
        try:
            result = self.session.prompt(
                prompt_text,
                completer=completer,
                complete_while_typing=True if completer else False,
            )
            return result
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+D or Ctrl+C
            raise
