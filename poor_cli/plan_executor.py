"""
Plan Executor for poor-cli

Handles execution of plans with user approval and step-by-step execution.
"""

from typing import Optional, List, Callable, Awaitable, Any, Dict
from rich.console import Console

from poor_cli.plan_mode import ExecutionPlan, PlanStep
from poor_cli.plan_analyzer import PlanAnalyzer
from poor_cli.plan_display import PlanDisplay
from poor_cli.checkpoint import CheckpointManager
from poor_cli.diff_preview import DiffPreview
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class PlanExecutor:
    """Executes plans with user approval"""

    def __init__(
        self,
        console: Optional[Console] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        diff_preview: Optional[DiffPreview] = None
    ):
        self.console = console or Console()
        self.plan_analyzer = PlanAnalyzer()
        self.plan_display = PlanDisplay(console=self.console)
        self.checkpoint_manager = checkpoint_manager
        self.diff_preview = diff_preview

    async def execute_with_plan(
        self,
        user_request: str,
        function_calls: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        ai_summary: Optional[str] = None
    ) -> tuple[bool, List[str]]:
        """Execute function calls with plan mode

        Args:
            user_request: Original user request
            function_calls: List of function calls to execute
            tool_executor: Async function to execute tools
            ai_summary: Optional AI summary of what will be done

        Returns:
            Tuple of (success, results)
        """
        # Create plan
        plan = self.plan_analyzer.create_plan_from_request(user_request, ai_summary)

        # Add function calls to plan
        for fc in function_calls:
            self.plan_analyzer.add_function_call_to_plan(
                plan,
                fc["name"],
                fc["arguments"],
                fc.get("description")
            )

        # If plan is empty, nothing to do
        if not plan.steps:
            logger.debug("Empty plan, nothing to execute")
            return True, []

        # Display plan
        self.plan_display.display_plan(plan, show_details=True)

        # Get user approval
        choice = self.plan_display.request_approval(plan)

        if choice == "reject":
            self.console.print("[yellow]Plan rejected by user[/yellow]")
            return False, []

        elif choice == "details":
            # Show details and ask again
            for step in plan.steps:
                self.plan_display.show_step_details(step)
            return await self.execute_with_plan(
                user_request, function_calls, tool_executor, ai_summary
            )

        elif choice == "modify":
            # Let user skip steps
            skip_steps = self.plan_display.select_steps_to_skip(plan)
            return await self._execute_plan_steps(
                plan, tool_executor, skip_steps=skip_steps
            )

        elif choice == "approve":
            # Execute all steps
            return await self._execute_plan_steps(plan, tool_executor)

        else:
            # Default to reject
            return False, []

    async def _execute_plan_steps(
        self,
        plan: ExecutionPlan,
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        skip_steps: Optional[List[int]] = None
    ) -> tuple[bool, List[str]]:
        """Execute plan steps

        Args:
            plan: Execution plan
            tool_executor: Function to execute tools
            skip_steps: Step numbers to skip

        Returns:
            Tuple of (success, results)
        """
        skip_steps = skip_steps or []
        results = []
        executed = 0
        skipped = 0

        try:
            # Create checkpoint before execution if configured
            if self.checkpoint_manager:
                affected_files = plan.get_affected_files()
                if affected_files:
                    try:
                        # Filter to existing files
                        from pathlib import Path
                        existing_files = [f for f in affected_files if Path(f).exists()]

                        if existing_files:
                            checkpoint = self.checkpoint_manager.create_checkpoint(
                                file_paths=existing_files,
                                description=f"Before plan execution: {plan.plan_id}",
                                operation_type="pre_plan",
                                tags=["plan", "auto"]
                            )
                            logger.info(f"Created checkpoint before plan execution: {checkpoint.checkpoint_id}")
                            self.console.print(f"[dim]📸 Checkpoint created: {checkpoint.checkpoint_id}[/dim]\n")
                    except Exception as e:
                        logger.warning(f"Failed to create pre-plan checkpoint: {e}")

            # Execute each step
            for step in plan.steps:
                # Skip if requested
                if step.step_number in skip_steps:
                    self.console.print(f"[yellow]⊘ Skipping step {step.step_number}[/yellow]")
                    skipped += 1
                    results.append(f"Skipped: {step.description}")
                    continue

                # Display progress
                self.plan_display.display_execution_progress(step)

                # Show diff preview if applicable and configured
                if (
                    step.tool_name in ["write_file", "edit_file"] and
                    self.diff_preview and
                    step.affected_files
                ):
                    try:
                        await self._show_diff_for_step(step)
                    except Exception as e:
                        logger.debug(f"Failed to show diff: {e}")

                # Execute tool
                try:
                    result = await tool_executor(step.tool_name, step.tool_args)
                    results.append(result)
                    executed += 1
                    self.console.print(f"[dim green]✓ Completed[/dim green]")

                except Exception as e:
                    logger.error(f"Step {step.step_number} failed: {e}")
                    self.console.print(f"[red]✗ Failed: {e}[/red]")
                    results.append(f"Error: {str(e)}")
                    # Continue with other steps

            # Display completion
            self.plan_display.display_plan_complete(plan, executed, skipped)

            return True, results

        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            self.console.print(f"[red]Plan execution failed: {e}[/red]")
            return False, results

    async def _show_diff_for_step(self, step: PlanStep):
        """Show diff preview for a step if applicable

        Args:
            step: Plan step
        """
        if not step.affected_files or not self.diff_preview:
            return

        file_path = step.affected_files[0]  # First file

        if step.tool_name == "write_file":
            content = step.tool_args.get("content", "")
            self.diff_preview.preview_file_write(file_path, content)

        elif step.tool_name == "edit_file":
            old_text = step.tool_args.get("old_text")
            new_text = step.tool_args.get("new_text", "")
            start_line = step.tool_args.get("start_line")
            end_line = step.tool_args.get("end_line")

            self.diff_preview.preview_file_edit(
                file_path, old_text, new_text, start_line, end_line
            )

    def create_plan_from_function_calls(
        self,
        user_request: str,
        function_calls: List[Dict[str, Any]],
        ai_summary: Optional[str] = None
    ) -> ExecutionPlan:
        """Create a plan from function calls without executing

        Args:
            user_request: User request
            function_calls: Function calls
            ai_summary: AI summary

        Returns:
            ExecutionPlan
        """
        plan = self.plan_analyzer.create_plan_from_request(user_request, ai_summary)

        for fc in function_calls:
            self.plan_analyzer.add_function_call_to_plan(
                plan,
                fc["name"],
                fc["arguments"],
                fc.get("description")
            )

        return plan

    def should_use_plan_mode(
        self,
        function_calls: List[Dict[str, Any]],
        config
    ) -> bool:
        """Determine if plan mode should be used

        Args:
            function_calls: List of function calls
            config: Configuration object

        Returns:
            True if plan mode should be used
        """
        if not config.plan_mode.enabled:
            return False

        # Always use plan mode if any high-risk operations
        high_risk_tools = ["delete_file", "bash", "move_file"]
        for fc in function_calls:
            if fc["name"] in high_risk_tools:
                logger.debug(f"Plan mode triggered by high-risk tool: {fc['name']}")
                return True

        # Use plan mode if threshold exceeded
        if len(function_calls) >= config.plan_mode.auto_plan_threshold:
            logger.debug(f"Plan mode triggered by threshold: {len(function_calls)} calls")
            return True

        # Check if multiple files affected
        affected_files = set()
        for fc in function_calls:
            args = fc.get("arguments", {})
            if "file_path" in args:
                affected_files.add(args["file_path"])
            if "source" in args:
                affected_files.add(args["source"])
            if "destination" in args:
                affected_files.add(args["destination"])

        if len(affected_files) >= config.plan_mode.auto_plan_threshold:
            logger.debug(f"Plan mode triggered by affected files: {len(affected_files)}")
            return True

        return False
