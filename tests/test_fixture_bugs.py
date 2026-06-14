from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from poor_cli.cli import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_three_fixture_bugs_solve_end_to_end(tmp_path: Path, monkeypatch) -> None:
    fixes = {
        "bug-1": _replace_code("calculator.py", "return left - right", "return left + right"),
        "bug-2": _replace_code("slugify.py", "return value.lower()", "return '-'.join(value.lower().split())"),
        "bug-3": _replace_code("counter.py", 'return value.count("\\n")', "return len(value.splitlines())"),
    }
    for name, fix_code in fixes.items():
        workdir = tmp_path / name
        shutil.copytree(FIXTURES / name, workdir)
        planner = _planner(workdir, f"{sys.executable} -c {shlex.quote(fix_code)}")
        monkeypatch.chdir(workdir)
        monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

        assert main(["--store-dir", str(workdir / ".poor-cli" / "v6"), "run", f"fix {name}", "--yes"]) == 0
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=workdir, text=True, capture_output=True, check=False)

        assert result.returncode == 0, result.stdout + result.stderr


def _planner(root: Path, command: str) -> Path:
    planner = root / "planner.py"
    payload = {
        "problem_summary": "fixture bug",
        "architecture_assessment": "small fixture",
        "assumptions": [],
        "risks": [],
        "tasks": [{"title": "Fix fixture", "objective": "make fixture tests pass", "suggested_agent": "generic", "command": command}],
        "validation_strategy": ["python -m pytest -q"],
        "routing_strategy": "generic",
        "estimated_cost": {"tokens": None, "usd": None},
    }
    planner.write_text(
        f"import json, sys\nsys.stdin.read()\nprint({json.dumps(payload)!r})\n",
        encoding="utf-8",
    )
    return planner


def _replace_code(path: str, old: str, new: str) -> str:
    return f"from pathlib import Path; p=Path({path!r}); p.write_text(p.read_text().replace({old!r}, {new!r}))"
