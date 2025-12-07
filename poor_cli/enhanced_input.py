"""
Enhanced input handling with prompt_toolkit
Provides smart history and file path autocomplete
"""

import os
from pathlib import Path
from typing import Optional, Iterable
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import PathCompleter, Completer, Completion, merge_completers
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.document import Document


class CommandCompleter(Completer):
    """Completer for poor-cli commands"""

    COMMANDS = [
        '/help', '/quit', '/exit', '/clear', '/clear-output', '/history',
        '/sessions', '/new-session', '/retry', '/search', '/edit-last', '/copy',
        '/checkpoints', '/checkpoint', '/save', '/rewind', '/undo', '/restore', '/diff',
        '/provider', '/providers', '/switch', '/export', '/config', '/verbose',
        '/plan-mode', '/cost', '/model-info'
    ]

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Get command completions"""
        text = document.text_before_cursor

        # Only complete if we're at the start of the line and typing a command
        if text.startswith('/'):
            word = text
            for cmd in self.COMMANDS:
                if cmd.startswith(word):
                    yield Completion(
                        cmd,
                        start_position=-len(word),
                        display=cmd,
                        display_meta='command'
                    )


class SmartCompleter(Completer):
    """Smart completer that combines command and file path completion"""

    def __init__(self):
        self.command_completer = CommandCompleter()
        self.path_completer = PathCompleter(expanduser=True, file_filter=None, only_directories=False)

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Get completions based on context"""
        text = document.text_before_cursor

        # If typing a command, use command completer
        if text.lstrip().startswith('/'):
            yield from self.command_completer.get_completions(document, complete_event)
        else:
            # Otherwise, use file path completer
            yield from self.path_completer.get_completions(document, complete_event)


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

        # Create smart completer
        self.smart_completer = SmartCompleter()

        # Create prompt session with file history
        self.session = PromptSession(
            history=FileHistory(history_file)
        )

    async def get_input(self, prompt_text: str = "> ", enable_completer: bool = False) -> str:
        """Get user input with history navigation

        Args:
            prompt_text: The prompt to display
            enable_completer: Whether to enable smart completion (commands + file paths)

        Returns:
            User input string
        """
        # Set up completer if requested
        completer = None
        if enable_completer:
            completer = self.smart_completer

        # Get input with history support
        try:
            # prompt_toolkit's prompt() is synchronous, but we can call it from async context
            result = await self.session.prompt_async(
                prompt_text,
                completer=completer,
                complete_while_typing=False,  # Only complete on Tab, not while typing
            )
            return result
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+D or Ctrl+C
            raise

    def get_input_sync(self, prompt_text: str = "> ", enable_completer: bool = False) -> str:
        """Get user input synchronously (for non-async contexts)

        Args:
            prompt_text: The prompt to display
            enable_completer: Whether to enable smart completion (commands + file paths)

        Returns:
            User input string
        """
        # Set up completer if requested
        completer = None
        if enable_completer:
            completer = self.smart_completer

        # Get input with history support
        try:
            result = self.session.prompt(
                prompt_text,
                completer=completer,
                complete_while_typing=False,  # Only complete on Tab, not while typing
            )
            return result
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+D or Ctrl+C
            raise
