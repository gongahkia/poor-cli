"""
Enhanced input handling with prompt_toolkit
Provides smart history, slash-command suggestions, and file path autocomplete
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory


@dataclass(frozen=True)
class SlashCommandSpec:
    """Metadata for a slash command shown in completion UI."""

    command: str
    description: str
    recommended: bool = False


class CommandCompleter(Completer):
    """Completer for poor-cli slash commands."""

    COMMAND_SPECS = [
        SlashCommandSpec("/help", "Show all available commands", recommended=True),
        SlashCommandSpec("/review", "Review code or staged diff", recommended=True),
        SlashCommandSpec("/test", "Generate tests for a file", recommended=True),
        SlashCommandSpec("/provider", "Show active provider", recommended=True),
        SlashCommandSpec("/switch", "Switch provider/model", recommended=True),
        SlashCommandSpec("/history", "Show recent messages", recommended=True),
        SlashCommandSpec("/new-session", "Start a fresh session", recommended=True),
        SlashCommandSpec("/permission-mode", "Set permission mode", recommended=True),
        SlashCommandSpec("/quit", "Exit the REPL"),
        SlashCommandSpec("/exit", "Exit the REPL (alias)"),
        SlashCommandSpec("/clear", "Clear conversation history"),
        SlashCommandSpec("/clear-output", "Clear screen, keep history"),
        SlashCommandSpec("/sessions", "List previous sessions"),
        SlashCommandSpec("/retry", "Retry last request"),
        SlashCommandSpec("/search", "Search conversation history"),
        SlashCommandSpec("/edit-last", "Edit and resend last request"),
        SlashCommandSpec("/copy", "Copy last assistant response"),
        SlashCommandSpec("/checkpoints", "List checkpoints"),
        SlashCommandSpec("/checkpoint", "Create checkpoint"),
        SlashCommandSpec("/save", "Create checkpoint (alias)"),
        SlashCommandSpec("/rewind", "Restore checkpoint"),
        SlashCommandSpec("/undo", "Restore latest checkpoint"),
        SlashCommandSpec("/restore", "Restore latest checkpoint (alias)"),
        SlashCommandSpec("/diff", "Compare two files"),
        SlashCommandSpec("/providers", "List providers and models"),
        SlashCommandSpec("/export", "Export conversation"),
        SlashCommandSpec("/config", "Show active configuration"),
        SlashCommandSpec("/verbose", "Toggle verbose logging"),
        SlashCommandSpec("/plan-mode", "Toggle plan mode"),
        SlashCommandSpec("/cost", "Show usage and cost estimate"),
        SlashCommandSpec("/model-info", "Show model capabilities"),
        SlashCommandSpec("/commit", "Create commit message from staged diff"),
        SlashCommandSpec("/image", "Attach image to next message"),
        SlashCommandSpec("/watch", "Watch directory for changes"),
        SlashCommandSpec("/unwatch", "Stop watch mode"),
        SlashCommandSpec("/save-prompt", "Save reusable prompt"),
        SlashCommandSpec("/use", "Load and run saved prompt"),
        SlashCommandSpec("/prompts", "List saved prompts"),
    ]

    PATH_ARGUMENT_COMMANDS = {
        "/review",
        "/test",
        "/image",
        "/watch",
        "/diff",
    }

    @staticmethod
    def extract_command_token(text: str) -> str:
        """Extract the slash command token currently being typed."""
        stripped = text.lstrip()
        if not stripped.startswith("/"):
            return ""
        return stripped.split(maxsplit=1)[0]

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Get slash-command completions."""
        token = self.extract_command_token(document.text_before_cursor)
        if not token:
            return

        if token == "/":
            candidates = [spec for spec in self.COMMAND_SPECS if spec.recommended]
        else:
            normalized = token.lower()
            candidates = [
                spec for spec in self.COMMAND_SPECS if spec.command.startswith(normalized)
            ]

        for spec in candidates:
            prefix = "recommended | " if spec.recommended else ""
            yield Completion(
                spec.command,
                start_position=-len(token),
                display=spec.command,
                display_meta=f"{prefix}{spec.description}",
            )


class SmartCompleter(Completer):
    """Smart completer that combines command and path completion."""

    def __init__(self):
        self.command_completer = CommandCompleter()
        self.path_completer = PathCompleter(
            expanduser=True, file_filter=None, only_directories=False
        )

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Get completions based on context."""
        text = document.text_before_cursor

        if not text.lstrip().startswith("/"):
            yield from self.path_completer.get_completions(document, complete_event)
            return

        command_token = self.command_completer.extract_command_token(text)
        stripped = text.lstrip()

        # Complete command names while still typing command token.
        if " " not in stripped:
            yield from self.command_completer.get_completions(document, complete_event)
            return

        # For known file-path commands, complete the argument path.
        if command_token.lower() in self.command_completer.PATH_ARGUMENT_COMMANDS:
            argument_text = stripped[len(command_token):].lstrip()
            argument_doc = Document(
                text=argument_text,
                cursor_position=len(argument_text),
            )
            yield from self.path_completer.get_completions(argument_doc, complete_event)


class EnhancedInputManager:
    """Manages enhanced input with history and autocompletion."""

    @staticmethod
    def should_show_live_completions(text_before_cursor: str) -> bool:
        """Enable live completion only while typing a slash command token."""
        stripped = text_before_cursor.lstrip()
        return stripped.startswith("/") and " " not in stripped

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
        self._live_command_completion = Condition(
            lambda: self.should_show_live_completions(
                self.session.default_buffer.document.text_before_cursor
            )
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
        complete_while_typing = False
        if enable_completer:
            completer = self.smart_completer
            complete_while_typing = self._live_command_completion

        # Get input with history support
        try:
            # prompt_toolkit's prompt() is synchronous, but we can call it from async context
            result = await self.session.prompt_async(
                prompt_text,
                completer=completer,
                complete_while_typing=complete_while_typing,
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
        complete_while_typing = False
        if enable_completer:
            completer = self.smart_completer
            complete_while_typing = self._live_command_completion

        # Get input with history support
        try:
            result = self.session.prompt(
                prompt_text,
                completer=completer,
                complete_while_typing=complete_while_typing,
            )
            return result
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+D or Ctrl+C
            raise
