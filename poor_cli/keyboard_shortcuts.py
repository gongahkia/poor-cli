"""
Keyboard Shortcuts for poor-cli

Global keyboard shortcuts:
- Ctrl+R: Retry last command
- Ctrl+P: Show plan history
- Ctrl+H: Show help
- Ctrl+F: Find/search
- Ctrl+E: Edit last message
- Ctrl+/: Toggle verbose mode
"""

from typing import Callable, Dict, Optional
from enum import Enum
import sys

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class ShortcutKey(Enum):
    """Keyboard shortcuts"""
    CTRL_R = "ctrl+r"  # Retry
    CTRL_P = "ctrl+p"  # Plan history
    CTRL_H = "ctrl+h"  # Help
    CTRL_F = "ctrl+f"  # Find
    CTRL_E = "ctrl+e"  # Edit
    CTRL_SLASH = "ctrl+/"  # Toggle verbose
    CTRL_C = "ctrl+c"  # Cancel
    CTRL_D = "ctrl+d"  # Exit
    ESC = "esc"  # Cancel/back


class KeyboardHandler:
    """Handle keyboard shortcuts"""

    def __init__(self):
        self.handlers: Dict[ShortcutKey, Callable] = {}
        self.enabled = True

    def register(self, key: ShortcutKey, handler: Callable):
        """Register shortcut handler

        Args:
            key: Keyboard shortcut
            handler: Handler function
        """
        self.handlers[key] = handler
        logger.debug(f"Registered shortcut: {key.value}")

    def unregister(self, key: ShortcutKey):
        """Unregister shortcut"""
        if key in self.handlers:
            del self.handlers[key]

    def handle(self, key: ShortcutKey) -> bool:
        """Handle keyboard shortcut

        Args:
            key: Pressed key

        Returns:
            True if handled
        """
        if not self.enabled:
            return False

        if key in self.handlers:
            try:
                self.handlers[key]()
                return True
            except Exception as e:
                logger.error(f"Shortcut handler error: {e}")
                return False

        return False

    def enable(self):
        """Enable shortcuts"""
        self.enabled = True

    def disable(self):
        """Disable shortcuts"""
        self.enabled = False


class ShortcutManager:
    """Manage keyboard shortcuts for REPL"""

    def __init__(self):
        self.handler = KeyboardHandler()
        self._setup_default_shortcuts()

    def _setup_default_shortcuts(self):
        """Setup default shortcuts"""
        # These are placeholders - actual implementation would
        # integrate with the REPL

        self.handler.register(
            ShortcutKey.CTRL_H,
            self._show_help
        )

    def _show_help(self):
        """Show keyboard shortcuts help"""
        help_text = """
[bold cyan]Keyboard Shortcuts[/bold cyan]

[bold]Navigation:[/bold]
  Ctrl+R    - Retry last command
  Ctrl+P    - Show plan history
  Ctrl+H    - Show this help
  Ctrl+F    - Find/search in history
  Ctrl+E    - Edit last message

[bold]Actions:[/bold]
  Ctrl+/    - Toggle verbose mode
  Ctrl+C    - Cancel current operation
  Ctrl+D    - Exit REPL
  ESC       - Cancel/go back

[bold]Checkpoints:[/bold]
  Ctrl+S    - Create checkpoint
  Ctrl+Z    - Undo (rewind last checkpoint)

[bold]Display:[/bold]
  Ctrl+L    - Clear screen
  Ctrl+T    - Toggle UI mode
"""
        print(help_text)

    def get_shortcut_map(self) -> Dict[str, str]:
        """Get mapping of shortcuts to descriptions

        Returns:
            Dict of shortcut -> description
        """
        return {
            "Ctrl+R": "Retry last command",
            "Ctrl+P": "Show plan history",
            "Ctrl+H": "Show help",
            "Ctrl+F": "Find/search",
            "Ctrl+E": "Edit last message",
            "Ctrl+/": "Toggle verbose mode",
            "Ctrl+C": "Cancel operation",
            "Ctrl+D": "Exit",
            "Ctrl+S": "Create checkpoint",
            "Ctrl+Z": "Undo/rewind",
            "Ctrl+L": "Clear screen",
            "Ctrl+T": "Toggle UI mode",
            "ESC": "Cancel/back"
        }


# Global shortcut manager instance
_shortcut_manager: Optional[ShortcutManager] = None


def get_shortcut_manager() -> ShortcutManager:
    """Get global shortcut manager"""
    global _shortcut_manager
    if _shortcut_manager is None:
        _shortcut_manager = ShortcutManager()
    return _shortcut_manager
