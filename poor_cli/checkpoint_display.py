"""
Checkpoint Display for poor-cli

Rich formatting for checkpoint listings and management.
"""

from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from datetime import datetime

from poor_cli.checkpoint import Checkpoint, CheckpointManager
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class CheckpointDisplay:
    """Displays checkpoints with rich formatting"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def display_checkpoint_list(
        self,
        checkpoints: List[Checkpoint],
        show_details: bool = False
    ):
        """Display list of checkpoints

        Args:
            checkpoints: List of checkpoints to display
            show_details: Whether to show detailed information
        """
        if not checkpoints:
            self.console.print("[dim]No checkpoints found[/dim]")
            return

        table = Table(
            title=f"Checkpoints ({len(checkpoints)})",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )

        # Add columns
        table.add_column("#", style="dim", width=3)
        table.add_column("ID", style="cyan", width=20)
        table.add_column("Created", width=20)
        table.add_column("Description", width=40)
        table.add_column("Files", justify="right", width=6)

        if show_details:
            table.add_column("Size", justify="right", width=10)
            table.add_column("Type", width=12)

        # Add rows
        for idx, checkpoint in enumerate(checkpoints, 1):
            # Format creation time
            try:
                created_dt = datetime.fromisoformat(checkpoint.created_at)
                created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                created_str = checkpoint.created_at[:19]

            # Truncate description if too long
            description = checkpoint.description
            if len(description) > 40:
                description = description[:37] + "..."

            # Format size
            total_size = checkpoint.get_total_size()
            if total_size < 1024:
                size_str = f"{total_size}B"
            elif total_size < 1024 * 1024:
                size_str = f"{total_size / 1024:.1f}KB"
            else:
                size_str = f"{total_size / (1024 * 1024):.1f}MB"

            row = [
                str(idx),
                checkpoint.checkpoint_id,
                created_str,
                description,
                str(checkpoint.get_file_count())
            ]

            if show_details:
                row.append(size_str)
                row.append(checkpoint.operation_type)

            table.add_row(*row)

        self.console.print(table)
        self.console.print()

    def display_checkpoint_details(self, checkpoint: Checkpoint):
        """Display detailed information about a checkpoint

        Args:
            checkpoint: Checkpoint to display
        """
        # Format creation time
        try:
            created_dt = datetime.fromisoformat(checkpoint.created_at)
            created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            created_str = checkpoint.created_at

        # Build details text
        details = f"""[bold]Checkpoint ID:[/bold] {checkpoint.checkpoint_id}
[bold]Created:[/bold] {created_str}
[bold]Type:[/bold] {checkpoint.operation_type}
[bold]Description:[/bold] {checkpoint.description}

[bold]Statistics:[/bold]
  • Files: {checkpoint.get_file_count()}
  • Total Size: {self._format_size(checkpoint.get_total_size())}
"""

        # Add tags if any
        if checkpoint.tags:
            details += f"  • Tags: {', '.join(checkpoint.tags)}\n"

        # Add metadata if any
        if checkpoint.metadata:
            details += "\n[bold]Metadata:[/bold]\n"
            for key, value in checkpoint.metadata.items():
                details += f"  • {key}: {value}\n"

        # Add file list
        if checkpoint.snapshots:
            details += "\n[bold]Files:[/bold]\n"
            for snapshot in checkpoint.snapshots[:10]:  # Show first 10
                size_str = self._format_size(snapshot.size_bytes)
                details += f"  • {snapshot.file_path} ({size_str})\n"

            if len(checkpoint.snapshots) > 10:
                details += f"  ... and {len(checkpoint.snapshots) - 10} more files\n"

        self.console.print(Panel(
            details,
            title=f"[bold cyan]Checkpoint Details[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        ))
        self.console.print()

    def display_restore_summary(
        self,
        checkpoint: Checkpoint,
        files_restored: int,
        files_requested: Optional[int] = None
    ):
        """Display summary after restoring checkpoint

        Args:
            checkpoint: Restored checkpoint
            files_restored: Number of files actually restored
            files_requested: Number of files requested (None = all)
        """
        if files_requested is None:
            files_requested = checkpoint.get_file_count()

        status = "green" if files_restored == files_requested else "yellow"

        summary = f"""[bold {status}]✓ Checkpoint restored[/bold {status}]

[bold]Checkpoint:[/bold] {checkpoint.checkpoint_id}
[bold]Description:[/bold] {checkpoint.description}

[bold]Results:[/bold]
  • Requested: {files_requested} file(s)
  • Restored: {files_restored} file(s)
"""

        if files_restored < files_requested:
            failed = files_requested - files_restored
            summary += f"  • Failed: {failed} file(s)\n"
            summary += "\n[yellow]Some files could not be restored (check logs)[/yellow]"

        self.console.print(Panel(
            summary,
            title="[bold]Restore Complete[/bold]",
            border_style=status,
            box=box.ROUNDED
        ))
        self.console.print()

    def display_checkpoint_created(self, checkpoint: Checkpoint):
        """Display notification that checkpoint was created

        Args:
            checkpoint: Created checkpoint
        """
        summary = f"""[bold green]✓ Checkpoint created[/bold green]

[bold]ID:[/bold] {checkpoint.checkpoint_id}
[bold]Description:[/bold] {checkpoint.description}
[bold]Files:[/bold] {checkpoint.get_file_count()}
[bold]Size:[/bold] {self._format_size(checkpoint.get_total_size())}

[dim]Use /rewind {checkpoint.checkpoint_id} to restore this checkpoint[/dim]
"""

        self.console.print(Panel(
            summary,
            title="[bold cyan]📸 Checkpoint[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        ))
        self.console.print()

    def display_storage_info(self, manager: CheckpointManager):
        """Display storage usage information

        Args:
            manager: CheckpointManager instance
        """
        total_size = manager.get_storage_size()
        checkpoint_count = len(manager.checkpoints)

        info = f"""[bold]Checkpoint Storage[/bold]

[bold]Location:[/bold] {manager.checkpoints_dir}
[bold]Checkpoints:[/bold] {checkpoint_count} / {manager.MAX_CHECKPOINTS}
[bold]Total Size:[/bold] {self._format_size(total_size)}

[dim]Old checkpoints are automatically cleaned up after {manager.MAX_CHECKPOINTS} checkpoints[/dim]
"""

        self.console.print(Panel(
            info,
            title="[bold]Storage Info[/bold]",
            border_style="dim",
            box=box.ROUNDED
        ))
        self.console.print()

    def confirm_restore(
        self,
        checkpoint: Checkpoint,
        file_paths: Optional[List[str]] = None
    ) -> bool:
        """Ask user to confirm restore operation

        Args:
            checkpoint: Checkpoint to restore
            file_paths: Specific files to restore (None = all)

        Returns:
            True if user confirms, False otherwise
        """
        if file_paths:
            files_info = f"{len(file_paths)} specific file(s)"
        else:
            files_info = f"all {checkpoint.get_file_count()} file(s)"

        self.console.print(Panel(
            f"[bold yellow]⚠ Warning[/bold yellow]\n\n"
            f"This will restore {files_info} from checkpoint:\n"
            f"[cyan]{checkpoint.checkpoint_id}[/cyan]\n\n"
            f"[bold]Description:[/bold] {checkpoint.description}\n\n"
            f"[bold red]Current files will be overwritten![/bold red]\n\n"
            f"[dim]Tip: Create a new checkpoint first to save current state[/dim]",
            title="[bold]Confirm Restore[/bold]",
            border_style="yellow",
            box=box.ROUNDED
        ))

        # Get confirmation
        from rich.prompt import Confirm
        confirmed = Confirm.ask(
            "[bold]Proceed with restore?[/bold]",
            default=False
        )

        return confirmed

    def _format_size(self, size_bytes: int) -> str:
        """Format size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f}GB"

    def show_quick_restore_hint(self):
        """Show hint about quick restore with Esc key"""
        self.console.print(
            "[dim]💡 Tip: Press Esc twice to quickly restore the last checkpoint[/dim]\n"
        )
