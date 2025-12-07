"""
Interactive Elements for poor-cli

Advanced interactive components:
- Tab completion with fuzzy matching
- Fuzzy search through files/commands
- Multi-select menus
- Inline editing
- Click-to-open links
"""

from typing import List, Optional, Callable, Any
from pathlib import Path
import re

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class FuzzyMatcher:
    """Fuzzy string matching"""

    @staticmethod
    def fuzzy_match(query: str, target: str) -> float:
        """Calculate fuzzy match score (0-1)

        Args:
            query: Search query
            target: Target string

        Returns:
            Match score (higher is better)
        """
        query = query.lower()
        target = target.lower()

        # Exact match
        if query == target:
            return 1.0

        # Substring match
        if query in target:
            return 0.8

        # Character sequence match
        query_idx = 0
        for char in target:
            if query_idx < len(query) and char == query[query_idx]:
                query_idx += 1

        if query_idx == len(query):
            return 0.6

        # No match
        return 0.0

    @staticmethod
    def fuzzy_search(
        query: str,
        candidates: List[str],
        limit: int = 10
    ) -> List[tuple[str, float]]:
        """Fuzzy search candidates

        Args:
            query: Search query
            candidates: List of candidates
            limit: Max results

        Returns:
            List of (candidate, score) tuples
        """
        scores = [
            (candidate, FuzzyMatcher.fuzzy_match(query, candidate))
            for candidate in candidates
        ]

        # Filter and sort
        scores = [(c, s) for c, s in scores if s > 0.0]
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:limit]


class TabCompleter:
    """Tab completion with fuzzy matching"""

    def __init__(self):
        self.completions: dict[str, List[str]] = {}

    def register_completions(self, context: str, options: List[str]):
        """Register completion options for a context"""
        self.completions[context] = options

    def complete(
        self,
        context: str,
        partial: str
    ) -> List[str]:
        """Get completions for partial input"""
        if context not in self.completions:
            return []

        options = self.completions[context]

        # Fuzzy search
        matches = FuzzyMatcher.fuzzy_search(partial, options)

        return [match[0] for match in matches]


class MultiSelect:
    """Multi-select menu"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def select(
        self,
        options: List[str],
        title: str = "Select items",
        preselected: Optional[List[int]] = None
    ) -> List[str]:
        """Show multi-select menu

        Args:
            options: List of options
            title: Menu title
            preselected: Pre-selected indices

        Returns:
            List of selected items
        """
        selected = set(preselected or [])

        self.console.print(f"\n[bold]{title}[/bold]")
        self.console.print("[dim]Use space to select, Enter to confirm[/dim]\n")

        # Display options
        for i, option in enumerate(options):
            marker = "[X]" if i in selected else "[ ]"
            self.console.print(f"{i+1}. {marker} {option}")

        # Get selection (simplified - in real implementation would use key events)
        response = Prompt.ask(
            "\nEnter numbers to toggle (space-separated), or 'done' to finish",
            default="done"
        )

        if response == "done":
            return [options[i] for i in selected]

        # Parse response
        try:
            indices = [int(x.strip()) - 1 for x in response.split()]
            for idx in indices:
                if 0 <= idx < len(options):
                    if idx in selected:
                        selected.remove(idx)
                    else:
                        selected.add(idx)
        except ValueError:
            pass

        # Recursively show menu again
        return self.select(options, title, list(selected))


class InlineEditor:
    """Inline text editing"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def edit_inline(
        self,
        initial_text: str,
        title: str = "Edit"
    ) -> str:
        """Edit text inline

        Args:
            initial_text: Initial text
            title: Editor title

        Returns:
            Edited text
        """
        self.console.print(f"\n[bold]{title}[/bold]")
        self.console.print(f"[dim]Current: {initial_text}[/dim]\n")

        edited = Prompt.ask("New value", default=initial_text)

        return edited


class ClickableLinks:
    """Handle clickable links in terminal"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def print_link(
        self,
        text: str,
        url: str
    ):
        """Print clickable link"""
        # Use OSC 8 hyperlink escape sequence
        link = f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
        self.console.print(link)

    def print_file_link(
        self,
        file_path: Path,
        line_number: Optional[int] = None
    ):
        """Print clickable file link"""
        url = f"file://{file_path.absolute()}"

        if line_number:
            url += f":{line_number}"
            text = f"{file_path}:{line_number}"
        else:
            text = str(file_path)

        self.print_link(text, url)
