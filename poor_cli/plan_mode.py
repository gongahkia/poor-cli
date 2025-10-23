"""
Plan and Preview Mode for poor-cli

Allows users to preview AI actions before execution for enhanced safety.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
from poor_cli.exceptions import ValidationError, setup_logger

logger = setup_logger(__name__)


class PlanStepType(Enum):
    """Types of plan steps"""
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    DELETE_FILE = "delete_file"
    CREATE_DIR = "create_directory"
    BASH_COMMAND = "bash"
    GIT_OPERATION = "git"
    SEARCH = "search"
    OTHER = "other"


class RiskLevel(Enum):
    """Risk levels for operations"""
    SAFE = "safe"        # Read-only operations
    LOW = "low"          # Minor modifications
    MEDIUM = "medium"    # File modifications
    HIGH = "high"        # Destructive operations
    CRITICAL = "critical"  # System-level operations


@dataclass
class PlanStep:
    """A single step in an execution plan"""
    step_number: int
    step_type: PlanStepType
    description: str
    tool_name: str
    tool_args: Dict[str, Any]
    risk_level: RiskLevel
    affected_files: List[str] = field(default_factory=list)
    estimated_duration: str = "instant"
    dependencies: List[int] = field(default_factory=list)  # Step numbers this depends on

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "step_number": self.step_number,
            "step_type": self.step_type.value,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "risk_level": self.risk_level.value,
            "affected_files": self.affected_files,
            "estimated_duration": self.estimated_duration,
            "dependencies": self.dependencies
        }


@dataclass
class ExecutionPlan:
    """Complete execution plan for a user request"""
    plan_id: str
    user_request: str
    summary: str
    steps: List[PlanStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    estimated_total_duration: str = "unknown"
    overall_risk_level: RiskLevel = RiskLevel.SAFE

    def add_step(self, step: PlanStep):
        """Add a step to the plan"""
        self.steps.append(step)
        # Update overall risk level
        if step.risk_level.value == "critical":
            self.overall_risk_level = RiskLevel.CRITICAL
        elif step.risk_level.value == "high" and self.overall_risk_level != RiskLevel.CRITICAL:
            self.overall_risk_level = RiskLevel.HIGH
        elif step.risk_level.value == "medium" and self.overall_risk_level not in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            self.overall_risk_level = RiskLevel.MEDIUM
        elif step.risk_level.value == "low" and self.overall_risk_level == RiskLevel.SAFE:
            self.overall_risk_level = RiskLevel.LOW

    def get_affected_files(self) -> List[str]:
        """Get all files affected by this plan"""
        files = []
        for step in self.steps:
            files.extend(step.affected_files)
        return list(set(files))

    def get_high_risk_steps(self) -> List[PlanStep]:
        """Get all high-risk steps"""
        return [s for s in self.steps if s.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "plan_id": self.plan_id,
            "user_request": self.user_request,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
            "estimated_total_duration": self.estimated_total_duration,
            "overall_risk_level": self.overall_risk_level.value,
            "affected_files": self.get_affected_files(),
            "high_risk_steps": len(self.get_high_risk_steps())
        }
