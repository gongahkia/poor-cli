"""
Plan Display for poor-cli

Rich formatting and display of execution plans.
"""

from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from poor_cli.plan_mode import ExecutionPlan, PlanStep, RiskLevel
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class PlanDisplay:
    """Displays execution plans with rich formatting"""

    # Risk level colors
    RISK_COLORS = {
        RiskLevel.SAFE: "green",
        RiskLevel.LOW: "blue",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "red",
        RiskLevel.CRITICAL: "bold red",
    }

    # Risk level icons
    RISK_ICONS = {
        RiskLevel.SAFE: "✓",
        RiskLevel.LOW: "○",
        RiskLevel.MEDIUM: "⚠",
        RiskLevel.HIGH: "⚠",
        RiskLevel.CRITICAL: "⚠",
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def display_plan(self, plan: ExecutionPlan, show_details: bool = True):
        """Display an execution plan with rich formatting

        Args:
            plan: The execution plan to display
            show_details: Whether to show detailed step information
        """
        # Display plan header
        self._display_plan_header(plan)

        # Display steps table
        if plan.steps:
            self._display_steps_table(plan, show_details)

        # Display summary
        self._display_plan_summary(plan)

    def _display_plan_header(self, plan: ExecutionPlan):
        """Display plan header with summary"""
        risk_color = self.RISK_COLORS[plan.overall_risk_level]
        risk_icon = self.RISK_ICONS[plan.overall_risk_level]

        header_text = f"""[bold]Execution Plan[/bold] [dim]({plan.plan_id})[/dim]

[bold cyan]Request:[/bold cyan] {plan.user_request}

[bold]Summary:[/bold]
{plan.summary}

[bold]Overall Risk:[/bold] [{risk_color}]{risk_icon} {plan.overall_risk_level.value.upper()}[/{risk_color}]
[bold]Steps:[/bold] {len(plan.steps)}
[bold]Affected Files:[/bold] {len(plan.get_affected_files())}
"""

        self.console.print(
            Panel(
                header_text,
                title="[bold cyan]📋 Plan Preview[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED
            )
        )
        self.console.print()

    def _display_steps_table(self, plan: ExecutionPlan, show_details: bool):
        """Display steps in a table"""
        table = Table(
            title="Execution Steps",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )

        # Add columns
        table.add_column("#", style="dim", width=3)
        table.add_column("Risk", width=8)
        table.add_column("Operation", style="cyan", width=15)
        table.add_column("Description", width=50)

        if show_details:
            table.add_column("Files", style="dim", width=30)

        # Add rows
        for step in plan.steps:
            risk_color = self.RISK_COLORS[step.risk_level]
            risk_icon = self.RISK_ICONS[step.risk_level]
            risk_text = f"[{risk_color}]{risk_icon} {step.risk_level.value}[/{risk_color}]"

            # Truncate description if too long
            description = step.description
            if len(description) > 50:
                description = description[:47] + "..."

            row = [
                str(step.step_number),
                risk_text,
                step.step_type.value,
                description
            ]

            if show_details:
                files_text = ""
                if step.affected_files:
                    if len(step.affected_files) == 1:
                        files_text = step.affected_files[0]
                        if len(files_text) > 30:
                            files_text = "..." + files_text[-27:]
                    else:
                        files_text = f"{len(step.affected_files)} files"
                row.append(files_text)

            table.add_row(*row)

        self.console.print(table)
        self.console.print()

    def _display_plan_summary(self, plan: ExecutionPlan):
        """Display plan summary and warnings"""
        summary_lines = []

        # Count operations by risk
        risk_counts = {}
        for step in plan.steps:
            risk_counts[step.risk_level] = risk_counts.get(step.risk_level, 0) + 1

        summary_lines.append("[bold]Risk Breakdown:[/bold]")
        for risk_level in [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]:
            count = risk_counts.get(risk_level, 0)
            if count > 0:
                color = self.RISK_COLORS[risk_level]
                icon = self.RISK_ICONS[risk_level]
                summary_lines.append(f"  [{color}]{icon} {risk_level.value}:[/{color}] {count}")

        # Show affected files if any
        affected_files = plan.get_affected_files()
        if affected_files:
            summary_lines.append(f"\n[bold]Affected Files ({len(affected_files)}):[/bold]")
            for file_path in affected_files[:5]:  # Show first 5
                summary_lines.append(f"  • {file_path}")
            if len(affected_files) > 5:
                summary_lines.append(f"  ... and {len(affected_files) - 5} more")

        # Show warnings for high-risk operations
        high_risk = plan.get_high_risk_steps()
        if high_risk:
            summary_lines.append(f"\n[bold red]⚠ Warning:[/bold red] {len(high_risk)} high-risk operation(s)")
            for step in high_risk[:3]:
                summary_lines.append(f"  • Step {step.step_number}: {step.description}")

        self.console.print(Panel(
            "\n".join(summary_lines),
            title="[bold]Summary[/bold]",
            border_style="dim",
            box=box.ROUNDED
        ))
        self.console.print()

    def request_approval(self, plan: ExecutionPlan) -> str:
        """Request user approval for a plan

        Returns:
            One of: 'approve', 'reject', 'modify', 'details'
        """
        self.console.print("[bold]What would you like to do?[/bold]")
        self.console.print("  [green]approve[/green] - Execute the plan")
        self.console.print("  [red]reject[/red]  - Cancel and discard plan")
        self.console.print("  [yellow]details[/yellow] - Show more details")
        self.console.print("  [cyan]modify[/cyan]  - Skip specific steps")
        self.console.print()

        choice = Prompt.ask(
            "[bold]Your choice[/bold]",
            choices=["approve", "reject", "details", "modify", "a", "r", "d", "m"],
            default="approve"
        )

        # Map short forms
        choice_map = {
            "a": "approve",
            "r": "reject",
            "d": "details",
            "m": "modify"
        }

        return choice_map.get(choice, choice)

    def show_step_details(self, step: PlanStep):
        """Show detailed information about a step"""
        risk_color = self.RISK_COLORS[step.risk_level]
        risk_icon = self.RISK_ICONS[step.risk_level]

        details = f"""[bold]Step {step.step_number}:[/bold] {step.description}

[bold]Type:[/bold] {step.step_type.value}
[bold]Tool:[/bold] {step.tool_name}
[bold]Risk:[/bold] [{risk_color}]{risk_icon} {step.risk_level.value.upper()}[/{risk_color}]
[bold]Duration:[/bold] {step.estimated_duration}

[bold]Arguments:[/bold]
"""
        for key, value in step.tool_args.items():
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            details += f"  • {key}: {value_str}\n"

        if step.affected_files:
            details += f"\n[bold]Affected Files:[/bold]\n"
            for file_path in step.affected_files:
                details += f"  • {file_path}\n"

        self.console.print(Panel(
            details,
            title=f"[bold cyan]Step {step.step_number} Details[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()

    def select_steps_to_skip(self, plan: ExecutionPlan) -> list[int]:
        """Allow user to select steps to skip

        Returns:
            List of step numbers to skip
        """
        self.console.print("[bold]Select steps to skip (comma-separated numbers):[/bold]")
        self.console.print("[dim]Leave empty to execute all steps[/dim]")
        self.console.print()

        # Show simplified list
        for step in plan.steps:
            risk_color = self.RISK_COLORS[step.risk_level]
            self.console.print(
                f"  [{risk_color}]{step.step_number}.[/{risk_color}] {step.description}"
            )

        self.console.print()
        skip_input = Prompt.ask(
            "[bold]Steps to skip[/bold]",
            default=""
        )

        if not skip_input.strip():
            return []

        # Parse input
        skip_steps = []
        for part in skip_input.split(","):
            part = part.strip()
            if part.isdigit():
                step_num = int(part)
                if 1 <= step_num <= len(plan.steps):
                    skip_steps.append(step_num)

        if skip_steps:
            self.console.print(f"\n[yellow]Will skip steps: {', '.join(map(str, skip_steps))}[/yellow]")

        return skip_steps

    def display_execution_progress(self, step: PlanStep):
        """Display progress indicator for step execution"""
        risk_color = self.RISK_COLORS[step.risk_level]
        self.console.print(
            f"\n[{risk_color}]→ Executing step {step.step_number}:[/{risk_color}] {step.description}"
        )

    def display_plan_complete(self, plan: ExecutionPlan, executed_steps: int, skipped_steps: int):
        """Display completion message"""
        self.console.print()
        self.console.print(Panel(
            f"[bold green]✓ Plan execution complete![/bold green]\n\n"
            f"Executed: [green]{executed_steps}[/green] steps\n"
            f"Skipped: [yellow]{skipped_steps}[/yellow] steps\n"
            f"Total: {len(plan.steps)} steps",
            title="[bold]Execution Summary[/bold]",
            border_style="green"
        ))
