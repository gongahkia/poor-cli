"""
Advanced Planning for poor-cli

Enhanced planning capabilities:
- Dependency graph analysis and visualization
- Plan templates for common tasks
- Conditional steps (if/else logic)
- Cost estimation (API calls, tokens, time)
- Resource requirements analysis
- Parallel execution optimization
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from enum import Enum
from datetime import datetime, timedelta
import json
from pathlib import Path

from poor_cli.plan_mode import ExecutionPlan, PlanStep, PlanStepType, RiskLevel
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class ConditionType(Enum):
    """Types of conditions for conditional steps"""
    FILE_EXISTS = "file_exists"
    FILE_CONTAINS = "file_contains"
    ENV_VAR_SET = "env_var_set"
    PREVIOUS_STEP_SUCCESS = "previous_step_success"
    PREVIOUS_STEP_OUTPUT = "previous_step_output"
    CUSTOM = "custom"


@dataclass
class Condition:
    """Condition for conditional step execution"""
    condition_type: ConditionType
    parameters: Dict[str, Any]
    description: str

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition with current context

        Args:
            context: Execution context with variables and results

        Returns:
            True if condition is met
        """
        if self.condition_type == ConditionType.FILE_EXISTS:
            file_path = Path(self.parameters.get('path', ''))
            return file_path.exists()

        elif self.condition_type == ConditionType.FILE_CONTAINS:
            file_path = Path(self.parameters.get('path', ''))
            pattern = self.parameters.get('pattern', '')
            if not file_path.exists():
                return False
            try:
                content = file_path.read_text()
                return pattern in content
            except:
                return False

        elif self.condition_type == ConditionType.ENV_VAR_SET:
            import os
            var_name = self.parameters.get('variable', '')
            return var_name in os.environ

        elif self.condition_type == ConditionType.PREVIOUS_STEP_SUCCESS:
            step_num = self.parameters.get('step', 0)
            results = context.get('step_results', {})
            return results.get(step_num, {}).get('success', False)

        elif self.condition_type == ConditionType.PREVIOUS_STEP_OUTPUT:
            step_num = self.parameters.get('step', 0)
            expected = self.parameters.get('expected', '')
            results = context.get('step_results', {})
            output = results.get(step_num, {}).get('output', '')
            return expected in output

        return True  # CUSTOM conditions default to True


@dataclass
class ConditionalPlanStep(PlanStep):
    """Plan step with optional conditions"""
    condition: Optional[Condition] = None
    else_step: Optional['ConditionalPlanStep'] = None

    def should_execute(self, context: Dict[str, Any]) -> bool:
        """Check if step should execute

        Args:
            context: Execution context

        Returns:
            True if step should execute
        """
        if self.condition is None:
            return True
        return self.condition.evaluate(context)


@dataclass
class ResourceRequirements:
    """Resource requirements for a plan"""
    estimated_tokens: int = 0
    estimated_api_calls: int = 0
    estimated_time_seconds: int = 0
    disk_space_mb: float = 0
    memory_mb: float = 0
    requires_network: bool = False
    requires_git: bool = False


@dataclass
class CostEstimate:
    """Cost estimation for plan execution"""
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0
    estimated_time: timedelta = field(default_factory=lambda: timedelta())
    breakdown: Dict[str, Any] = field(default_factory=dict)

    def format_time(self) -> str:
        """Format estimated time as human-readable string"""
        seconds = self.estimated_time.total_seconds()
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"


class DependencyGraph:
    """Dependency graph for plan steps"""

    def __init__(self, steps: List[PlanStep]):
        self.steps = steps
        self.adjacency: Dict[int, Set[int]] = {}
        self.reverse_adjacency: Dict[int, Set[int]] = {}
        self._build_graph()

    def _build_graph(self):
        """Build dependency graph from steps"""
        for step in self.steps:
            step_num = step.step_number

            # Initialize adjacency lists
            if step_num not in self.adjacency:
                self.adjacency[step_num] = set()
            if step_num not in self.reverse_adjacency:
                self.reverse_adjacency[step_num] = set()

            # Add dependencies
            for dep in step.dependencies:
                self.adjacency[dep].add(step_num)
                self.reverse_adjacency[step_num].add(dep)

    def get_execution_order(self) -> List[List[int]]:
        """Get execution order as list of batches (parallel execution possible)

        Returns:
            List of batches, where each batch can execute in parallel
        """
        # Topological sort with parallel batching
        in_degree = {step.step_number: len(step.dependencies) for step in self.steps}
        batches = []

        while in_degree:
            # Find all steps with no dependencies (can execute in parallel)
            batch = [step_num for step_num, degree in in_degree.items() if degree == 0]

            if not batch:
                logger.warning("Circular dependency detected!")
                # Return remaining steps as separate batches
                return batches + [[step_num] for step_num in in_degree.keys()]

            batches.append(batch)

            # Remove these steps and update in-degrees
            for step_num in batch:
                del in_degree[step_num]
                # Decrease in-degree for dependent steps
                for dependent in self.adjacency.get(step_num, []):
                    if dependent in in_degree:
                        in_degree[dependent] -= 1

        return batches

    def get_critical_path(self) -> List[int]:
        """Get critical path (longest dependency chain)

        Returns:
            List of step numbers in critical path
        """
        # Find step with no dependents (end of graph)
        end_steps = [
            step.step_number for step in self.steps
            if not self.adjacency.get(step.step_number, set())
        ]

        if not end_steps:
            return []

        # Find longest path to each end step
        longest_path = []
        for end_step in end_steps:
            path = self._longest_path_to(end_step)
            if len(path) > len(longest_path):
                longest_path = path

        return longest_path

    def _longest_path_to(self, step_num: int) -> List[int]:
        """Find longest path to a step (recursive)"""
        dependencies = self.reverse_adjacency.get(step_num, set())

        if not dependencies:
            return [step_num]

        # Find longest path through dependencies
        longest = []
        for dep in dependencies:
            path = self._longest_path_to(dep)
            if len(path) > len(longest):
                longest = path

        return longest + [step_num]

    def visualize_ascii(self) -> str:
        """Generate ASCII visualization of dependency graph"""
        lines = []
        lines.append("Dependency Graph:")
        lines.append("")

        execution_order = self.get_execution_order()

        for batch_num, batch in enumerate(execution_order, 1):
            if len(batch) == 1:
                lines.append(f"  [{batch[0]}]")
            else:
                lines.append(f"  Parallel: {batch}")

            # Show dependencies
            for step_num in batch:
                deps = self.reverse_adjacency.get(step_num, set())
                if deps:
                    lines.append(f"    └─ depends on: {list(deps)}")

        # Show critical path
        critical = self.get_critical_path()
        if critical:
            lines.append("")
            lines.append(f"Critical Path: {' → '.join(map(str, critical))}")

        return "\n".join(lines)


class PlanTemplate:
    """Template for common plan patterns"""

    def __init__(
        self,
        template_id: str,
        name: str,
        description: str,
        steps_template: List[Dict[str, Any]]
    ):
        self.template_id = template_id
        self.name = name
        self.description = description
        self.steps_template = steps_template

    def instantiate(self, parameters: Dict[str, Any]) -> ExecutionPlan:
        """Create execution plan from template

        Args:
            parameters: Template parameters

        Returns:
            Instantiated execution plan
        """
        plan_id = f"{self.template_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        plan = ExecutionPlan(
            plan_id=plan_id,
            user_request=parameters.get('user_request', f'From template: {self.name}'),
            summary=self.description
        )

        # Instantiate steps
        for idx, step_template in enumerate(self.steps_template, 1):
            # Replace template variables
            description = self._substitute_vars(step_template['description'], parameters)
            tool_args = {
                k: self._substitute_vars(v, parameters)
                for k, v in step_template.get('tool_args', {}).items()
            }

            step = PlanStep(
                step_number=idx,
                step_type=PlanStepType(step_template['step_type']),
                description=description,
                tool_name=step_template['tool_name'],
                tool_args=tool_args,
                risk_level=RiskLevel(step_template.get('risk_level', 'low')),
                affected_files=step_template.get('affected_files', []),
                dependencies=step_template.get('dependencies', [])
            )

            plan.add_step(step)

        return plan

    def _substitute_vars(self, value: Any, parameters: Dict[str, Any]) -> Any:
        """Substitute template variables"""
        if isinstance(value, str):
            for key, val in parameters.items():
                placeholder = f"{{{key}}}"
                if placeholder in value:
                    value = value.replace(placeholder, str(val))
        return value


class PlanTemplateLibrary:
    """Library of plan templates"""

    def __init__(self):
        self.templates: Dict[str, PlanTemplate] = {}
        self._load_default_templates()

    def _load_default_templates(self):
        """Load default templates"""
        # Template: Add new feature
        self.add_template(PlanTemplate(
            template_id="add_feature",
            name="Add New Feature",
            description="Standard workflow for adding a new feature",
            steps_template=[
                {
                    'step_type': 'read_file',
                    'description': 'Read existing code: {target_file}',
                    'tool_name': 'read_file',
                    'tool_args': {'file_path': '{target_file}'},
                    'risk_level': 'safe'
                },
                {
                    'step_type': 'edit_file',
                    'description': 'Add feature: {feature_name}',
                    'tool_name': 'edit_file',
                    'tool_args': {'file_path': '{target_file}'},
                    'risk_level': 'medium',
                    'affected_files': ['{target_file}'],
                    'dependencies': [1]
                },
                {
                    'step_type': 'bash',
                    'description': 'Run tests',
                    'tool_name': 'bash',
                    'tool_args': {'command': '{test_command}'},
                    'risk_level': 'low',
                    'dependencies': [2]
                }
            ]
        ))

        # Template: Fix bug
        self.add_template(PlanTemplate(
            template_id="fix_bug",
            name="Fix Bug",
            description="Standard workflow for fixing a bug",
            steps_template=[
                {
                    'step_type': 'search',
                    'description': 'Search for bug location',
                    'tool_name': 'grep_files',
                    'tool_args': {'pattern': '{bug_pattern}'},
                    'risk_level': 'safe'
                },
                {
                    'step_type': 'read_file',
                    'description': 'Read affected file',
                    'tool_name': 'read_file',
                    'tool_args': {'file_path': '{affected_file}'},
                    'risk_level': 'safe',
                    'dependencies': [1]
                },
                {
                    'step_type': 'edit_file',
                    'description': 'Apply bug fix',
                    'tool_name': 'edit_file',
                    'tool_args': {'file_path': '{affected_file}'},
                    'risk_level': 'medium',
                    'affected_files': ['{affected_file}'],
                    'dependencies': [2]
                },
                {
                    'step_type': 'bash',
                    'description': 'Verify fix with tests',
                    'tool_name': 'bash',
                    'tool_args': {'command': 'pytest {affected_file}'},
                    'risk_level': 'low',
                    'dependencies': [3]
                }
            ]
        ))

        # Template: Refactor code
        self.add_template(PlanTemplate(
            template_id="refactor",
            name="Refactor Code",
            description="Standard workflow for refactoring",
            steps_template=[
                {
                    'step_type': 'read_file',
                    'description': 'Read code to refactor',
                    'tool_name': 'read_file',
                    'tool_args': {'file_path': '{file_path}'},
                    'risk_level': 'safe'
                },
                {
                    'step_type': 'other',
                    'description': 'Create checkpoint before refactoring',
                    'tool_name': 'checkpoint',
                    'tool_args': {'description': 'Before {refactor_type}'},
                    'risk_level': 'safe',
                    'dependencies': [1]
                },
                {
                    'step_type': 'edit_file',
                    'description': 'Apply refactoring: {refactor_type}',
                    'tool_name': 'edit_file',
                    'tool_args': {'file_path': '{file_path}'},
                    'risk_level': 'medium',
                    'affected_files': ['{file_path}'],
                    'dependencies': [2]
                },
                {
                    'step_type': 'bash',
                    'description': 'Run tests to verify refactoring',
                    'tool_name': 'bash',
                    'tool_args': {'command': '{test_command}'},
                    'risk_level': 'low',
                    'dependencies': [3]
                }
            ]
        ))

    def add_template(self, template: PlanTemplate):
        """Add template to library"""
        self.templates[template.template_id] = template

    def get_template(self, template_id: str) -> Optional[PlanTemplate]:
        """Get template by ID"""
        return self.templates.get(template_id)

    def list_templates(self) -> List[Tuple[str, str, str]]:
        """List available templates

        Returns:
            List of (id, name, description) tuples
        """
        return [
            (t.template_id, t.name, t.description)
            for t in self.templates.values()
        ]


class CostEstimator:
    """Estimates cost of plan execution"""

    # Token costs (per 1M tokens) for common models
    MODEL_COSTS = {
        'gpt-4': {'input': 30.0, 'output': 60.0},
        'gpt-4-turbo': {'input': 10.0, 'output': 30.0},
        'gpt-3.5-turbo': {'input': 0.5, 'output': 1.5},
        'claude-3-opus': {'input': 15.0, 'output': 75.0},
        'claude-3-sonnet': {'input': 3.0, 'output': 15.0},
        'claude-3-haiku': {'input': 0.25, 'output': 1.25},
        'gemini-pro': {'input': 0.5, 'output': 1.5},
    }

    def __init__(self, model_name: str = 'gpt-3.5-turbo'):
        self.model_name = model_name
        self.costs = self.MODEL_COSTS.get(model_name, {'input': 1.0, 'output': 2.0})

    def estimate_plan_cost(
        self,
        plan: ExecutionPlan,
        context_tokens: int = 1000
    ) -> CostEstimate:
        """Estimate cost of executing a plan

        Args:
            plan: Execution plan
            context_tokens: Estimated context tokens per API call

        Returns:
            Cost estimate
        """
        estimate = CostEstimate()

        # Count API calls and token usage per step
        for step in plan.steps:
            step_cost = self._estimate_step_cost(step, context_tokens)

            estimate.api_calls += step_cost['api_calls']
            estimate.input_tokens += step_cost['input_tokens']
            estimate.output_tokens += step_cost['output_tokens']
            estimate.estimated_time += timedelta(seconds=step_cost['time_seconds'])

            estimate.breakdown[f"step_{step.step_number}"] = step_cost

        # Calculate total tokens and cost
        estimate.total_tokens = estimate.input_tokens + estimate.output_tokens

        input_cost = (estimate.input_tokens / 1_000_000) * self.costs['input']
        output_cost = (estimate.output_tokens / 1_000_000) * self.costs['output']
        estimate.estimated_cost_usd = input_cost + output_cost

        return estimate

    def _estimate_step_cost(
        self,
        step: PlanStep,
        context_tokens: int
    ) -> Dict[str, Any]:
        """Estimate cost of a single step"""
        # Different step types have different costs
        if step.step_type == PlanStepType.READ_FILE:
            # Reading typically doesn't need AI
            return {
                'api_calls': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'time_seconds': 1
            }

        elif step.step_type in [PlanStepType.WRITE_FILE, PlanStepType.EDIT_FILE]:
            # Writing/editing requires AI generation
            return {
                'api_calls': 1,
                'input_tokens': context_tokens + 500,  # Context + instructions
                'output_tokens': 1000,  # Estimated code generation
                'time_seconds': 5
            }

        elif step.step_type == PlanStepType.BASH_COMMAND:
            # Bash might need AI to construct command
            return {
                'api_calls': 1,
                'input_tokens': context_tokens + 200,
                'output_tokens': 100,  # Short command
                'time_seconds': 3
            }

        else:
            # Default estimate
            return {
                'api_calls': 1,
                'input_tokens': context_tokens,
                'output_tokens': 500,
                'time_seconds': 3
            }


class AdvancedPlanManager:
    """Manager for advanced planning features"""

    def __init__(self):
        self.template_library = PlanTemplateLibrary()
        self.cost_estimator = CostEstimator()

    def create_plan_from_template(
        self,
        template_id: str,
        parameters: Dict[str, Any]
    ) -> Optional[ExecutionPlan]:
        """Create plan from template"""
        template = self.template_library.get_template(template_id)
        if not template:
            logger.error(f"Template not found: {template_id}")
            return None

        return template.instantiate(parameters)

    def analyze_dependencies(self, plan: ExecutionPlan) -> DependencyGraph:
        """Analyze plan dependencies"""
        return DependencyGraph(plan.steps)

    def estimate_cost(self, plan: ExecutionPlan) -> CostEstimate:
        """Estimate plan execution cost"""
        return self.cost_estimator.estimate_plan_cost(plan)

    def optimize_execution_order(self, plan: ExecutionPlan) -> List[List[int]]:
        """Get optimized execution order for parallel execution"""
        graph = DependencyGraph(plan.steps)
        return graph.get_execution_order()
