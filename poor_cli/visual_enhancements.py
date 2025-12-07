"""
Visual Enhancements for poor-cli

Rich UI components:
- Progress indicators with Rich
- Collapsible sections
- Inline diffs with syntax highlighting
- File trees and directory visualization
- Split-pane views
"""

from typing import List, Optional, Any
from pathlib import Path

from rich.console import Console, Group
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.tree import Tree
from rich.panel import Panel
from rich.columns import Columns
from rich.syntax import Syntax
from rich.layout import Layout
from rich import box
from rich.live import Live

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class ProgressIndicator:
    """Advanced progress indicators"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def show_spinner(self, text: str):
        """Show spinner with text"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            progress.add_task(description=text, total=None)

    def show_progress_bar(
        self,
        total: int,
        description: str = "Processing"
    ) -> Progress:
        """Create progress bar"""
        return Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        )


class FileTreeVisualizer:
    """Visualize directory structure as tree"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def create_tree(
        self,
        root_path: Path,
        max_depth: int = 3,
        show_hidden: bool = False
    ) -> Tree:
        """Create file tree

        Args:
            root_path: Root directory
            max_depth: Maximum depth to show
            show_hidden: Show hidden files

        Returns:
            Rich Tree object
        """
        tree = Tree(
            f"📁 {root_path.name}",
            guide_style="dim"
        )

        self._add_directory_to_tree(
            tree,
            root_path,
            max_depth,
            show_hidden,
            current_depth=0
        )

        return tree

    def _add_directory_to_tree(
        self,
        tree: Tree,
        directory: Path,
        max_depth: int,
        show_hidden: bool,
        current_depth: int
    ):
        """Recursively add directory contents to tree"""
        if current_depth >= max_depth:
            return

        try:
            paths = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))

            for path in paths:
                # Skip hidden files if not requested
                if not show_hidden and path.name.startswith('.'):
                    continue

                if path.is_dir():
                    branch = tree.add(f"📁 {path.name}", style="bold blue")
                    self._add_directory_to_tree(
                        branch,
                        path,
                        max_depth,
                        show_hidden,
                        current_depth + 1
                    )
                else:
                    # Add file with emoji based on extension
                    icon = self._get_file_icon(path)
                    tree.add(f"{icon} {path.name}", style="dim")

        except PermissionError:
            tree.add("[red]Permission denied[/red]")

    def _get_file_icon(self, path: Path) -> str:
        """Get emoji icon for file type"""
        ext = path.suffix.lower()

        icon_map = {
            '.py': '🐍',
            '.js': '📜',
            '.ts': '📘',
            '.json': '📋',
            '.md': '📝',
            '.txt': '📄',
            '.yml': '⚙️',
            '.yaml': '⚙️',
            '.toml': '⚙️',
            '.sh': '🔧',
            '.rs': '🦀',
            '.go': '🔵',
        }

        return icon_map.get(ext, '📄')


class InlineDiffViewer:
    """Display inline diffs with syntax highlighting"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def show_diff(
        self,
        old_content: str,
        new_content: str,
        language: str = "python"
    ):
        """Show side-by-side diff"""
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')

        # Create panels
        old_panel = Panel(
            Syntax(old_content, language, theme="monokai"),
            title="[red]Before[/red]",
            border_style="red"
        )

        new_panel = Panel(
            Syntax(new_content, language, theme="monokai"),
            title="[green]After[/green]",
            border_style="green"
        )

        # Display side-by-side
        self.console.print(Columns([old_panel, new_panel]))


class CollapsibleSection:
    """Collapsible section manager"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.sections: dict[str, bool] = {}  # section_id -> expanded

    def create_section(
        self,
        section_id: str,
        title: str,
        content: str,
        expanded: bool = False
    ):
        """Create collapsible section"""
        self.sections[section_id] = expanded

        if expanded:
            self.console.print(Panel(
                content,
                title=f"▼ {title}",
                border_style="cyan"
            ))
        else:
            self.console.print(f"▶ {title} (collapsed)")

    def toggle(self, section_id: str):
        """Toggle section expansion"""
        if section_id in self.sections:
            self.sections[section_id] = not self.sections[section_id]


class SplitPaneView:
    """Split-pane layout"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def create_split_view(
        self,
        left_content: Any,
        right_content: Any,
        title: str = ""
    ):
        """Create split pane view"""
        layout = Layout()

        layout.split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        layout["left"].update(Panel(left_content, border_style="cyan"))
        layout["right"].update(Panel(right_content, border_style="green"))

        if title:
            wrapper = Layout()
            wrapper.split_column(
                Layout(Panel(title, box=box.DOUBLE), size=3),
                layout
            )
            self.console.print(wrapper)
        else:
            self.console.print(layout)
