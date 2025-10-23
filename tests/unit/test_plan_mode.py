"""
Unit tests for plan mode data structures
"""

import pytest
from datetime import datetime
from poor_cli.plan_mode import (
    PlanStep, PlanStepType, RiskLevel, ExecutionPlan
)


class TestPlanStep:
    """Test PlanStep dataclass"""

    def test_plan_step_creation(self):
        """Test creating a plan step"""
        step = PlanStep(
            step_number=1,
            step_type=PlanStepType.WRITE_FILE,
            description="Write config file",
            tool_name="write_file",
            tool_args={"file_path": "config.yaml", "content": "key: value"},
            risk_level=RiskLevel.MEDIUM,
            affected_files=["config.yaml"]
        )

        assert step.step_number == 1
        assert step.step_type == PlanStepType.WRITE_FILE
        assert step.risk_level == RiskLevel.MEDIUM
        assert len(step.affected_files) == 1

    def test_plan_step_to_dict(self):
        """Test converting plan step to dictionary"""
        step = PlanStep(
            step_number=1,
            step_type=PlanStepType.READ_FILE,
            description="Read file",
            tool_name="read_file",
            tool_args={"file_path": "test.txt"},
            risk_level=RiskLevel.SAFE
        )

        step_dict = step.to_dict()

        assert step_dict["step_number"] == 1
        assert step_dict["step_type"] == "read_file"
        assert step_dict["risk_level"] == "safe"
        assert step_dict["tool_name"] == "read_file"


class TestExecutionPlan:
    """Test ExecutionPlan dataclass"""

    def test_empty_plan_creation(self):
        """Test creating an empty plan"""
        plan = ExecutionPlan(
            plan_id="test_001",
            user_request="Do something",
            summary="Test plan"
        )

        assert plan.plan_id == "test_001"
        assert len(plan.steps) == 0
        assert plan.overall_risk_level == RiskLevel.SAFE

    def test_add_step_updates_risk(self):
        """Test adding steps updates overall risk level"""
        plan = ExecutionPlan(
            plan_id="test_002",
            user_request="Test",
            summary="Test"
        )

        # Add safe step
        safe_step = PlanStep(
            step_number=1,
            step_type=PlanStepType.READ_FILE,
            description="Read",
            tool_name="read_file",
            tool_args={},
            risk_level=RiskLevel.SAFE
        )
        plan.add_step(safe_step)
        assert plan.overall_risk_level == RiskLevel.SAFE

        # Add high risk step
        high_risk_step = PlanStep(
            step_number=2,
            step_type=PlanStepType.DELETE_FILE,
            description="Delete",
            tool_name="delete_file",
            tool_args={},
            risk_level=RiskLevel.HIGH
        )
        plan.add_step(high_risk_step)
        assert plan.overall_risk_level == RiskLevel.HIGH

        # Add critical risk step
        critical_step = PlanStep(
            step_number=3,
            step_type=PlanStepType.BASH_COMMAND,
            description="Sudo command",
            tool_name="bash",
            tool_args={},
            risk_level=RiskLevel.CRITICAL
        )
        plan.add_step(critical_step)
        assert plan.overall_risk_level == RiskLevel.CRITICAL

    def test_get_affected_files(self):
        """Test getting all affected files"""
        plan = ExecutionPlan(
            plan_id="test_003",
            user_request="Test",
            summary="Test"
        )

        step1 = PlanStep(
            step_number=1,
            step_type=PlanStepType.WRITE_FILE,
            description="Write file1",
            tool_name="write_file",
            tool_args={},
            risk_level=RiskLevel.MEDIUM,
            affected_files=["file1.txt"]
        )
        step2 = PlanStep(
            step_number=2,
            step_type=PlanStepType.EDIT_FILE,
            description="Edit file2",
            tool_name="edit_file",
            tool_args={},
            risk_level=RiskLevel.MEDIUM,
            affected_files=["file2.txt", "file1.txt"]  # Duplicate
        )

        plan.add_step(step1)
        plan.add_step(step2)

        affected = plan.get_affected_files()
        assert len(affected) == 2  # Deduplicated
        assert "file1.txt" in affected
        assert "file2.txt" in affected

    def test_get_high_risk_steps(self):
        """Test filtering high risk steps"""
        plan = ExecutionPlan(
            plan_id="test_004",
            user_request="Test",
            summary="Test"
        )

        safe_step = PlanStep(1, PlanStepType.READ_FILE, "Read", "read_file", {}, RiskLevel.SAFE)
        high_step = PlanStep(2, PlanStepType.DELETE_FILE, "Delete", "delete_file", {}, RiskLevel.HIGH)
        critical_step = PlanStep(3, PlanStepType.BASH_COMMAND, "Bash", "bash", {}, RiskLevel.CRITICAL)

        plan.add_step(safe_step)
        plan.add_step(high_step)
        plan.add_step(critical_step)

        high_risk = plan.get_high_risk_steps()
        assert len(high_risk) == 2
        assert all(s.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL] for s in high_risk)

    def test_plan_to_dict(self):
        """Test converting plan to dictionary"""
        plan = ExecutionPlan(
            plan_id="test_005",
            user_request="Test request",
            summary="Test summary"
        )

        step = PlanStep(
            1, PlanStepType.WRITE_FILE, "Write", "write_file",
            {"file_path": "test.txt"}, RiskLevel.MEDIUM,
            affected_files=["test.txt"]
        )
        plan.add_step(step)

        plan_dict = plan.to_dict()

        assert plan_dict["plan_id"] == "test_005"
        assert plan_dict["user_request"] == "Test request"
        assert len(plan_dict["steps"]) == 1
        assert plan_dict["overall_risk_level"] == "medium"
        assert len(plan_dict["affected_files"]) == 1


class TestRiskLevel:
    """Test RiskLevel enum"""

    def test_risk_level_values(self):
        """Test risk level enum values"""
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_risk_level_comparison(self):
        """Test comparing risk levels by value"""
        levels = [
            RiskLevel.SAFE,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL
        ]

        # Test that we can identify critical
        assert levels[-1] == RiskLevel.CRITICAL
        assert levels[0] == RiskLevel.SAFE
