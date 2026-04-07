"""Extended tests for feedback loop detection and formatting."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from poor_cli.feedback_loop import (
    detect_project,
    FeedbackResult,
    format_feedback_for_model,
    toggle_feedback_loop,
)


class TestProjectDetection(unittest.TestCase):
    def test_python_project(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "pyproject.toml").touch()
            det = detect_project(d)
            self.assertEqual(det.project_type, "python")
            self.assertIn("pytest", det.test_command or "")

    def test_node_project(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text('{"scripts": {"lint": "eslint .", "test": "jest"}}')
            det = detect_project(d)
            self.assertEqual(det.project_type, "node")
            self.assertEqual(det.lint_command, "npm run lint")
            self.assertEqual(det.test_command, "npm test")

    def test_node_no_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text("{}")
            det = detect_project(d)
            self.assertEqual(det.project_type, "node")
            self.assertIsNone(det.lint_command)

    def test_rust_project(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Cargo.toml").touch()
            det = detect_project(d)
            self.assertEqual(det.project_type, "rust")
            self.assertIn("clippy", det.lint_command or "")

    def test_go_project(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "go.mod").touch()
            det = detect_project(d)
            self.assertEqual(det.project_type, "go")
            self.assertIn("go vet", det.lint_command or "")

    def test_unknown_project(self):
        with tempfile.TemporaryDirectory() as d:
            det = detect_project(d)
            self.assertEqual(det.project_type, "unknown")
            self.assertIsNone(det.lint_command)
            self.assertIsNone(det.test_command)

    def test_priority_python_over_node(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "pyproject.toml").touch()
            (Path(d) / "package.json").write_text("{}")
            det = detect_project(d)
            self.assertEqual(det.project_type, "python") # python checked first


class TestFeedbackResult(unittest.TestCase):
    def test_summary_pass(self):
        r = FeedbackResult(tool="lint", command="ruff check .", exit_code=0, stdout="All good", stderr="", passed=True)
        s = r.summary()
        self.assertIn("PASS", s)
        self.assertIn("ruff check", s)

    def test_summary_fail(self):
        r = FeedbackResult(tool="test", command="pytest", exit_code=1, stdout="", stderr="FAILED test_foo.py", passed=False)
        s = r.summary()
        self.assertIn("FAIL", s)
        self.assertIn("FAILED test_foo.py", s)

    def test_summary_truncation(self):
        long_output = "x" * 5000
        r = FeedbackResult(tool="lint", command="cmd", exit_code=1, stdout="", stderr=long_output, passed=False)
        s = r.summary()
        self.assertIn("[truncated]", s)
        self.assertLess(len(s), 3000)

    def test_summary_prefers_stderr(self):
        r = FeedbackResult(tool="lint", command="cmd", exit_code=1, stdout="stdout", stderr="stderr", passed=False)
        s = r.summary()
        self.assertIn("stderr", s)


class TestFormatFeedback(unittest.TestCase):
    def test_all_passing_returns_empty(self):
        results = [
            FeedbackResult(tool="lint", command="cmd", exit_code=0, stdout="ok", stderr="", passed=True),
            FeedbackResult(tool="test", command="cmd", exit_code=0, stdout="ok", stderr="", passed=True),
        ]
        self.assertEqual(format_feedback_for_model(results), "")

    def test_empty_results(self):
        self.assertEqual(format_feedback_for_model([]), "")

    def test_failures_formatted(self):
        results = [
            FeedbackResult(tool="lint", command="ruff", exit_code=1, stdout="", stderr="E501 line too long", passed=False),
        ]
        text = format_feedback_for_model(results)
        self.assertIn("Auto-feedback", text)
        self.assertIn("E501", text)
        self.assertIn("fix these issues", text)

    def test_mixed_results_only_failures(self):
        results = [
            FeedbackResult(tool="lint", command="ruff", exit_code=0, stdout="ok", stderr="", passed=True),
            FeedbackResult(tool="test", command="pytest", exit_code=1, stdout="", stderr="1 failed", passed=False),
        ]
        text = format_feedback_for_model(results)
        self.assertIn("1 failed", text)
        self.assertNotIn("ok", text)


class TestToggleFeedbackLoop(unittest.TestCase):
    def test_toggle_on(self):
        cfg = MagicMock()
        cfg.agentic = MagicMock()
        cfg.agentic.auto_lint = False
        cfg._auto_feedback_enabled = False
        result = toggle_feedback_loop(cfg)
        self.assertIn("enabled", result)

    def test_toggle_off(self):
        cfg = MagicMock()
        cfg.agentic = MagicMock()
        cfg.agentic.auto_lint = True
        cfg._auto_feedback_enabled = True
        result = toggle_feedback_loop(cfg)
        self.assertIn("disabled", result)

    def test_explicit_set(self):
        cfg = MagicMock()
        cfg.agentic = MagicMock()
        cfg.agentic.auto_lint = True
        result = toggle_feedback_loop(cfg, enable=False)
        self.assertIn("disabled", result)
        self.assertFalse(cfg.agentic.auto_lint)

    def test_no_agentic_config(self):
        cfg = MagicMock(spec=[]) # no attributes at all
        result = toggle_feedback_loop(cfg)
        self.assertIn("no agentic config", result)

    def test_none_config(self):
        result = toggle_feedback_loop(None)
        self.assertIn("no agentic config", result)


if __name__ == "__main__":
    unittest.main()
