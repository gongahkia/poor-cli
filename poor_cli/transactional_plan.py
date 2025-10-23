"""
Transactional plan execution for poor-cli

Provides automatic rollback on plan execution failures.
"""

from typing import Callable, Awaitable, Dict, Any, List, Optional
from poor_cli.plan_mode import ExecutionPlan
from poor_cli.plan_executor import PlanExecutor
from poor_cli.checkpoint import CheckpointManager
from poor_cli.exceptions import PoorCLIError, setup_logger

logger = setup_logger(__name__)


class PlanExecutionError(PoorCLIError):
    """Raised when plan execution fails"""
    pass


class TransactionalPlanExecutor(PlanExecutor):
    """Plan executor with automatic rollback on failure"""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        **kwargs
    ):
        """Initialize transactional executor

        Args:
            checkpoint_manager: CheckpointManager instance
            **kwargs: Additional args for PlanExecutor
        """
        super().__init__(checkpoint_manager=checkpoint_manager, **kwargs)
        self.transaction_checkpoint = None

    async def execute_with_transaction(
        self,
        user_request: str,
        function_calls: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        ai_summary: Optional[str] = None,
        auto_rollback: bool = True
    ) -> tuple[bool, List[str], Optional[str]]:
        """Execute plan with transaction support

        Args:
            user_request: User's original request
            function_calls: Function calls to execute
            tool_executor: Tool execution function
            ai_summary: AI summary
            auto_rollback: Whether to auto-rollback on failure

        Returns:
            Tuple of (success, results, rollback_checkpoint_id)

        If execution fails and auto_rollback=True, the workspace will be
        restored to the state before plan execution started.
        """
        from pathlib import Path

        # Create pre-execution checkpoint
        try:
            affected_files = self._get_affected_files_from_calls(function_calls)
            existing_files = [f for f in affected_files if Path(f).exists()]

            if existing_files:
                self.transaction_checkpoint = self.checkpoint_manager.create_checkpoint(
                    file_paths=existing_files,
                    description=f"Transaction checkpoint for: {user_request[:50]}",
                    operation_type="transaction",
                    tags=["auto", "transaction"]
                )
                checkpoint_id = self.transaction_checkpoint.checkpoint_id
                logger.info(f"Created transaction checkpoint: {checkpoint_id}")
                self.console.print(
                    f"[dim]📸 Transaction checkpoint: {checkpoint_id}[/dim]\n"
                )
            else:
                checkpoint_id = None
                logger.info("No existing files to checkpoint")

        except Exception as e:
            logger.warning(f"Failed to create transaction checkpoint: {e}")
            checkpoint_id = None

        # Execute plan
        try:
            success, results = await self.execute_with_plan(
                user_request,
                function_calls,
                tool_executor,
                ai_summary
            )

            if success:
                logger.info("Plan executed successfully")
                return (True, results, checkpoint_id)
            else:
                # Plan was rejected or failed
                if auto_rollback and checkpoint_id:
                    logger.info("Plan failed, rolling back...")
                    await self._rollback_transaction(checkpoint_id)
                    return (False, results, checkpoint_id)
                else:
                    return (False, results, checkpoint_id)

        except Exception as e:
            logger.error(f"Plan execution error: {e}")

            # Rollback if auto_rollback enabled
            if auto_rollback and checkpoint_id:
                logger.info("Exception during execution, rolling back...")
                await self._rollback_transaction(checkpoint_id)

            raise PlanExecutionError(f"Plan execution failed: {e}") from e

    async def _rollback_transaction(self, checkpoint_id: str):
        """Rollback to transaction checkpoint

        Args:
            checkpoint_id: Transaction checkpoint ID
        """
        try:
            self.console.print(
                "\n[yellow]⚠️  Rolling back changes...[/yellow]"
            )

            restored = self.checkpoint_manager.restore_checkpoint(checkpoint_id)

            self.console.print(
                f"[green]✓ Rolled back {restored} file(s)[/green]\n"
            )

            logger.info(f"Rolled back to checkpoint {checkpoint_id}")

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            self.console.print(
                f"[red]✗ Rollback failed: {e}[/red]\n"
            )
            raise

    def _get_affected_files_from_calls(
        self,
        function_calls: List[Dict[str, Any]]
    ) -> List[str]:
        """Extract affected files from function calls

        Args:
            function_calls: List of function call dicts

        Returns:
            List of file paths
        """
        affected = []

        for fc in function_calls:
            args = fc.get("arguments", {})

            # File operation args
            if "file_path" in args:
                affected.append(args["file_path"])
            if "source" in args:
                affected.append(args["source"])
            if "destination" in args:
                affected.append(args["destination"])

        return list(set(affected))  # Deduplicate

    async def execute_with_retry(
        self,
        user_request: str,
        function_calls: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        max_retries: int = 3,
        ai_summary: Optional[str] = None
    ) -> tuple[bool, List[str], int]:
        """Execute plan with retry logic

        Args:
            user_request: User request
            function_calls: Function calls
            tool_executor: Tool executor
            max_retries: Maximum retry attempts
            ai_summary: AI summary

        Returns:
            Tuple of (success, results, attempts_made)
        """
        attempts = 0

        for attempt in range(max_retries):
            attempts += 1

            try:
                self.console.print(
                    f"[dim]Attempt {attempt + 1}/{max_retries}...[/dim]"
                )

                success, results, checkpoint_id = await self.execute_with_transaction(
                    user_request,
                    function_calls,
                    tool_executor,
                    ai_summary,
                    auto_rollback=True
                )

                if success:
                    return (True, results, attempts)

                # Plan rejected, don't retry
                logger.info("Plan rejected by user, not retrying")
                return (False, results, attempts)

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    self.console.print(
                        f"[yellow]Attempt {attempt + 1} failed, retrying...[/yellow]\n"
                    )
                    # Small delay before retry
                    import asyncio
                    await asyncio.sleep(1)
                else:
                    self.console.print(
                        f"[red]All {max_retries} attempts failed[/red]\n"
                    )
                    raise

        return (False, [], attempts)

    async def execute_with_partial_rollback(
        self,
        user_request: str,
        function_calls: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        ai_summary: Optional[str] = None
    ) -> tuple[bool, List[str], List[int]]:
        """Execute plan with partial rollback on step failures

        If a step fails, only that step is rolled back, not the entire plan.

        Args:
            user_request: User request
            function_calls: Function calls
            tool_executor: Tool executor
            ai_summary: AI summary

        Returns:
            Tuple of (overall_success, results, failed_step_numbers)
        """
        # Create plan
        plan = self.plan_analyzer.create_plan_from_request(user_request, ai_summary)

        for fc in function_calls:
            self.plan_analyzer.add_function_call_to_plan(
                plan,
                fc["name"],
                fc["arguments"],
                fc.get("description")
            )

        # Show plan and get approval
        self.plan_display.display_plan(plan, show_details=True)
        choice = self.plan_display.request_approval(plan)

        if choice != "approve":
            return (False, [], [])

        # Execute with per-step checkpoints
        results = []
        failed_steps = []

        for step in plan.steps:
            # Create step checkpoint
            step_checkpoint = None
            from pathlib import Path

            if step.affected_files:
                existing = [f for f in step.affected_files if Path(f).exists()]
                if existing:
                    try:
                        step_checkpoint = self.checkpoint_manager.create_checkpoint(
                            file_paths=existing,
                            description=f"Before step {step.step_number}",
                            operation_type="step",
                            tags=["auto", "step"]
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create step checkpoint: {e}")

            # Execute step
            try:
                self.plan_display.display_execution_progress(step)

                result = await tool_executor(step.tool_name, step.tool_args)
                results.append(result)

                self.console.print("[dim green]✓ Completed[/dim green]")

            except Exception as e:
                logger.error(f"Step {step.step_number} failed: {e}")
                failed_steps.append(step.step_number)

                # Rollback this step
                if step_checkpoint:
                    logger.info(f"Rolling back step {step.step_number}")
                    self.checkpoint_manager.restore_checkpoint(
                        step_checkpoint.checkpoint_id
                    )
                    self.console.print(
                        f"[yellow]✗ Step failed and rolled back[/yellow]"
                    )
                else:
                    self.console.print(f"[red]✗ Step failed (no rollback)[/red]")

                results.append(f"Error: {str(e)}")

        overall_success = len(failed_steps) == 0

        self.console.print()
        self.console.print(
            f"[bold]Completed:[/bold] {len(plan.steps) - len(failed_steps)}/{len(plan.steps)} steps"
        )

        if failed_steps:
            self.console.print(
                f"[yellow]Failed steps: {', '.join(map(str, failed_steps))}[/yellow]"
            )

        return (overall_success, results, failed_steps)
