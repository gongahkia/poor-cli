"""
Automatic lint + test feedback loop for poor-cli.

After file mutations, detects project type, runs appropriate linter/tests,
and feeds errors back to the AI for iterative fixing.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

MAX_FIX_ITERATIONS = 3
DEFAULT_TIMEOUT = 30


@dataclass
class FeedbackResult:
    """Result of a lint/test feedback pass."""
    tool: str # "lint" or "test"
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        output = self.stderr.strip() or self.stdout.strip()
        if len(output) > 2000:
            output = output[:2000] + "\n... [truncated]"
        return f"[{self.tool} {status}] `{self.command}`\n{output}"


@dataclass
class ProjectDetection:
    """Detected project type and associated commands."""
    project_type: str
    lint_command: Optional[str] = None
    test_command: Optional[str] = None
    root: str = ""


def detect_project(cwd: Optional[str] = None) -> ProjectDetection:
    """Detect project type from filesystem markers."""
    root = Path(cwd or os.getcwd()).resolve()
    detection = ProjectDetection(project_type="unknown", root=str(root))

    # python
    if (root / "pyproject.toml").exists():
        detection.project_type = "python"
        detection.lint_command = "ruff check --fix ." if _has_bin("ruff") else None
        detection.test_command = "python -m pytest -x -q --tb=short"
        return detection

    # node/js/ts
    if (root / "package.json").exists():
        detection.project_type = "node"
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if "lint" in scripts:
                detection.lint_command = "npm run lint"
            if "test" in scripts:
                detection.test_command = "npm test"
        except Exception:
            pass
        return detection

    # rust
    if (root / "Cargo.toml").exists():
        detection.project_type = "rust"
        detection.lint_command = "cargo clippy --quiet 2>&1"
        detection.test_command = "cargo test --quiet 2>&1"
        return detection

    # go
    if (root / "go.mod").exists():
        detection.project_type = "go"
        detection.lint_command = "go vet ./..."
        detection.test_command = "go test ./... -count=1 -short"
        return detection

    return detection


def _has_bin(name: str) -> bool:
    """Check if a binary is available on PATH."""
    import shutil
    return shutil.which(name) is not None


async def _run_command(cmd: str, cwd: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[int, str, str]:
    """Run a shell command and capture output."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        return (1, "", f"command timed out after {timeout}s: {cmd}")
    except Exception as exc:
        return (1, "", f"command failed: {exc}")


async def run_feedback_pass(
    cwd: Optional[str] = None,
    detection: Optional[ProjectDetection] = None,
    run_lint: bool = True,
    run_tests: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[FeedbackResult]:
    """Run lint and/or test commands, return structured results."""
    if detection is None:
        detection = detect_project(cwd)
    root = detection.root or str(Path(cwd or os.getcwd()).resolve())
    results: List[FeedbackResult] = []

    if run_lint and detection.lint_command:
        code, stdout, stderr = await _run_command(detection.lint_command, root, timeout)
        results.append(FeedbackResult(
            tool="lint",
            command=detection.lint_command,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            passed=code == 0,
        ))

    if run_tests and detection.test_command:
        code, stdout, stderr = await _run_command(detection.test_command, root, timeout)
        results.append(FeedbackResult(
            tool="test",
            command=detection.test_command,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            passed=code == 0,
        ))

    return results


def format_feedback_for_model(results: List[FeedbackResult]) -> str:
    """Format feedback results as a message to feed back to the AI."""
    if not results:
        return ""
    failures = [r for r in results if not r.passed]
    if not failures:
        return ""
    parts = ["## Auto-feedback: lint/test failures detected after your edit\n"]
    for r in failures:
        parts.append(r.summary())
    parts.append("\nPlease fix these issues.")
    return "\n\n".join(parts)


def toggle_feedback_loop(config: Any, enable: Optional[bool] = None) -> str:
    """Toggle or set auto-lint feedback loop. Returns status message."""
    agentic = getattr(config, "agentic", None) if config else None
    if agentic is None:
        return "feedback-loop: no agentic config available"
    current = getattr(agentic, "auto_lint", False)
    if enable is None:
        new_val = not current
    else:
        new_val = enable
    agentic.auto_lint = new_val
    return f"feedback-loop: {'enabled' if new_val else 'disabled'}"
