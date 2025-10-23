"""
Plan Analyzer for poor-cli

Analyzes AI responses and generates execution plans.
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from poor_cli.plan_mode import (
    ExecutionPlan, PlanStep, PlanStepType, RiskLevel
)
from poor_cli.exceptions import ValidationError, setup_logger

logger = setup_logger(__name__)


class PlanAnalyzer:
    """Analyzes function calls and generates execution plans"""

    # Risk level mapping for tools
    TOOL_RISK_LEVELS = {
        "read_file": RiskLevel.SAFE,
        "glob_files": RiskLevel.SAFE,
        "grep_files": RiskLevel.SAFE,
        "list_directory": RiskLevel.SAFE,
        "git_status": RiskLevel.SAFE,
        "git_diff": RiskLevel.SAFE,
        "write_file": RiskLevel.MEDIUM,
        "edit_file": RiskLevel.MEDIUM,
        "create_directory": RiskLevel.LOW,
        "copy_file": RiskLevel.LOW,
        "move_file": RiskLevel.MEDIUM,
        "delete_file": RiskLevel.HIGH,
        "bash": RiskLevel.HIGH,  # Default high, can be lowered for safe commands
        "diff_files": RiskLevel.SAFE,
    }

    # Safe bash commands that are read-only
    SAFE_BASH_COMMANDS = [
        "ls", "pwd", "echo", "cat", "head", "tail", "grep",
        "find", "which", "whoami", "date", "wc", "sort", "uniq"
    ]

    def __init__(self):
        self.plan_counter = 0

    def generate_plan_id(self) -> str:
        """Generate unique plan ID"""
        self.plan_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"plan_{timestamp}_{self.plan_counter}"

    def create_plan_from_request(
        self,
        user_request: str,
        ai_summary: Optional[str] = None
    ) -> ExecutionPlan:
        """Create an execution plan from a user request

        Args:
            user_request: The user's original request
            ai_summary: Optional AI-generated summary of what will be done

        Returns:
            Empty ExecutionPlan ready to be populated
        """
        plan = ExecutionPlan(
            plan_id=self.generate_plan_id(),
            user_request=user_request,
            summary=ai_summary or "Analyzing request..."
        )
        logger.info(f"Created plan {plan.plan_id} for request: {user_request[:100]}")
        return plan

    def add_function_call_to_plan(
        self,
        plan: ExecutionPlan,
        function_name: str,
        function_args: Dict[str, Any],
        description: Optional[str] = None
    ) -> PlanStep:
        """Add a function call as a step to the plan

        Args:
            plan: The execution plan to add to
            function_name: Name of the function/tool
            function_args: Arguments for the function
            description: Human-readable description of what this step does

        Returns:
            The created PlanStep
        """
        step_number = len(plan.steps) + 1

        # Determine step type
        step_type = self._map_function_to_step_type(function_name)

        # Determine risk level
        risk_level = self._assess_risk_level(function_name, function_args)

        # Get affected files
        affected_files = self._extract_affected_files(function_name, function_args)

        # Generate description if not provided
        if not description:
            description = self._generate_step_description(
                function_name, function_args
            )

        # Create step
        step = PlanStep(
            step_number=step_number,
            step_type=step_type,
            description=description,
            tool_name=function_name,
            tool_args=function_args,
            risk_level=risk_level,
            affected_files=affected_files,
            estimated_duration=self._estimate_duration(function_name)
        )

        plan.add_step(step)
        logger.debug(f"Added step {step_number} to plan {plan.plan_id}: {function_name}")

        return step

    def _map_function_to_step_type(self, function_name: str) -> PlanStepType:
        """Map function name to step type"""
        mapping = {
            "read_file": PlanStepType.READ_FILE,
            "write_file": PlanStepType.WRITE_FILE,
            "edit_file": PlanStepType.EDIT_FILE,
            "delete_file": PlanStepType.DELETE_FILE,
            "create_directory": PlanStepType.CREATE_DIR,
            "bash": PlanStepType.BASH_COMMAND,
            "git_status": PlanStepType.GIT_OPERATION,
            "git_diff": PlanStepType.GIT_OPERATION,
            "glob_files": PlanStepType.SEARCH,
            "grep_files": PlanStepType.SEARCH,
        }
        return mapping.get(function_name, PlanStepType.OTHER)

    def _assess_risk_level(
        self,
        function_name: str,
        function_args: Dict[str, Any]
    ) -> RiskLevel:
        """Assess risk level of a function call"""
        # Get base risk level
        base_risk = self.TOOL_RISK_LEVELS.get(function_name, RiskLevel.MEDIUM)

        # Special handling for bash commands
        if function_name == "bash":
            command = function_args.get("command", "").strip().lower()
            # Check if it's a safe command
            for safe_cmd in self.SAFE_BASH_COMMANDS:
                if command.startswith(safe_cmd):
                    return RiskLevel.SAFE

            # Check for destructive operations
            if any(danger in command for danger in ["rm ", "mv ", "dd ", "format", "> /dev/"]):
                return RiskLevel.CRITICAL

            # Check for sudo
            if command.startswith("sudo"):
                return RiskLevel.CRITICAL

        # Check for system paths
        if function_name in ["write_file", "edit_file", "delete_file"]:
            file_path = function_args.get("file_path", "")
            if any(path in file_path for path in ["/etc/", "/sys/", "/proc/", "/dev/"]):
                return RiskLevel.CRITICAL

        return base_risk

    def _extract_affected_files(
        self,
        function_name: str,
        function_args: Dict[str, Any]
    ) -> List[str]:
        """Extract files that will be affected by this operation"""
        affected = []

        # File operations
        if "file_path" in function_args:
            affected.append(function_args["file_path"])

        if "source" in function_args:
            affected.append(function_args["source"])

        if "destination" in function_args:
            affected.append(function_args["destination"])

        if "file1" in function_args:
            affected.append(function_args["file1"])

        if "file2" in function_args:
            affected.append(function_args["file2"])

        return affected

    def _generate_step_description(
        self,
        function_name: str,
        function_args: Dict[str, Any]
    ) -> str:
        """Generate human-readable description of a step"""
        descriptions = {
            "read_file": lambda args: f"Read file: {args.get('file_path', 'unknown')}",
            "write_file": lambda args: f"Write file: {args.get('file_path', 'unknown')}",
            "edit_file": lambda args: f"Edit file: {args.get('file_path', 'unknown')}",
            "delete_file": lambda args: f"Delete file: {args.get('file_path', 'unknown')}",
            "create_directory": lambda args: f"Create directory: {args.get('path', 'unknown')}",
            "copy_file": lambda args: f"Copy {args.get('source', '?')} to {args.get('destination', '?')}",
            "move_file": lambda args: f"Move {args.get('source', '?')} to {args.get('destination', '?')}",
            "bash": lambda args: f"Execute: {args.get('command', 'unknown')[:50]}",
            "glob_files": lambda args: f"Find files matching: {args.get('pattern', 'unknown')}",
            "grep_files": lambda args: f"Search for: {args.get('pattern', 'unknown')}",
            "git_status": lambda args: "Check git status",
            "git_diff": lambda args: "Show git differences",
        }

        generator = descriptions.get(function_name)
        if generator:
            return generator(function_args)

        return f"Execute {function_name}"

    def _estimate_duration(self, function_name: str) -> str:
        """Estimate how long a step will take"""
        durations = {
            "read_file": "instant",
            "write_file": "instant",
            "edit_file": "instant",
            "delete_file": "instant",
            "create_directory": "instant",
            "glob_files": "1-5s",
            "grep_files": "1-10s",
            "bash": "varies",
            "git_status": "1-2s",
            "git_diff": "1-5s",
        }
        return durations.get(function_name, "unknown")

    def validate_plan(self, plan: ExecutionPlan) -> List[str]:
        """Validate a plan and return any warnings

        Returns:
            List of warning messages
        """
        warnings = []

        # Check for high-risk operations
        high_risk_steps = plan.get_high_risk_steps()
        if high_risk_steps:
            warnings.append(
                f"Plan contains {len(high_risk_steps)} high-risk operation(s)"
            )

        # Check for operations on many files
        affected_files = plan.get_affected_files()
        if len(affected_files) > 10:
            warnings.append(
                f"Plan will affect {len(affected_files)} files"
            )

        # Check for bash commands with sudo
        for step in plan.steps:
            if step.tool_name == "bash":
                command = step.tool_args.get("command", "")
                if "sudo" in command:
                    warnings.append(
                        f"Step {step.step_number} uses sudo (elevated privileges)"
                    )

        return warnings
