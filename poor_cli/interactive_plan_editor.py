"""
Interactive Plan Editor for poor-cli

Allows users to interactively modify execution plans:
- Modify step parameters
- Reorder steps
- Skip/enable steps
- Add new steps
- Remove steps
- Visual editing interface
"""

from typing import List, Dict, Optional, Any
from dataclasses import replace
from copy import deepcopy

from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.panel import Panel
from rich import box

from poor_cli.plan_mode import ExecutionPlan, PlanStep, PlanStepType, RiskLevel
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class PlanEditor:
    """Interactive editor for execution plans"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def edit_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Interactively edit an execution plan

        Args:
            plan: Plan to edit

        Returns:
            Modified plan
        """
        # Create working copy
        edited_plan = deepcopy(plan)

        while True:
            # Display current plan
            self._display_plan(edited_plan)

            # Show menu
            self.console.print()
            self.console.print(Panel(
                "[cyan]1[/cyan] - Modify step\n"
                "[cyan]2[/cyan] - Reorder steps\n"
                "[cyan]3[/cyan] - Skip/enable step\n"
                "[cyan]4[/cyan] - Add step\n"
                "[cyan]5[/cyan] - Remove step\n"
                "[cyan]6[/cyan] - View step details\n"
                "[cyan]7[/cyan] - Reset to original\n"
                "[cyan]8[/cyan] - Done editing",
                title="[bold]Edit Menu[/bold]",
                border_style="cyan"
            ))

            choice = Prompt.ask(
                "Choose action",
                choices=["1", "2", "3", "4", "5", "6", "7", "8"],
                default="8"
            )

            if choice == "1":
                edited_plan = self._modify_step(edited_plan)
            elif choice == "2":
                edited_plan = self._reorder_steps(edited_plan)
            elif choice == "3":
                edited_plan = self._toggle_step(edited_plan)
            elif choice == "4":
                edited_plan = self._add_step(edited_plan)
            elif choice == "5":
                edited_plan = self._remove_step(edited_plan)
            elif choice == "6":
                self._view_step_details(edited_plan)
            elif choice == "7":
                if Confirm.ask("[yellow]Reset all changes?[/yellow]", default=False):
                    edited_plan = deepcopy(plan)
                    self.console.print("[green]Plan reset to original[/green]")
            elif choice == "8":
                # Confirm changes
                if self._has_changes(plan, edited_plan):
                    if Confirm.ask("[bold]Save changes?[/bold]", default=True):
                        self.console.print("[green]✓ Changes saved[/green]")
                        break
                    else:
                        self.console.print("[yellow]Changes discarded[/yellow]")
                        return plan
                else:
                    self.console.print("[dim]No changes made[/dim]")
                    break

        return edited_plan

    def _display_plan(self, plan: ExecutionPlan):
        """Display current plan state"""
        self.console.clear()

        # Header
        self.console.print(Panel(
            f"[bold cyan]Plan Editor[/bold cyan]\n\n"
            f"[bold]Request:[/bold] {plan.user_request}\n"
            f"[bold]Summary:[/bold] {plan.summary}\n"
            f"[bold]Risk Level:[/bold] {self._format_risk(plan.overall_risk_level)}",
            box=box.ROUNDED
        ))

        # Steps table
        table = Table(
            title=f"Steps ({len(plan.steps)})",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )

        table.add_column("#", width=3)
        table.add_column("Type", width=12)
        table.add_column("Description", width=40)
        table.add_column("Risk", width=8)
        table.add_column("Status", width=8)

        for step in plan.steps:
            # Check if step is marked as skipped
            status = step.metadata.get('skipped', False) if hasattr(step, 'metadata') else False
            status_str = "[dim]SKIP[/dim]" if status else "[green]ACTIVE[/green]"

            table.add_row(
                str(step.step_number),
                step.step_type.value,
                step.description[:40],
                self._format_risk(step.risk_level),
                status_str
            )

        self.console.print(table)

    def _modify_step(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Modify a step's parameters"""
        if not plan.steps:
            self.console.print("[yellow]No steps to modify[/yellow]")
            return plan

        step_num = IntPrompt.ask(
            "Step number to modify",
            default=1
        )

        # Find step
        step = self._find_step(plan, step_num)
        if not step:
            self.console.print(f"[red]Step {step_num} not found[/red]")
            return plan

        # Show current values
        self.console.print(f"\n[bold]Current step:[/bold]")
        self.console.print(f"  Type: {step.step_type.value}")
        self.console.print(f"  Description: {step.description}")
        self.console.print(f"  Tool: {step.tool_name}")
        self.console.print(f"  Args: {step.tool_args}")

        # Ask what to modify
        self.console.print("\n[bold]What to modify?[/bold]")
        field = Prompt.ask(
            "Field",
            choices=["description", "tool_args", "risk_level", "cancel"],
            default="cancel"
        )

        if field == "cancel":
            return plan

        # Modify field
        if field == "description":
            new_desc = Prompt.ask("New description", default=step.description)
            step.description = new_desc

        elif field == "tool_args":
            self.console.print("\n[bold]Current arguments:[/bold]")
            for key, value in step.tool_args.items():
                self.console.print(f"  {key}: {value}")

            arg_name = Prompt.ask("Argument to modify")
            if arg_name in step.tool_args:
                new_value = Prompt.ask(f"New value for {arg_name}", default=str(step.tool_args[arg_name]))
                step.tool_args[arg_name] = new_value
            else:
                self.console.print(f"[yellow]Argument '{arg_name}' not found[/yellow]")

        elif field == "risk_level":
            new_risk = Prompt.ask(
                "New risk level",
                choices=["safe", "low", "medium", "high", "critical"],
                default=step.risk_level.value
            )
            step.risk_level = RiskLevel(new_risk)

        self.console.print("[green]✓ Step modified[/green]")
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

        return plan

    def _reorder_steps(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Reorder steps"""
        if len(plan.steps) < 2:
            self.console.print("[yellow]Need at least 2 steps to reorder[/yellow]")
            return plan

        from_pos = IntPrompt.ask("Move step number", default=1)
        to_pos = IntPrompt.ask("To position", default=1)

        if from_pos < 1 or from_pos > len(plan.steps):
            self.console.print(f"[red]Invalid step number: {from_pos}[/red]")
            return plan

        if to_pos < 1 or to_pos > len(plan.steps):
            self.console.print(f"[red]Invalid position: {to_pos}[/red]")
            return plan

        # Move step
        step = plan.steps.pop(from_pos - 1)
        plan.steps.insert(to_pos - 1, step)

        # Renumber steps
        for i, s in enumerate(plan.steps, 1):
            s.step_number = i

        self.console.print(f"[green]✓ Moved step {from_pos} to position {to_pos}[/green]")
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

        return plan

    def _toggle_step(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Toggle step skip status"""
        if not plan.steps:
            self.console.print("[yellow]No steps available[/yellow]")
            return plan

        step_num = IntPrompt.ask("Step number to skip/enable", default=1)

        step = self._find_step(plan, step_num)
        if not step:
            self.console.print(f"[red]Step {step_num} not found[/red]")
            return plan

        # Initialize metadata if needed
        if not hasattr(step, 'metadata'):
            step.metadata = {}

        # Toggle skip status
        current_status = step.metadata.get('skipped', False)
        step.metadata['skipped'] = not current_status

        status_str = "skipped" if step.metadata['skipped'] else "enabled"
        self.console.print(f"[green]✓ Step {step_num} is now {status_str}[/green]")
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

        return plan

    def _add_step(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Add a new step"""
        self.console.print("\n[bold cyan]Add New Step[/bold cyan]\n")

        # Get step details
        step_type = Prompt.ask(
            "Step type",
            choices=["read_file", "write_file", "edit_file", "bash", "other"],
            default="other"
        )

        description = Prompt.ask("Description")

        tool_name = Prompt.ask("Tool name", default=step_type)

        # Get tool arguments
        self.console.print("\n[bold]Tool arguments (key=value, empty to finish):[/bold]")
        tool_args = {}
        while True:
            arg = Prompt.ask("Argument", default="")
            if not arg:
                break

            if '=' in arg:
                key, value = arg.split('=', 1)
                tool_args[key.strip()] = value.strip()

        risk_level = Prompt.ask(
            "Risk level",
            choices=["safe", "low", "medium", "high", "critical"],
            default="low"
        )

        position = IntPrompt.ask(
            "Insert at position",
            default=len(plan.steps) + 1
        )

        # Create new step
        new_step = PlanStep(
            step_number=position,
            step_type=PlanStepType(step_type),
            description=description,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=RiskLevel(risk_level)
        )

        # Insert step
        if position <= len(plan.steps):
            plan.steps.insert(position - 1, new_step)
        else:
            plan.steps.append(new_step)

        # Renumber steps
        for i, s in enumerate(plan.steps, 1):
            s.step_number = i

        self.console.print("[green]✓ Step added[/green]")
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

        return plan

    def _remove_step(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Remove a step"""
        if not plan.steps:
            self.console.print("[yellow]No steps to remove[/yellow]")
            return plan

        step_num = IntPrompt.ask("Step number to remove", default=1)

        step = self._find_step(plan, step_num)
        if not step:
            self.console.print(f"[red]Step {step_num} not found[/red]")
            return plan

        # Confirm removal
        if Confirm.ask(f"[yellow]Remove step {step_num}: {step.description}?[/yellow]", default=False):
            plan.steps = [s for s in plan.steps if s.step_number != step_num]

            # Renumber steps
            for i, s in enumerate(plan.steps, 1):
                s.step_number = i

            self.console.print("[green]✓ Step removed[/green]")
        else:
            self.console.print("[dim]Cancelled[/dim]")

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

        return plan

    def _view_step_details(self, plan: ExecutionPlan):
        """View detailed information about a step"""
        if not plan.steps:
            self.console.print("[yellow]No steps available[/yellow]")
            return

        step_num = IntPrompt.ask("Step number to view", default=1)

        step = self._find_step(plan, step_num)
        if not step:
            self.console.print(f"[red]Step {step_num} not found[/red]")
            return

        # Display details
        details = f"""[bold cyan]Step {step.step_number} Details[/bold cyan]

[bold]Type:[/bold] {step.step_type.value}
[bold]Description:[/bold] {step.description}
[bold]Tool:[/bold] {step.tool_name}
[bold]Risk Level:[/bold] {self._format_risk(step.risk_level)}

[bold]Tool Arguments:[/bold]
"""

        for key, value in step.tool_args.items():
            details += f"  • {key}: {value}\n"

        if step.affected_files:
            details += f"\n[bold]Affected Files:[/bold]\n"
            for f in step.affected_files:
                details += f"  • {f}\n"

        if step.dependencies:
            details += f"\n[bold]Dependencies:[/bold] {step.dependencies}\n"

        if hasattr(step, 'metadata') and step.metadata:
            details += f"\n[bold]Metadata:[/bold]\n"
            for key, value in step.metadata.items():
                details += f"  • {key}: {value}\n"

        self.console.print(Panel(details, box=box.ROUNDED))
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    def _find_step(self, plan: ExecutionPlan, step_num: int) -> Optional[PlanStep]:
        """Find step by number"""
        for step in plan.steps:
            if step.step_number == step_num:
                return step
        return None

    def _format_risk(self, risk: RiskLevel) -> str:
        """Format risk level with color"""
        colors = {
            RiskLevel.SAFE: "green",
            RiskLevel.LOW: "cyan",
            RiskLevel.MEDIUM: "yellow",
            RiskLevel.HIGH: "orange",
            RiskLevel.CRITICAL: "red"
        }
        color = colors.get(risk, "white")
        return f"[{color}]{risk.value.upper()}[/{color}]"

    def _has_changes(self, original: ExecutionPlan, edited: ExecutionPlan) -> bool:
        """Check if plan has been modified"""
        if len(original.steps) != len(edited.steps):
            return True

        for orig_step, edit_step in zip(original.steps, edited.steps):
            if orig_step.description != edit_step.description:
                return True
            if orig_step.tool_args != edit_step.tool_args:
                return True
            if orig_step.risk_level != edit_step.risk_level:
                return True
            if hasattr(edit_step, 'metadata') and edit_step.metadata.get('skipped', False):
                return True

        return False


class QuickPlanModifier:
    """Quick plan modifications without full editor"""

    @staticmethod
    def skip_steps(plan: ExecutionPlan, step_numbers: List[int]) -> ExecutionPlan:
        """Mark steps to be skipped

        Args:
            plan: Plan to modify
            step_numbers: List of step numbers to skip

        Returns:
            Modified plan
        """
        for step in plan.steps:
            if step.step_number in step_numbers:
                if not hasattr(step, 'metadata'):
                    step.metadata = {}
                step.metadata['skipped'] = True

        return plan

    @staticmethod
    def change_step_order(plan: ExecutionPlan, new_order: List[int]) -> ExecutionPlan:
        """Reorder steps

        Args:
            plan: Plan to modify
            new_order: New order as list of step numbers

        Returns:
            Modified plan
        """
        if len(new_order) != len(plan.steps):
            logger.error("New order must have same number of steps")
            return plan

        # Create new step list in specified order
        step_map = {step.step_number: step for step in plan.steps}
        new_steps = []

        for new_num, old_num in enumerate(new_order, 1):
            if old_num not in step_map:
                logger.error(f"Invalid step number: {old_num}")
                return plan

            step = step_map[old_num]
            step.step_number = new_num
            new_steps.append(step)

        plan.steps = new_steps
        return plan

    @staticmethod
    def modify_step_args(
        plan: ExecutionPlan,
        step_number: int,
        new_args: Dict[str, Any]
    ) -> ExecutionPlan:
        """Modify step arguments

        Args:
            plan: Plan to modify
            step_number: Step number to modify
            new_args: New arguments

        Returns:
            Modified plan
        """
        for step in plan.steps:
            if step.step_number == step_number:
                step.tool_args.update(new_args)
                break

        return plan

    @staticmethod
    def filter_steps(
        plan: ExecutionPlan,
        step_type: Optional[PlanStepType] = None,
        max_risk: Optional[RiskLevel] = None
    ) -> ExecutionPlan:
        """Filter steps by criteria

        Args:
            plan: Plan to modify
            step_type: Only include this step type (None = all)
            max_risk: Maximum risk level (None = all)

        Returns:
            Filtered plan
        """
        filtered_steps = []

        for step in plan.steps:
            # Check type filter
            if step_type and step.step_type != step_type:
                continue

            # Check risk filter
            if max_risk:
                risk_levels = [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
                if risk_levels.index(step.risk_level) > risk_levels.index(max_risk):
                    continue

            filtered_steps.append(step)

        # Renumber steps
        for i, step in enumerate(filtered_steps, 1):
            step.step_number = i

        plan.steps = filtered_steps
        return plan
