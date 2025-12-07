"""
Visual Checkpoint Timeline for poor-cli

Interactive git-style graph visualization and browser for checkpoints.
Features:
- Git-style branch/timeline graph
- Interactive browser with navigation
- File change visualization
- Relationship tracking between checkpoints
"""

from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict
import math

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich.columns import Columns
from rich.align import Align
from rich import box
from rich.prompt import Prompt, Confirm
from rich.layout import Layout
from rich.live import Live

from poor_cli.checkpoint import Checkpoint, CheckpointManager
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class TimelineNode:
    """Node in the checkpoint timeline"""
    checkpoint: Checkpoint
    parent_ids: List[str]
    child_ids: List[str]
    branch: int  # Branch/lane number for visualization
    distance_from_head: int  # How many checkpoints back


class CheckpointTimeline:
    """Manages checkpoint relationships and timeline"""

    def __init__(self, checkpoints: List[Checkpoint]):
        self.checkpoints = checkpoints
        self.nodes: Dict[str, TimelineNode] = {}
        self._build_timeline()

    def _build_timeline(self):
        """Build timeline with parent-child relationships"""
        # Sort by creation time
        sorted_cps = sorted(self.checkpoints, key=lambda cp: cp.created_at, reverse=True)

        # Build nodes
        for i, checkpoint in enumerate(sorted_cps):
            node = TimelineNode(
                checkpoint=checkpoint,
                parent_ids=[],
                child_ids=[],
                branch=0,
                distance_from_head=i
            )
            self.nodes[checkpoint.checkpoint_id] = node

        # Infer relationships based on file overlaps and temporal proximity
        self._infer_relationships()

        # Assign branches for visualization
        self._assign_branches()

    def _infer_relationships(self):
        """Infer parent-child relationships between checkpoints"""
        sorted_nodes = sorted(
            self.nodes.values(),
            key=lambda n: n.checkpoint.created_at
        )

        for i, node in enumerate(sorted_nodes):
            # Look at previous checkpoints to find potential parents
            for prev_node in sorted_nodes[:i]:
                if self._is_likely_parent(prev_node.checkpoint, node.checkpoint):
                    node.parent_ids.append(prev_node.checkpoint.checkpoint_id)
                    prev_node.child_ids.append(node.checkpoint.checkpoint_id)
                    break  # Only take immediate parent

    def _is_likely_parent(self, cp1: Checkpoint, cp2: Checkpoint) -> bool:
        """Determine if cp1 is likely a parent of cp2"""
        # Check temporal proximity (within 1 hour)
        try:
            time1 = datetime.fromisoformat(cp1.created_at)
            time2 = datetime.fromisoformat(cp2.created_at)
            time_diff = abs((time2 - time1).total_seconds())

            if time_diff > 3600:  # More than 1 hour apart
                return False
        except:
            pass

        # Check file overlap
        files1 = set(s.file_path for s in cp1.snapshots)
        files2 = set(s.file_path for s in cp2.snapshots)

        if not files1 or not files2:
            return False

        overlap = len(files1 & files2) / len(files1 | files2)

        # Consider parent if >50% file overlap
        return overlap > 0.5

    def _assign_branches(self):
        """Assign branch lanes for visualization"""
        sorted_nodes = sorted(
            self.nodes.values(),
            key=lambda n: n.checkpoint.created_at
        )

        used_branches: Set[int] = set()
        branch_counter = 0

        for node in sorted_nodes:
            if not node.parent_ids:
                # Root node
                node.branch = branch_counter
                used_branches.add(branch_counter)
                branch_counter += 1
            else:
                # Inherit parent's branch
                parent_id = node.parent_ids[0]
                if parent_id in self.nodes:
                    node.branch = self.nodes[parent_id].branch


class CheckpointTimelineDisplay:
    """Visual display for checkpoint timeline"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.colors = [
            "cyan", "green", "yellow", "magenta", "blue", "red",
            "bright_cyan", "bright_green", "bright_yellow"
        ]

    def display_git_style_graph(
        self,
        checkpoints: List[Checkpoint],
        limit: int = 20
    ):
        """Display git-style graph of checkpoints

        Args:
            checkpoints: List of checkpoints
            limit: Maximum number of checkpoints to show
        """
        if not checkpoints:
            self.console.print("[dim]No checkpoints found[/dim]")
            return

        # Build timeline
        timeline = CheckpointTimeline(checkpoints[:limit])

        # Display header
        self.console.print(Panel(
            f"[bold cyan]Checkpoint Timeline[/bold cyan] ({len(checkpoints)} total)",
            box=box.ROUNDED
        ))

        # Display each checkpoint in timeline
        sorted_nodes = sorted(
            timeline.nodes.values(),
            key=lambda n: n.checkpoint.created_at,
            reverse=True
        )

        for i, node in enumerate(sorted_nodes):
            self._display_timeline_node(node, timeline, i == 0)

    def _display_timeline_node(
        self,
        node: TimelineNode,
        timeline: CheckpointTimeline,
        is_head: bool
    ):
        """Display a single node in the timeline"""
        checkpoint = node.checkpoint

        # Build graph line
        graph = self._build_graph_line(node, timeline)

        # Format checkpoint info
        try:
            created_dt = datetime.fromisoformat(checkpoint.created_at)
            time_str = created_dt.strftime("%Y-%m-%d %H:%M")
        except:
            time_str = checkpoint.created_at[:16]

        # Color based on branch
        color = self.colors[node.branch % len(self.colors)]

        # Build display line
        head_marker = "[bold yellow]HEAD → [/bold yellow]" if is_head else ""

        # Truncate description
        desc = checkpoint.description
        if len(desc) > 50:
            desc = desc[:47] + "..."

        # Tags
        tags_str = ""
        if checkpoint.tags:
            tags_str = f" [{', '.join(checkpoint.tags[:2])}]"

        # Format: graph | ID | time | description
        line = Text.assemble(
            (graph, f"{color}"),
            ("  ", ""),
            (f"{checkpoint.checkpoint_id[:16]}", "cyan"),
            ("  ", ""),
            (f"{time_str}", "dim"),
            ("  ", ""),
            (head_marker, ""),
            (desc, ""),
            (tags_str, "dim")
        )

        self.console.print(line)

    def _build_graph_line(
        self,
        node: TimelineNode,
        timeline: CheckpointTimeline
    ) -> str:
        """Build git-style graph line for a node"""
        # Simple linear graph
        if node.branch == 0:
            if not node.child_ids:
                # Latest checkpoint
                return "● "
            elif not node.parent_ids:
                # Oldest checkpoint
                return "○ "
            else:
                # Middle checkpoint
                return "● "
        else:
            # Branch
            return "◆ "

    def display_checkpoint_tree(
        self,
        checkpoints: List[Checkpoint],
        max_depth: int = 10
    ):
        """Display checkpoint relationships as a tree

        Args:
            checkpoints: List of checkpoints
            max_depth: Maximum tree depth to show
        """
        if not checkpoints:
            self.console.print("[dim]No checkpoints found[/dim]")
            return

        timeline = CheckpointTimeline(checkpoints)

        # Find root nodes (no parents)
        roots = [
            node for node in timeline.nodes.values()
            if not node.parent_ids
        ]

        if not roots:
            # If no clear roots, use oldest checkpoints
            sorted_nodes = sorted(
                timeline.nodes.values(),
                key=lambda n: n.checkpoint.created_at
            )
            roots = sorted_nodes[:3]

        # Build tree
        tree = Tree(
            "[bold cyan]📸 Checkpoint Tree[/bold cyan]",
            guide_style="dim"
        )

        for root in roots:
            self._add_node_to_tree(tree, root, timeline, depth=0, max_depth=max_depth)

        self.console.print(tree)

    def _add_node_to_tree(
        self,
        parent: Tree,
        node: TimelineNode,
        timeline: CheckpointTimeline,
        depth: int,
        max_depth: int
    ):
        """Recursively add nodes to tree"""
        if depth >= max_depth:
            return

        checkpoint = node.checkpoint

        # Format node label
        try:
            created_dt = datetime.fromisoformat(checkpoint.created_at)
            time_str = created_dt.strftime("%m-%d %H:%M")
        except:
            time_str = checkpoint.created_at[:16]

        desc = checkpoint.description
        if len(desc) > 40:
            desc = desc[:37] + "..."

        label = f"[cyan]{checkpoint.checkpoint_id[:12]}[/cyan] {time_str} - {desc}"

        # Add tags
        if checkpoint.tags:
            label += f" [dim]({', '.join(checkpoint.tags[:2])})[/dim]"

        # Add node
        branch = parent.add(label)

        # Add children
        for child_id in node.child_ids:
            if child_id in timeline.nodes:
                child_node = timeline.nodes[child_id]
                self._add_node_to_tree(branch, child_node, timeline, depth + 1, max_depth)

    def launch_interactive_browser(
        self,
        manager: CheckpointManager,
        checkpoints: List[Checkpoint]
    ):
        """Launch interactive checkpoint browser

        Args:
            manager: CheckpointManager instance
            checkpoints: List of checkpoints to browse
        """
        if not checkpoints:
            self.console.print("[yellow]No checkpoints to browse[/yellow]")
            return

        current_index = 0

        while True:
            # Clear screen
            self.console.clear()

            # Display current checkpoint
            self._display_browser_view(
                checkpoints,
                current_index,
                manager
            )

            # Display navigation help
            self.console.print()
            self.console.print(Panel(
                "[cyan]j/k[/cyan] or [cyan]↓/↑[/cyan]: Navigate  |  "
                "[cyan]v[/cyan]: View details  |  "
                "[cyan]r[/cyan]: Restore  |  "
                "[cyan]d[/cyan]: Delete  |  "
                "[cyan]q[/cyan]: Quit",
                title="[bold]Navigation[/bold]",
                border_style="dim"
            ))

            # Get user input
            command = Prompt.ask(
                "\n[bold]Command[/bold]",
                choices=["j", "k", "v", "r", "d", "q", "↓", "↑"],
                default="q",
                show_choices=False
            ).lower()

            # Handle commands
            if command in ["q", "quit"]:
                break
            elif command in ["j", "↓"]:
                current_index = min(current_index + 1, len(checkpoints) - 1)
            elif command in ["k", "↑"]:
                current_index = max(current_index - 1, 0)
            elif command == "v":
                self._show_checkpoint_details(checkpoints[current_index])
                Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            elif command == "r":
                if self._confirm_restore(checkpoints[current_index]):
                    try:
                        manager.restore_checkpoint(checkpoints[current_index].checkpoint_id)
                        self.console.print("[green]✓ Checkpoint restored successfully[/green]")
                        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
                    except Exception as e:
                        self.console.print(f"[red]✗ Failed to restore: {e}[/red]")
                        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            elif command == "d":
                if self._confirm_delete(checkpoints[current_index]):
                    try:
                        manager.delete_checkpoint(checkpoints[current_index].checkpoint_id)
                        checkpoints.pop(current_index)
                        if current_index >= len(checkpoints):
                            current_index = max(0, len(checkpoints) - 1)
                        self.console.print("[green]✓ Checkpoint deleted[/green]")
                        if not checkpoints:
                            self.console.print("[yellow]No more checkpoints[/yellow]")
                            break
                        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
                    except Exception as e:
                        self.console.print(f"[red]✗ Failed to delete: {e}[/red]")
                        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    def _display_browser_view(
        self,
        checkpoints: List[Checkpoint],
        current_index: int,
        manager: CheckpointManager
    ):
        """Display browser view with current checkpoint highlighted"""
        checkpoint = checkpoints[current_index]

        # Display position indicator
        position = f"[bold]{current_index + 1}[/bold] / {len(checkpoints)}"
        self.console.print(Panel(
            f"[cyan]📸 Checkpoint Browser[/cyan]  |  {position}",
            box=box.ROUNDED,
            style="bold"
        ))

        # Display surrounding checkpoints
        start = max(0, current_index - 2)
        end = min(len(checkpoints), current_index + 3)

        for i in range(start, end):
            cp = checkpoints[i]

            try:
                created_dt = datetime.fromisoformat(cp.created_at)
                time_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                time_str = cp.created_at[:19]

            marker = "→" if i == current_index else " "
            style = "bold cyan" if i == current_index else "dim"

            self.console.print(
                f"  {marker} [{style}]{cp.checkpoint_id[:16]}[/{style}]  "
                f"{time_str}  {cp.description[:50]}"
            )

        # Display detailed info for current checkpoint
        self.console.print()
        self._display_checkpoint_summary(checkpoint, manager)

    def _display_checkpoint_summary(
        self,
        checkpoint: Checkpoint,
        manager: CheckpointManager
    ):
        """Display summary panel for checkpoint"""
        try:
            created_dt = datetime.fromisoformat(checkpoint.created_at)
            time_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = checkpoint.created_at

        # Build summary
        lines = [
            f"[bold]ID:[/bold] {checkpoint.checkpoint_id}",
            f"[bold]Created:[/bold] {time_str}",
            f"[bold]Type:[/bold] {checkpoint.operation_type}",
            f"[bold]Files:[/bold] {checkpoint.get_file_count()}",
            f"[bold]Size:[/bold] {self._format_size(checkpoint.get_total_size())}"
        ]

        if checkpoint.tags:
            lines.append(f"[bold]Tags:[/bold] {', '.join(checkpoint.tags)}")

        lines.append("")
        lines.append(f"[bold]Description:[/bold]")
        lines.append(checkpoint.description)

        # Display file list
        if checkpoint.snapshots:
            lines.append("")
            lines.append(f"[bold]Files ({len(checkpoint.snapshots)}):[/bold]")
            for snapshot in checkpoint.snapshots[:5]:
                lines.append(f"  • {snapshot.file_path}")
            if len(checkpoint.snapshots) > 5:
                lines.append(f"  ... and {len(checkpoint.snapshots) - 5} more")

        self.console.print(Panel(
            "\n".join(lines),
            title="[bold]Details[/bold]",
            border_style="cyan",
            box=box.ROUNDED
        ))

    def _show_checkpoint_details(self, checkpoint: Checkpoint):
        """Show detailed view of checkpoint"""
        self.console.clear()

        try:
            created_dt = datetime.fromisoformat(checkpoint.created_at)
            time_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = checkpoint.created_at

        details = [
            f"[bold cyan]Checkpoint Details[/bold cyan]",
            "",
            f"[bold]ID:[/bold] {checkpoint.checkpoint_id}",
            f"[bold]Created:[/bold] {time_str}",
            f"[bold]Operation Type:[/bold] {checkpoint.operation_type}",
            f"[bold]Description:[/bold] {checkpoint.description}",
            "",
            f"[bold]Statistics:[/bold]",
            f"  • Files: {checkpoint.get_file_count()}",
            f"  • Total Size: {self._format_size(checkpoint.get_total_size())}",
        ]

        if checkpoint.tags:
            details.append(f"  • Tags: {', '.join(checkpoint.tags)}")

        if checkpoint.metadata:
            details.append("")
            details.append("[bold]Metadata:[/bold]")
            for key, value in checkpoint.metadata.items():
                details.append(f"  • {key}: {value}")

        details.append("")
        details.append(f"[bold]All Files:[/bold]")
        for snapshot in checkpoint.snapshots:
            size_str = self._format_size(snapshot.size_bytes)
            details.append(f"  • {snapshot.file_path} ({size_str})")

        self.console.print("\n".join(details))

    def _confirm_restore(self, checkpoint: Checkpoint) -> bool:
        """Confirm restore operation"""
        return Confirm.ask(
            f"\n[bold yellow]Restore checkpoint {checkpoint.checkpoint_id[:16]}?[/bold yellow]",
            default=False
        )

    def _confirm_delete(self, checkpoint: Checkpoint) -> bool:
        """Confirm delete operation"""
        return Confirm.ask(
            f"\n[bold red]Delete checkpoint {checkpoint.checkpoint_id[:16]}?[/bold red]",
            default=False
        )

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

    def display_timeline_stats(self, checkpoints: List[Checkpoint]):
        """Display timeline statistics"""
        if not checkpoints:
            self.console.print("[dim]No checkpoints[/dim]")
            return

        # Calculate stats
        total_files = sum(cp.get_file_count() for cp in checkpoints)
        total_size = sum(cp.get_total_size() for cp in checkpoints)

        # Group by operation type
        by_type = defaultdict(int)
        for cp in checkpoints:
            by_type[cp.operation_type] += 1

        # Group by tags
        tag_counts = defaultdict(int)
        for cp in checkpoints:
            for tag in cp.tags:
                tag_counts[tag] += 1

        # Time range
        try:
            times = [datetime.fromisoformat(cp.created_at) for cp in checkpoints]
            oldest = min(times)
            newest = max(times)
            time_range = f"{oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}"
        except:
            time_range = "Unknown"

        # Display stats
        stats = f"""[bold cyan]Timeline Statistics[/bold cyan]

[bold]Overview:[/bold]
  • Total Checkpoints: {len(checkpoints)}
  • Total Files: {total_files}
  • Total Size: {self._format_size(total_size)}
  • Time Range: {time_range}

[bold]By Operation Type:[/bold]
"""

        for op_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            stats += f"  • {op_type}: {count}\n"

        if tag_counts:
            stats += "\n[bold]Most Common Tags:[/bold]\n"
            for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                stats += f"  • {tag}: {count}\n"

        self.console.print(Panel(stats, box=box.ROUNDED))
