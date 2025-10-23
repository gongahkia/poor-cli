"""
Diff Preview for poor-cli

Shows unified diffs before applying file modifications.
"""

import difflib
from typing import Optional, List, Tuple
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich import box

from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


class DiffPreview:
    """Generates and displays file diffs"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def generate_unified_diff(
        self,
        original_content: str,
        new_content: str,
        file_path: str = "file",
        context_lines: int = 3
    ) -> str:
        """Generate unified diff between two contents

        Args:
            original_content: Original file content
            new_content: New file content
            file_path: File path for diff header
            context_lines: Number of context lines around changes

        Returns:
            Unified diff string
        """
        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm='\n',
            n=context_lines
        )

        return ''.join(diff)

    def generate_side_by_side_diff(
        self,
        original_content: str,
        new_content: str,
        width: int = 80
    ) -> List[Tuple[str, str, str]]:
        """Generate side-by-side diff

        Args:
            original_content: Original file content
            new_content: New file content
            width: Width for each side

        Returns:
            List of (marker, left_line, right_line) tuples
        """
        original_lines = original_content.splitlines()
        new_lines = new_content.splitlines()

        diff_lines = []
        matcher = difflib.SequenceMatcher(None, original_lines, new_lines)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    diff_lines.append((' ', original_lines[i], new_lines[j]))

            elif tag == 'delete':
                for i in range(i1, i2):
                    diff_lines.append(('-', original_lines[i], ''))

            elif tag == 'insert':
                for j in range(j1, j2):
                    diff_lines.append(('+', '', new_lines[j]))

            elif tag == 'replace':
                # Show both deletions and insertions
                for i in range(i1, i2):
                    diff_lines.append(('-', original_lines[i], ''))
                for j in range(j1, j2):
                    diff_lines.append(('+', '', new_lines[j]))

        return diff_lines

    def display_unified_diff(
        self,
        original_content: str,
        new_content: str,
        file_path: str,
        show_line_numbers: bool = True
    ):
        """Display unified diff with syntax highlighting

        Args:
            original_content: Original file content
            new_content: New file content
            file_path: File path for context
            show_line_numbers: Whether to show line numbers
        """
        # Generate diff
        diff_text = self.generate_unified_diff(
            original_content,
            new_content,
            file_path
        )

        if not diff_text.strip():
            self.console.print("[dim]No changes detected[/dim]")
            return

        # Count changes
        added_lines = diff_text.count('\n+') - 1  # Exclude header
        removed_lines = diff_text.count('\n-') - 1  # Exclude header

        # Display header
        header = f"[bold cyan]File:[/bold cyan] {file_path}\n"
        header += f"[green]+{added_lines}[/green] / [red]-{removed_lines}[/red] lines"

        self.console.print(Panel(
            header,
            title="[bold]Diff Preview[/bold]",
            border_style="cyan",
            box=box.ROUNDED
        ))
        self.console.print()

        # Display diff with syntax highlighting
        try:
            # Use Syntax for better formatting
            syntax = Syntax(
                diff_text,
                "diff",
                theme="monokai",
                line_numbers=show_line_numbers,
                word_wrap=False
            )
            self.console.print(syntax)
        except Exception as e:
            # Fallback to plain text with manual coloring
            logger.debug(f"Syntax highlighting failed, using plain text: {e}")
            self._display_diff_plain(diff_text)

        self.console.print()

    def _display_diff_plain(self, diff_text: str):
        """Display diff with basic coloring"""
        for line in diff_text.splitlines():
            if line.startswith('+++') or line.startswith('---'):
                self.console.print(f"[bold]{line}[/bold]")
            elif line.startswith('+'):
                self.console.print(f"[green]{line}[/green]")
            elif line.startswith('-'):
                self.console.print(f"[red]{line}[/red]")
            elif line.startswith('@@'):
                self.console.print(f"[cyan]{line}[/cyan]")
            else:
                self.console.print(f"[dim]{line}[/dim]")

    def display_side_by_side_diff(
        self,
        original_content: str,
        new_content: str,
        file_path: str,
        max_lines: int = 50
    ):
        """Display side-by-side diff (compact view)

        Args:
            original_content: Original content
            new_content: New content
            file_path: File path
            max_lines: Maximum lines to show
        """
        diff_lines = self.generate_side_by_side_diff(original_content, new_content)

        # Limit lines
        if len(diff_lines) > max_lines:
            diff_lines = diff_lines[:max_lines]
            truncated = True
        else:
            truncated = False

        # Display header
        self.console.print(Panel(
            f"[bold cyan]File:[/bold cyan] {file_path}",
            title="[bold]Side-by-Side Diff[/bold]",
            border_style="cyan"
        ))
        self.console.print()

        # Display diff
        for marker, left, right in diff_lines:
            if marker == '+':
                self.console.print(f"[green]+ {right}[/green]")
            elif marker == '-':
                self.console.print(f"[red]- {left}[/red]")
            else:
                self.console.print(f"[dim]  {left}[/dim]")

        if truncated:
            self.console.print(f"\n[dim]... truncated ({len(diff_lines)} more lines)[/dim]")

        self.console.print()

    def get_diff_stats(
        self,
        original_content: str,
        new_content: str
    ) -> dict:
        """Get statistics about the diff

        Returns:
            Dict with stats: {
                'added_lines': int,
                'removed_lines': int,
                'changed_lines': int,
                'total_lines_before': int,
                'total_lines_after': int
            }
        """
        original_lines = original_content.splitlines()
        new_lines = new_content.splitlines()

        matcher = difflib.SequenceMatcher(None, original_lines, new_lines)

        added = 0
        removed = 0
        changed = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'delete':
                removed += (i2 - i1)
            elif tag == 'insert':
                added += (j2 - j1)
            elif tag == 'replace':
                removed += (i2 - i1)
                added += (j2 - j1)
                changed += min(i2 - i1, j2 - j1)

        return {
            'added_lines': added,
            'removed_lines': removed,
            'changed_lines': changed,
            'total_lines_before': len(original_lines),
            'total_lines_after': len(new_lines)
        }

    def compare_files(
        self,
        file_path1: str,
        file_path2: str,
        display: bool = True
    ) -> Optional[str]:
        """Compare two files and optionally display diff

        Args:
            file_path1: First file path
            file_path2: Second file path
            display: Whether to display the diff

        Returns:
            Diff string or None if error
        """
        try:
            path1 = Path(file_path1)
            path2 = Path(file_path2)

            if not path1.exists():
                raise FileOperationError(f"File not found: {file_path1}")
            if not path2.exists():
                raise FileOperationError(f"File not found: {file_path2}")

            # Read files
            with open(path1, 'r', encoding='utf-8', errors='ignore') as f:
                content1 = f.read()

            with open(path2, 'r', encoding='utf-8', errors='ignore') as f:
                content2 = f.read()

            # Generate diff
            diff = self.generate_unified_diff(
                content1,
                content2,
                file_path=f"{path1.name} vs {path2.name}"
            )

            # Display if requested
            if display:
                self.display_unified_diff(content1, content2, f"{path1.name} vs {path2.name}")

            return diff

        except Exception as e:
            logger.error(f"Failed to compare files: {e}")
            if display:
                self.console.print(f"[red]Error comparing files: {e}[/red]")
            return None

    def preview_file_write(
        self,
        file_path: str,
        new_content: str,
        display_mode: str = "unified"
    ) -> bool:
        """Preview changes before writing to file

        Args:
            file_path: Target file path
            new_content: Content to be written
            display_mode: 'unified' or 'side-by-side'

        Returns:
            True if file will be modified, False if no changes
        """
        path = Path(file_path)

        # Check if file exists
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    original_content = f.read()

                # Check if content is identical
                if original_content == new_content:
                    self.console.print(f"[dim]No changes to {file_path}[/dim]")
                    return False

                # Display diff
                if display_mode == "side-by-side":
                    self.display_side_by_side_diff(
                        original_content,
                        new_content,
                        file_path
                    )
                else:
                    self.display_unified_diff(
                        original_content,
                        new_content,
                        file_path
                    )

                return True

            except Exception as e:
                logger.error(f"Failed to preview file write: {e}")
                self.console.print(f"[yellow]Warning: Could not read existing file for preview[/yellow]")
                return True

        else:
            # New file
            self.console.print(Panel(
                f"[bold green]Creating new file:[/bold green] {file_path}\n"
                f"[dim]Size: {len(new_content)} bytes\n"
                f"Lines: {len(new_content.splitlines())}[/dim]",
                title="[bold]New File[/bold]",
                border_style="green"
            ))
            self.console.print()
            return True

    def preview_file_edit(
        self,
        file_path: str,
        old_text: Optional[str],
        new_text: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ):
        """Preview file edit operation

        Args:
            file_path: File to be edited
            old_text: Text to be replaced (for text mode)
            new_text: Replacement text
            start_line: Start line for line mode
            end_line: End line for line mode
        """
        path = Path(file_path)

        if not path.exists():
            self.console.print(f"[red]File not found: {file_path}[/red]")
            return

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()

            # Simulate the edit
            if old_text is not None:
                # Text replacement mode
                if old_text not in original_content:
                    self.console.print(f"[yellow]Warning: Text to replace not found in file[/yellow]")
                    return
                new_content = original_content.replace(old_text, new_text)

            elif start_line is not None:
                # Line-based editing mode
                lines = original_content.split('\n')
                start = start_line - 1
                end = end_line if end_line else start + 1

                if start < 0 or start >= len(lines):
                    self.console.print(f"[red]Invalid line range[/red]")
                    return

                lines[start:end] = [new_text]
                new_content = '\n'.join(lines)

            else:
                # Append mode
                new_content = original_content + new_text

            # Display diff
            self.display_unified_diff(original_content, new_content, file_path)

        except Exception as e:
            logger.error(f"Failed to preview file edit: {e}")
            self.console.print(f"[red]Error previewing edit: {e}[/red]")
