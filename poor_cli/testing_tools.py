"""
Testing and Quality Tools for poor-cli

Comprehensive testing and quality assurance:
- run_tests: Execute test suites (pytest, jest, cargo test, go test)
- lint_check: Run linters (ruff, pylint, eslint)
- type_check: Run type checkers (mypy, TypeScript)
- generate_test: Auto-generate test templates
- coverage_report: Code coverage analysis
"""

import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class TestFramework(Enum):
    """Supported test frameworks"""
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    MOCHA = "mocha"
    CARGO_TEST = "cargo"
    GO_TEST = "go"


class Linter(Enum):
    """Supported linters"""
    RUFF = "ruff"
    PYLINT = "pylint"
    FLAKE8 = "flake8"
    ESLINT = "eslint"
    PRETTIER = "prettier"


@dataclass
class TestResult:
    """Test execution result"""
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    failures: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0


@dataclass
class LintResult:
    """Lint check result"""
    errors: int = 0
    warnings: int = 0
    info: int = 0
    output: str = ""
    issues: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.errors == 0


@dataclass
class CoverageResult:
    """Code coverage result"""
    coverage_percent: float = 0.0
    lines_covered: int = 0
    lines_total: int = 0
    files_covered: Dict[str, float] = field(default_factory=dict)


class TestRunner:
    """Run tests with various frameworks"""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()

    def run_tests(
        self,
        framework: TestFramework,
        test_path: Optional[str] = None,
        verbose: bool = False
    ) -> TestResult:
        """Run tests

        Args:
            framework: Test framework to use
            test_path: Specific test file/directory (None = all)
            verbose: Verbose output

        Returns:
            Test results
        """
        if framework == TestFramework.PYTEST:
            return self._run_pytest(test_path, verbose)
        elif framework == TestFramework.JEST:
            return self._run_jest(test_path, verbose)
        elif framework == TestFramework.CARGO_TEST:
            return self._run_cargo_test(test_path, verbose)
        elif framework == TestFramework.GO_TEST:
            return self._run_go_test(test_path, verbose)
        else:
            logger.error(f"Unsupported framework: {framework}")
            return TestResult()

    def _run_pytest(self, test_path: Optional[str], verbose: bool) -> TestResult:
        """Run pytest"""
        cmd = ["pytest"]

        if verbose:
            cmd.append("-v")

        cmd.extend(["--json-report", "--json-report-file=/tmp/pytest_report.json"])

        if test_path:
            cmd.append(test_path)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            output = result.stdout + result.stderr

            # Parse JSON report if available
            report_file = Path("/tmp/pytest_report.json")
            if report_file.exists():
                with open(report_file) as f:
                    report = json.load(f)

                return TestResult(
                    passed=report['summary'].get('passed', 0),
                    failed=report['summary'].get('failed', 0),
                    skipped=report['summary'].get('skipped', 0),
                    total=report['summary'].get('total', 0),
                    duration_seconds=report['duration'],
                    output=output
                )

            # Fallback: parse output
            return self._parse_pytest_output(output)

        except subprocess.TimeoutExpired:
            logger.error("Test execution timed out")
            return TestResult(output="Test execution timed out")
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return TestResult(output=str(e))

    def _run_jest(self, test_path: Optional[str], verbose: bool) -> TestResult:
        """Run jest"""
        cmd = ["jest", "--json"]

        if verbose:
            cmd.append("--verbose")

        if test_path:
            cmd.append(test_path)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                return TestResult(
                    passed=data.get('numPassedTests', 0),
                    failed=data.get('numFailedTests', 0),
                    total=data.get('numTotalTests', 0),
                    output=result.stdout + result.stderr
                )
            except:
                return self._parse_jest_output(result.stdout + result.stderr)

        except Exception as e:
            logger.error(f"Jest execution failed: {e}")
            return TestResult(output=str(e))

    def _run_cargo_test(self, test_path: Optional[str], verbose: bool) -> TestResult:
        """Run cargo test"""
        cmd = ["cargo", "test"]

        if test_path:
            cmd.append(test_path)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            return self._parse_cargo_output(result.stdout + result.stderr)

        except Exception as e:
            logger.error(f"Cargo test failed: {e}")
            return TestResult(output=str(e))

    def _run_go_test(self, test_path: Optional[str], verbose: bool) -> TestResult:
        """Run go test"""
        cmd = ["go", "test"]

        if verbose:
            cmd.append("-v")

        if test_path:
            cmd.append(test_path)
        else:
            cmd.append("./...")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            return self._parse_go_output(result.stdout + result.stderr)

        except Exception as e:
            logger.error(f"Go test failed: {e}")
            return TestResult(output=str(e))

    def _parse_pytest_output(self, output: str) -> TestResult:
        """Parse pytest output text"""
        result = TestResult(output=output)

        # Look for summary line
        import re
        match = re.search(r'(\d+) passed', output)
        if match:
            result.passed = int(match.group(1))

        match = re.search(r'(\d+) failed', output)
        if match:
            result.failed = int(match.group(1))

        match = re.search(r'(\d+) skipped', output)
        if match:
            result.skipped = int(match.group(1))

        result.total = result.passed + result.failed + result.skipped

        return result

    def _parse_jest_output(self, output: str) -> TestResult:
        """Parse jest output text"""
        # Similar parsing logic for jest
        return TestResult(output=output)

    def _parse_cargo_output(self, output: str) -> TestResult:
        """Parse cargo test output"""
        import re
        result = TestResult(output=output)

        # Parse "test result: ok. X passed; Y failed"
        match = re.search(r'(\d+) passed.*?(\d+) failed', output)
        if match:
            result.passed = int(match.group(1))
            result.failed = int(match.group(2))
            result.total = result.passed + result.failed

        return result

    def _parse_go_output(self, output: str) -> TestResult:
        """Parse go test output"""
        # Count PASS and FAIL lines
        passed = output.count('PASS')
        failed = output.count('FAIL')

        return TestResult(
            passed=passed,
            failed=failed,
            total=passed + failed,
            output=output
        )


class QualityChecker:
    """Run linters and type checkers"""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()

    def run_linter(
        self,
        linter: Linter,
        file_paths: Optional[List[str]] = None
    ) -> LintResult:
        """Run linter

        Args:
            linter: Linter to use
            file_paths: Specific files (None = all)

        Returns:
            Lint results
        """
        if linter == Linter.RUFF:
            return self._run_ruff(file_paths)
        elif linter == Linter.ESLINT:
            return self._run_eslint(file_paths)
        else:
            logger.error(f"Unsupported linter: {linter}")
            return LintResult()

    def run_type_check(self, checker: str = "mypy") -> LintResult:
        """Run type checker

        Args:
            checker: Type checker to use (mypy, tsc)

        Returns:
            Type check results
        """
        if checker == "mypy":
            return self._run_mypy()
        elif checker == "tsc":
            return self._run_tsc()
        else:
            logger.error(f"Unsupported type checker: {checker}")
            return LintResult()

    def _run_ruff(self, file_paths: Optional[List[str]]) -> LintResult:
        """Run ruff linter"""
        cmd = ["ruff", "check", "--output-format=json"]

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True
            )

            # Parse JSON output
            try:
                issues = json.loads(result.stdout)
                lint_result = LintResult(output=result.stdout)

                for issue in issues:
                    if issue.get('severity') == 'error':
                        lint_result.errors += 1
                    else:
                        lint_result.warnings += 1

                    lint_result.issues.append(issue)

                return lint_result

            except:
                return LintResult(output=result.stdout + result.stderr)

        except Exception as e:
            logger.error(f"Ruff failed: {e}")
            return LintResult(output=str(e))

    def _run_eslint(self, file_paths: Optional[List[str]]) -> LintResult:
        """Run eslint"""
        cmd = ["eslint", "--format=json"]

        if file_paths:
            cmd.extend(file_paths)
        else:
            cmd.append(".")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True
            )

            # Parse JSON
            try:
                data = json.loads(result.stdout)
                lint_result = LintResult(output=result.stdout)

                for file_result in data:
                    for message in file_result.get('messages', []):
                        if message.get('severity') == 2:
                            lint_result.errors += 1
                        else:
                            lint_result.warnings += 1

                        lint_result.issues.append(message)

                return lint_result

            except:
                return LintResult(output=result.stdout + result.stderr)

        except Exception as e:
            logger.error(f"ESLint failed: {e}")
            return LintResult(output=str(e))

    def _run_mypy(self) -> LintResult:
        """Run mypy type checker"""
        cmd = ["mypy", "."]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True
            )

            # Count errors in output
            errors = result.stdout.count("error:")
            warnings = result.stdout.count("warning:")

            return LintResult(
                errors=errors,
                warnings=warnings,
                output=result.stdout + result.stderr
            )

        except Exception as e:
            logger.error(f"Mypy failed: {e}")
            return LintResult(output=str(e))

    def _run_tsc(self) -> LintResult:
        """Run TypeScript compiler"""
        cmd = ["tsc", "--noEmit"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True
            )

            errors = result.stdout.count("error TS")

            return LintResult(
                errors=errors,
                output=result.stdout + result.stderr
            )

        except Exception as e:
            logger.error(f"TypeScript check failed: {e}")
            return LintResult(output=str(e))


class CoverageAnalyzer:
    """Analyze code coverage"""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()

    def run_coverage(self, test_path: Optional[str] = None) -> CoverageResult:
        """Run coverage analysis with pytest-cov"""
        cmd = ["pytest", "--cov=.", "--cov-report=json"]

        if test_path:
            cmd.append(test_path)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            # Read coverage.json
            coverage_file = self.workspace_root / "coverage.json"
            if coverage_file.exists():
                with open(coverage_file) as f:
                    data = json.load(f)

                return CoverageResult(
                    coverage_percent=data['totals']['percent_covered'],
                    lines_covered=data['totals']['covered_lines'],
                    lines_total=data['totals']['num_statements'],
                    files_covered={
                        k: v['summary']['percent_covered']
                        for k, v in data.get('files', {}).items()
                    }
                )

        except Exception as e:
            logger.error(f"Coverage analysis failed: {e}")

        return CoverageResult()
