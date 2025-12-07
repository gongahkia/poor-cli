"""
Plan Analysis and Risk Assessment for poor-cli

Advanced analysis tools:
- Blast radius calculation (impact analysis)
- Rollback simulation
- Risk scoring and assessment
- Conflict detection
- Safety recommendations
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
import re

from poor_cli.plan_mode import ExecutionPlan, PlanStep, PlanStepType, RiskLevel
from poor_cli.checkpoint import CheckpointManager
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class ImpactSeverity(Enum):
    """Impact severity levels"""
    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass
class BlastRadius:
    """Blast radius analysis for a plan"""
    affected_files: Set[str] = field(default_factory=set)
    affected_directories: Set[str] = field(default_factory=set)
    affected_systems: Set[str] = field(default_factory=set)
    destructive_operations: List[str] = field(default_factory=list)
    reversible: bool = True
    impact_severity: ImpactSeverity = ImpactSeverity.NEGLIGIBLE
    estimated_recovery_time: str = "instant"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "affected_files": list(self.affected_files),
            "affected_directories": list(self.affected_directories),
            "affected_systems": list(self.affected_systems),
            "destructive_operations": self.destructive_operations,
            "reversible": self.reversible,
            "impact_severity": self.impact_severity.value,
            "estimated_recovery_time": self.estimated_recovery_time,
            "total_affected_files": len(self.affected_files)
        }


@dataclass
class RiskAssessment:
    """Comprehensive risk assessment"""
    overall_risk_score: float  # 0-100
    risk_level: RiskLevel
    risk_factors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    blast_radius: Optional[BlastRadius] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "overall_risk_score": self.overall_risk_score,
            "risk_level": self.risk_level.value,
            "risk_factors": self.risk_factors,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "conflicts": self.conflicts,
            "blast_radius": self.blast_radius.to_dict() if self.blast_radius else None
        }


@dataclass
class RollbackPlan:
    """Plan for rolling back changes"""
    rollback_steps: List[str] = field(default_factory=list)
    checkpoint_required: bool = True
    manual_intervention_needed: bool = False
    estimated_rollback_time: str = "instant"
    data_loss_risk: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rollback_steps": self.rollback_steps,
            "checkpoint_required": self.checkpoint_required,
            "manual_intervention_needed": self.manual_intervention_needed,
            "estimated_rollback_time": self.estimated_rollback_time,
            "data_loss_risk": self.data_loss_risk
        }


class PlanAnalyzer:
    """Analyzes execution plans for risks and impacts"""

    # Critical file patterns
    CRITICAL_PATTERNS = [
        r'\.env',
        r'config\.ya?ml',
        r'secrets',
        r'credentials',
        r'password',
        r'database',
        r'\.git/',
        r'package\.json',
        r'requirements\.txt',
        r'Cargo\.toml',
        r'go\.mod'
    ]

    # Destructive bash commands
    DESTRUCTIVE_COMMANDS = [
        'rm', 'rmdir', 'dd', 'mkfs', 'format',
        'fdisk', 'parted', 'shred', 'truncate',
        '> /dev/', 'DROP TABLE', 'DROP DATABASE'
    ]

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()

    def analyze_plan(self, plan: ExecutionPlan) -> RiskAssessment:
        """Perform comprehensive risk assessment

        Args:
            plan: Execution plan to analyze

        Returns:
            Risk assessment
        """
        assessment = RiskAssessment(
            overall_risk_score=0.0,
            risk_level=RiskLevel.SAFE
        )

        # Calculate blast radius
        assessment.blast_radius = self.calculate_blast_radius(plan)

        # Analyze risk factors
        risk_score = 0.0

        # Factor 1: Step risk levels (0-40 points)
        risk_score += self._score_step_risks(plan, assessment)

        # Factor 2: File impact (0-30 points)
        risk_score += self._score_file_impact(plan, assessment)

        # Factor 3: Destructive operations (0-20 points)
        risk_score += self._score_destructive_ops(plan, assessment)

        # Factor 4: Dependencies and conflicts (0-10 points)
        risk_score += self._score_dependencies(plan, assessment)

        assessment.overall_risk_score = min(risk_score, 100.0)
        assessment.risk_level = self._score_to_risk_level(risk_score)

        # Generate recommendations
        self._generate_recommendations(plan, assessment)

        return assessment

    def calculate_blast_radius(self, plan: ExecutionPlan) -> BlastRadius:
        """Calculate blast radius (impact area) of plan

        Args:
            plan: Execution plan

        Returns:
            Blast radius analysis
        """
        blast_radius = BlastRadius()

        for step in plan.steps:
            # Collect affected files
            blast_radius.affected_files.update(step.affected_files)

            # Determine affected directories
            for file_path in step.affected_files:
                path = Path(file_path)
                blast_radius.affected_directories.add(str(path.parent))

            # Check for destructive operations
            if step.step_type == PlanStepType.DELETE_FILE:
                blast_radius.destructive_operations.append(
                    f"Delete file: {', '.join(step.affected_files)}"
                )
                blast_radius.reversible = False

            elif step.step_type == PlanStepType.BASH_COMMAND:
                command = step.tool_args.get('command', '')
                if any(cmd in command for cmd in self.DESTRUCTIVE_COMMANDS):
                    blast_radius.destructive_operations.append(
                        f"Destructive bash: {command[:50]}"
                    )
                    blast_radius.reversible = False

            # Identify affected systems
            if step.step_type == PlanStepType.BASH_COMMAND:
                command = step.tool_args.get('command', '')
                if 'git' in command:
                    blast_radius.affected_systems.add('git')
                if any(db in command.lower() for db in ['mysql', 'postgres', 'mongo', 'redis']):
                    blast_radius.affected_systems.add('database')
                if 'docker' in command:
                    blast_radius.affected_systems.add('docker')
                if 'npm' in command or 'yarn' in command:
                    blast_radius.affected_systems.add('package_manager')

        # Determine impact severity
        file_count = len(blast_radius.affected_files)
        has_destructive = len(blast_radius.destructive_operations) > 0

        if has_destructive or file_count > 50:
            blast_radius.impact_severity = ImpactSeverity.CRITICAL
            blast_radius.estimated_recovery_time = "30+ minutes"
        elif file_count > 20:
            blast_radius.impact_severity = ImpactSeverity.MAJOR
            blast_radius.estimated_recovery_time = "10-30 minutes"
        elif file_count > 5:
            blast_radius.impact_severity = ImpactSeverity.MODERATE
            blast_radius.estimated_recovery_time = "5-10 minutes"
        elif file_count > 0:
            blast_radius.impact_severity = ImpactSeverity.MINOR
            blast_radius.estimated_recovery_time = "1-5 minutes"
        else:
            blast_radius.impact_severity = ImpactSeverity.NEGLIGIBLE
            blast_radius.estimated_recovery_time = "instant"

        return blast_radius

    def simulate_rollback(
        self,
        plan: ExecutionPlan,
        checkpoint_manager: Optional[CheckpointManager] = None
    ) -> RollbackPlan:
        """Simulate rollback scenario

        Args:
            plan: Execution plan
            checkpoint_manager: Optional checkpoint manager

        Returns:
            Rollback plan
        """
        rollback = RollbackPlan()

        # Check if checkpoint exists
        if checkpoint_manager:
            recent_checkpoints = checkpoint_manager.list_checkpoints(limit=1)
            if recent_checkpoints:
                rollback.checkpoint_required = False
                rollback.rollback_steps.append(
                    f"Restore checkpoint: {recent_checkpoints[0].checkpoint_id}"
                )
                rollback.estimated_rollback_time = "1-2 minutes"
            else:
                rollback.checkpoint_required = True
                rollback.rollback_steps.append(
                    "No checkpoint available - create one before proceeding"
                )

        # Analyze steps for rollback complexity
        for step in plan.steps:
            if step.step_type == PlanStepType.WRITE_FILE:
                rollback.rollback_steps.append(
                    f"Delete created file: {step.affected_files[0] if step.affected_files else 'unknown'}"
                )

            elif step.step_type == PlanStepType.EDIT_FILE:
                rollback.rollback_steps.append(
                    f"Restore original: {step.affected_files[0] if step.affected_files else 'unknown'}"
                )

            elif step.step_type == PlanStepType.DELETE_FILE:
                rollback.rollback_steps.append(
                    f"Cannot restore deleted file: {step.affected_files[0] if step.affected_files else 'unknown'}"
                )
                rollback.data_loss_risk = True
                rollback.manual_intervention_needed = True

            elif step.step_type == PlanStepType.BASH_COMMAND:
                command = step.tool_args.get('command', '')

                if 'git commit' in command:
                    rollback.rollback_steps.append("Git reset to undo commit")
                elif 'git push' in command:
                    rollback.rollback_steps.append("Git force push to revert (dangerous)")
                    rollback.manual_intervention_needed = True
                elif any(cmd in command for cmd in self.DESTRUCTIVE_COMMANDS):
                    rollback.rollback_steps.append(f"Cannot undo: {command[:50]}")
                    rollback.data_loss_risk = True
                    rollback.manual_intervention_needed = True

        # Estimate rollback time
        if rollback.manual_intervention_needed:
            rollback.estimated_rollback_time = "30+ minutes (manual)"
        elif len(rollback.rollback_steps) > 10:
            rollback.estimated_rollback_time = "10-30 minutes"
        elif len(rollback.rollback_steps) > 3:
            rollback.estimated_rollback_time = "5-10 minutes"
        else:
            rollback.estimated_rollback_time = "1-5 minutes"

        return rollback

    def detect_conflicts(self, plan: ExecutionPlan) -> List[str]:
        """Detect conflicts in plan

        Args:
            plan: Execution plan

        Returns:
            List of conflict descriptions
        """
        conflicts = []

        # Check for file conflicts (same file modified multiple times)
        file_operations = {}
        for step in plan.steps:
            for file_path in step.affected_files:
                if file_path not in file_operations:
                    file_operations[file_path] = []
                file_operations[file_path].append((step.step_number, step.step_type))

        for file_path, operations in file_operations.items():
            if len(operations) > 1:
                # Multiple operations on same file
                op_types = [op[1].value for op in operations]
                if 'delete_file' in op_types and len(op_types) > 1:
                    conflicts.append(
                        f"Conflict: {file_path} is deleted but also modified in other steps"
                    )
                elif op_types.count('write_file') > 1:
                    conflicts.append(
                        f"Conflict: {file_path} is written multiple times (overwrites)"
                    )

        # Check for dependency conflicts
        for step in plan.steps:
            for dep in step.dependencies:
                # Check if dependency exists
                dep_exists = any(s.step_number == dep for s in plan.steps)
                if not dep_exists:
                    conflicts.append(
                        f"Conflict: Step {step.step_number} depends on non-existent step {dep}"
                    )

                # Check if dependency comes after this step
                if dep > step.step_number:
                    conflicts.append(
                        f"Conflict: Step {step.step_number} depends on later step {dep} (circular dependency)"
                    )

        return conflicts

    def _score_step_risks(self, plan: ExecutionPlan, assessment: RiskAssessment) -> float:
        """Score risk based on step risk levels"""
        score = 0.0
        risk_weights = {
            RiskLevel.SAFE: 0,
            RiskLevel.LOW: 5,
            RiskLevel.MEDIUM: 15,
            RiskLevel.HIGH: 30,
            RiskLevel.CRITICAL: 40
        }

        for step in plan.steps:
            step_score = risk_weights.get(step.risk_level, 0)
            score = max(score, step_score)  # Take highest risk

            if step.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                assessment.risk_factors.append(
                    f"Step {step.step_number}: {step.risk_level.value} risk - {step.description}"
                )

        return score

    def _score_file_impact(self, plan: ExecutionPlan, assessment: RiskAssessment) -> float:
        """Score risk based on file impact"""
        if not assessment.blast_radius:
            return 0.0

        file_count = len(assessment.blast_radius.affected_files)

        # Check for critical files
        critical_count = 0
        for file_path in assessment.blast_radius.affected_files:
            if any(re.search(pattern, file_path, re.IGNORECASE) for pattern in self.CRITICAL_PATTERNS):
                critical_count += 1
                assessment.warnings.append(f"Critical file affected: {file_path}")

        # Calculate score
        score = 0.0

        if critical_count > 0:
            score += 20.0
            assessment.risk_factors.append(f"{critical_count} critical file(s) affected")

        if file_count > 20:
            score += 10.0
            assessment.risk_factors.append(f"Large file impact: {file_count} files")
        elif file_count > 5:
            score += 5.0

        return min(score, 30.0)

    def _score_destructive_ops(self, plan: ExecutionPlan, assessment: RiskAssessment) -> float:
        """Score risk based on destructive operations"""
        if not assessment.blast_radius:
            return 0.0

        destructive_count = len(assessment.blast_radius.destructive_operations)

        if destructive_count == 0:
            return 0.0

        score = destructive_count * 10.0

        assessment.risk_factors.append(
            f"{destructive_count} destructive operation(s)"
        )

        for op in assessment.blast_radius.destructive_operations:
            assessment.warnings.append(f"Destructive: {op}")

        return min(score, 20.0)

    def _score_dependencies(self, plan: ExecutionPlan, assessment: RiskAssessment) -> float:
        """Score risk based on dependencies and conflicts"""
        conflicts = self.detect_conflicts(plan)
        assessment.conflicts = conflicts

        if not conflicts:
            return 0.0

        score = len(conflicts) * 5.0

        for conflict in conflicts:
            assessment.warnings.append(conflict)

        assessment.risk_factors.append(f"{len(conflicts)} conflict(s) detected")

        return min(score, 10.0)

    def _score_to_risk_level(self, score: float) -> RiskLevel:
        """Convert risk score to risk level"""
        if score >= 70:
            return RiskLevel.CRITICAL
        elif score >= 50:
            return RiskLevel.HIGH
        elif score >= 30:
            return RiskLevel.MEDIUM
        elif score >= 10:
            return RiskLevel.LOW
        else:
            return RiskLevel.SAFE

    def _generate_recommendations(self, plan: ExecutionPlan, assessment: RiskAssessment):
        """Generate safety recommendations"""
        if assessment.overall_risk_score >= 50:
            assessment.recommendations.append(
                "Create checkpoint before executing this plan"
            )
            assessment.recommendations.append(
                "Review all steps carefully before proceeding"
            )

        if assessment.blast_radius and not assessment.blast_radius.reversible:
            assessment.recommendations.append(
                "Plan contains irreversible operations - ensure you have backups"
            )

        if assessment.conflicts:
            assessment.recommendations.append(
                "Resolve conflicts before execution"
            )

        if assessment.blast_radius and len(assessment.blast_radius.affected_files) > 20:
            assessment.recommendations.append(
                "Consider breaking plan into smaller, incremental steps"
            )

        # Check for critical system operations
        if assessment.blast_radius and 'database' in assessment.blast_radius.affected_systems:
            assessment.recommendations.append(
                "Database operations detected - verify database backups exist"
            )

        if assessment.blast_radius and 'git' in assessment.blast_radius.affected_systems:
            assessment.recommendations.append(
                "Git operations detected - ensure working directory is clean"
            )
