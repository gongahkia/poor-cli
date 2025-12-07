"""
UI Modes for poor-cli

Different display modes:
- Compact: Minimal output
- Verbose: Detailed logging
- Presentation: Clean, demo-friendly
- JSON: Machine-readable output
- GUI: Graphical panels and layout
"""

from typing import Any, Dict, Optional
from enum import Enum
import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich import box

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class UIMode(Enum):
    """UI display modes"""
    COMPACT = "compact"
    VERBOSE = "verbose"
    PRESENTATION = "presentation"
    JSON_MODE = "json"
    GUI = "gui"


class UIRenderer:
    """Render content in different UI modes"""

    def __init__(self, mode: UIMode = UIMode.VERBOSE):
        self.mode = mode
        self.console = Console()

    def set_mode(self, mode: UIMode):
        """Change UI mode"""
        self.mode = mode
        logger.info(f"UI mode changed to: {mode.value}")

    def render_message(self, message: str, level: str = "info"):
        """Render message based on mode

        Args:
            message: Message to display
            level: Message level (info, warning, error, success)
        """
        if self.mode == UIMode.COMPACT:
            # Minimal output
            symbol = {"info": "ℹ", "warning": "⚠", "error": "✗", "success": "✓"}.get(level, "•")
            self.console.print(f"{symbol} {message}")

        elif self.mode == UIMode.VERBOSE:
            # Detailed output
            styles = {
                "info": "blue",
                "warning": "yellow",
                "error": "red",
                "success": "green"
            }
            style = styles.get(level, "white")
            self.console.print(f"[{style}][{level.upper()}][/{style}] {message}")

        elif self.mode == UIMode.PRESENTATION:
            # Clean, demo-friendly
            styles = {
                "info": ("blue", "ℹ"),
                "warning": ("yellow", "⚠"),
                "error": ("red", "✗"),
                "success": ("green", "✓")
            }
            style, symbol = styles.get(level, ("white", "•"))
            self.console.print(Panel(
                f"{symbol} {message}",
                border_style=style,
                box=box.ROUNDED
            ))

        elif self.mode == UIMode.JSON_MODE:
            # Machine-readable JSON
            output = {
                "type": "message",
                "level": level,
                "content": message
            }
            self.console.print(json.dumps(output))

        elif self.mode == UIMode.GUI:
            # Graphical panel
            styles = {
                "info": "blue",
                "warning": "yellow",
                "error": "red",
                "success": "green"
            }
            style = styles.get(level, "white")
            self.console.print(Panel(
                message,
                title=f"[bold]{level.upper()}[/bold]",
                border_style=style
            ))

    def render_table(self, title: str, headers: list, rows: list):
        """Render table based on mode"""
        if self.mode == UIMode.COMPACT:
            # Simple text table
            for row in rows:
                self.console.print(" | ".join(str(cell) for cell in row))

        elif self.mode in [UIMode.VERBOSE, UIMode.PRESENTATION, UIMode.GUI]:
            # Rich table
            table = Table(title=title, box=box.ROUNDED)

            for header in headers:
                table.add_column(header, style="cyan")

            for row in rows:
                table.add_row(*[str(cell) for cell in row])

            self.console.print(table)

        elif self.mode == UIMode.JSON_MODE:
            # JSON array
            output = {
                "type": "table",
                "title": title,
                "headers": headers,
                "rows": rows
            }
            self.console.print(json.dumps(output))

    def render_progress(self, message: str, percent: float):
        """Render progress indicator"""
        if self.mode == UIMode.COMPACT:
            self.console.print(f"{message}: {percent:.0f}%")

        elif self.mode in [UIMode.VERBOSE, UIMode.PRESENTATION]:
            from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn

            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task(message, total=100)
                progress.update(task, completed=percent)

        elif self.mode == UIMode.JSON_MODE:
            output = {
                "type": "progress",
                "message": message,
                "percent": percent
            }
            self.console.print(json.dumps(output))

        elif self.mode == UIMode.GUI:
            self.console.print(Panel(
                f"[bold]{message}[/bold]\n{'█' * int(percent/10)}{'░' * (10-int(percent/10))} {percent:.0f}%",
                border_style="cyan"
            ))


class DashboardView:
    """GUI dashboard with multiple panes"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def create_dashboard(
        self,
        title: str,
        sections: Dict[str, Any]
    ):
        """Create dashboard with multiple sections

        Args:
            title: Dashboard title
            sections: Dict of section_name -> content
        """
        layout = Layout()

        # Header
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body")
        )

        layout["header"].update(Panel(
            f"[bold cyan]{title}[/bold cyan]",
            box=box.DOUBLE
        ))

        # Split body into sections
        if len(sections) == 2:
            layout["body"].split_row(*[Layout(name=name) for name in sections.keys()])
        elif len(sections) == 3:
            layout["body"].split_row(
                Layout(name=list(sections.keys())[0]),
                Layout(name="right")
            )
            layout["right"].split_column(*[
                Layout(name=name) for name in list(sections.keys())[1:]
            ])
        elif len(sections) == 4:
            layout["body"].split_row(
                Layout(name="left"),
                Layout(name="right")
            )
            layout["left"].split_column(*[
                Layout(name=name) for name in list(sections.keys())[:2]
            ])
            layout["right"].split_column(*[
                Layout(name=name) for name in list(sections.keys())[2:]
            ])

        # Add content to sections
        for section_name, content in sections.items():
            if section_name in layout:
                layout[section_name].update(Panel(
                    content,
                    title=section_name,
                    border_style="green"
                ))

        self.console.print(layout)
