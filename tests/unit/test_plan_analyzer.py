"""
Unit tests for plan analyzer
"""

import pytest
from poor_cli.plan_analyzer import PlanAnalyzer
from poor_cli.plan_mode import PlanStepType, RiskLevel, ExecutionPlan


class TestPlanAnalyzer:
    """Test PlanAnalyzer class"""

    @pytest.fixture
    def analyzer(self):
        """Create plan analyzer instance"""
        return PlanAnalyzer()

    @pytest.fixture
    def sample_plan(self, analyzer):
        """Create sample plan for testing"""
        return analyzer.create_plan_from_request(
            "Test request",
            "This is a test plan"
        )

    def test_generate_plan_id(self, analyzer):
        """Test unique plan ID generation"""
        id1 = analyzer.generate_plan_id()
        id2 = analyzer.generate_plan_id()

        assert id1.startswith("plan_")
        assert id2.startswith("plan_")
        assert id1 != id2  # Should be unique

    def test_create_plan_from_request(self, analyzer):
        """Test creating a plan from user request"""
        plan = analyzer.create_plan_from_request(
            "Create a config file",
            "Will create config.yaml"
        )

        assert plan.user_request == "Create a config file"
        assert plan.summary == "Will create config.yaml"
        assert len(plan.steps) == 0

    def test_map_function_to_step_type(self, analyzer):
        """Test mapping function names to step types"""
        assert analyzer._map_function_to_step_type("read_file") == PlanStepType.READ_FILE
        assert analyzer._map_function_to_step_type("write_file") == PlanStepType.WRITE_FILE
        assert analyzer._map_function_to_step_type("edit_file") == PlanStepType.EDIT_FILE
        assert analyzer._map_function_to_step_type("delete_file") == PlanStepType.DELETE_FILE
        assert analyzer._map_function_to_step_type("bash") == PlanStepType.BASH_COMMAND
        assert analyzer._map_function_to_step_type("git_status") == PlanStepType.GIT_OPERATION
        assert analyzer._map_function_to_step_type("unknown_tool") == PlanStepType.OTHER

    def test_assess_risk_level_safe_commands(self, analyzer):
        """Test risk assessment for safe commands"""
        # Safe read operations
        assert analyzer._assess_risk_level("read_file", {}) == RiskLevel.SAFE
        assert analyzer._assess_risk_level("glob_files", {}) == RiskLevel.SAFE
        assert analyzer._assess_risk_level("grep_files", {}) == RiskLevel.SAFE

        # Safe bash commands
        assert analyzer._assess_risk_level(
            "bash", {"command": "ls -la"}
        ) == RiskLevel.SAFE
        assert analyzer._assess_risk_level(
            "bash", {"command": "pwd"}
        ) == RiskLevel.SAFE

    def test_assess_risk_level_destructive_operations(self, analyzer):
        """Test risk assessment for destructive operations"""
        # File operations
        assert analyzer._assess_risk_level("write_file", {}) == RiskLevel.MEDIUM
        assert analyzer._assess_risk_level("edit_file", {}) == RiskLevel.MEDIUM
        assert analyzer._assess_risk_level("delete_file", {}) == RiskLevel.HIGH

        # Dangerous bash commands
        assert analyzer._assess_risk_level(
            "bash", {"command": "rm -rf /"}
        ) == RiskLevel.CRITICAL
        assert analyzer._assess_risk_level(
            "bash", {"command": "sudo apt-get install"}
        ) == RiskLevel.CRITICAL

    def test_assess_risk_level_system_paths(self, analyzer):
        """Test risk assessment for system path operations"""
        # Writing to system paths should be critical
        assert analyzer._assess_risk_level(
            "write_file",
            {"file_path": "/etc/passwd"}
        ) == RiskLevel.CRITICAL

        assert analyzer._assess_risk_level(
            "edit_file",
            {"file_path": "/sys/kernel/config"}
        ) == RiskLevel.CRITICAL

    def test_extract_affected_files(self, analyzer):
        """Test extracting affected files from arguments"""
        # Single file
        files = analyzer._extract_affected_files(
            "write_file",
            {"file_path": "test.txt"}
        )
        assert files == ["test.txt"]

        # Copy operation (source and destination)
        files = analyzer._extract_affected_files(
            "copy_file",
            {"source": "a.txt", "destination": "b.txt"}
        )
        assert len(files) == 2
        assert "a.txt" in files
        assert "b.txt" in files

        # Diff operation
        files = analyzer._extract_affected_files(
            "diff_files",
            {"file1": "old.txt", "file2": "new.txt"}
        )
        assert len(files) == 2

    def test_generate_step_description(self, analyzer):
        """Test generating human-readable step descriptions"""
        desc = analyzer._generate_step_description(
            "read_file",
            {"file_path": "config.yaml"}
        )
        assert "config.yaml" in desc

        desc = analyzer._generate_step_description(
            "bash",
            {"command": "npm install"}
        )
        assert "npm install" in desc

        desc = analyzer._generate_step_description(
            "copy_file",
            {"source": "a.txt", "destination": "b.txt"}
        )
        assert "a.txt" in desc
        assert "b.txt" in desc

    def test_estimate_duration(self, analyzer):
        """Test duration estimation"""
        assert analyzer._estimate_duration("read_file") == "instant"
        assert analyzer._estimate_duration("write_file") == "instant"
        assert analyzer._estimate_duration("bash") == "varies"
        assert "s" in analyzer._estimate_duration("grep_files")  # Contains seconds

    def test_add_function_call_to_plan(self, analyzer, sample_plan):
        """Test adding function calls to plan"""
        step = analyzer.add_function_call_to_plan(
            sample_plan,
            "write_file",
            {"file_path": "test.txt", "content": "Hello"},
            description="Write test file"
        )

        assert step.step_number == 1
        assert step.tool_name == "write_file"
        assert step.description == "Write test file"
        assert len(sample_plan.steps) == 1

        # Add another step
        step2 = analyzer.add_function_call_to_plan(
            sample_plan,
            "read_file",
            {"file_path": "test.txt"}
        )

        assert step2.step_number == 2
        assert len(sample_plan.steps) == 2

    def test_validate_plan_no_warnings(self, analyzer, sample_plan):
        """Test plan validation with safe plan"""
        analyzer.add_function_call_to_plan(
            sample_plan,
            "read_file",
            {"file_path": "test.txt"}
        )

        warnings = analyzer.validate_plan(sample_plan)
        assert len(warnings) == 0

    def test_validate_plan_high_risk_warning(self, analyzer, sample_plan):
        """Test plan validation with high risk operations"""
        analyzer.add_function_call_to_plan(
            sample_plan,
            "delete_file",
            {"file_path": "important.txt"}
        )

        warnings = analyzer.validate_plan(sample_plan)
        assert len(warnings) > 0
        assert any("high-risk" in w.lower() for w in warnings)

    def test_validate_plan_many_files_warning(self, analyzer, sample_plan):
        """Test plan validation with many affected files"""
        # Add steps affecting many files
        for i in range(15):
            analyzer.add_function_call_to_plan(
                sample_plan,
                "write_file",
                {"file_path": f"file_{i}.txt", "content": "test"}
            )

        warnings = analyzer.validate_plan(sample_plan)
        assert len(warnings) > 0
        assert any("files" in w.lower() for w in warnings)

    def test_validate_plan_sudo_warning(self, analyzer, sample_plan):
        """Test plan validation warns about sudo"""
        analyzer.add_function_call_to_plan(
            sample_plan,
            "bash",
            {"command": "sudo rm -rf /tmp/test"}
        )

        warnings = analyzer.validate_plan(sample_plan)
        assert len(warnings) > 0
        assert any("sudo" in w.lower() for w in warnings)

    def test_plan_counter_increments(self, analyzer):
        """Test that plan counter increments"""
        initial_counter = analyzer.plan_counter

        analyzer.generate_plan_id()
        assert analyzer.plan_counter == initial_counter + 1

        analyzer.generate_plan_id()
        assert analyzer.plan_counter == initial_counter + 2
