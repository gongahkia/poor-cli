from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures"

FIXTURES: dict[str, dict[str, str]] = {
    "bug-1": {
        "prompt": "Fix the calculator fixture so its pytest suite passes.",
        "command": "from pathlib import Path; p=Path('calculator.py'); p.write_text(p.read_text().replace('return left - right', 'return left + right'))",
    },
    "bug-2": {
        "prompt": "Fix the slugify fixture so its pytest suite passes.",
        "command": (
            "from pathlib import Path; p=Path('slugify.py'); "
            "p.write_text(p.read_text().replace('return value.lower()', \"return '-'.join(value.lower().split())\"))"
        ),
    },
    "bug-3": {
        "prompt": "Fix the counter fixture so its pytest suite passes.",
        "command": (
            "from pathlib import Path; p=Path('counter.py'); "
            "p.write_text(p.read_text().replace('return value.count(\"\\\\n\")', 'return len(value.splitlines())'))"
        ),
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local poor-cli fixture bug benchmark.")
    parser.add_argument("--agent", choices=["generic", "claude", "codex"], default="generic")
    parser.add_argument("--fixture", action="append", choices=sorted(FIXTURES), help="Fixture to run; repeatable.")
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON summary to this path.")
    parser.add_argument("--keep-workdirs", action="store_true")
    args = parser.parse_args(argv)

    payload = run_fixture_suite(
        agent=args.agent,
        fixtures=args.fixture or sorted(FIXTURES),
        work_root=args.work_root,
        keep_workdirs=args.keep_workdirs,
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    ok = all(item["completed"] and item["tests_passed"] and item["replay_verified"] for item in payload["results"])
    return 0 if ok else 1


def run_fixture_suite(
    *,
    agent: str = "generic",
    fixtures: list[str] | None = None,
    work_root: Path | None = None,
    keep_workdirs: bool = False,
) -> dict[str, Any]:
    selected = fixtures or sorted(FIXTURES)
    root = (work_root or Path(tempfile.mkdtemp(prefix="poor-cli-local-fixtures-"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results = [_run_fixture(name, agent, root) for name in selected]
    if not keep_workdirs and work_root is None:
        shutil.rmtree(root, ignore_errors=True)
    return {
        "schema_version": "poor-cli-local-fixture-bugs-v1",
        "mode": "poor-cli",
        "agent": agent,
        "fixture_count": len(results),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "work_root": str(root),
        "results": results,
    }


def _run_fixture(name: str, agent: str, work_root: Path) -> dict[str, Any]:
    source = FIXTURE_ROOT / name
    if not source.is_dir():
        raise RuntimeError(f"unknown fixture: {name}")
    workdir = work_root / name
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(source, workdir)
    store_dir = workdir / ".poor-cli" / "v6"
    planner = _write_planner(workdir, name, agent)
    env = _env_with_src()
    env["POOR_CLI_PLANNER_COMMAND"] = f"{sys.executable} {shlex.quote(str(planner))}"

    started = time.perf_counter()
    run_cmd = [sys.executable, "-m", "poor_cli", "--store-dir", str(store_dir), "run", FIXTURES[name]["prompt"], "--yes"]
    run = subprocess.run(run_cmd, cwd=workdir, env=env, text=True, capture_output=True, check=False)
    run_id = _extract_run_id(run.stdout)

    test_cmd = [sys.executable, "-m", "pytest", "-q"]
    tests = subprocess.run(test_cmd, cwd=workdir, env=env, text=True, capture_output=True, check=False)
    replay = _verify_replay(store_dir, run_id, workdir, env) if run_id else {"verified": False, "returncode": 1, "stdout": "", "stderr": "missing run_id"}

    return {
        "fixture": name,
        "agent": agent,
        "completed": run.returncode == 0,
        "tests_passed": tests.returncode == 0,
        "replay_verified": bool(replay["verified"]),
        "run_id": run_id,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "commands": {
            "run": run_cmd,
            "test": test_cmd,
            "replay": replay["command"],
        },
        "returncodes": {
            "run": run.returncode,
            "test": tests.returncode,
            "replay": replay["returncode"],
        },
        "stdout": {
            "run": _tail(run.stdout),
            "test": _tail(tests.stdout),
            "replay": _tail(str(replay["stdout"])),
        },
        "stderr": {
            "run": _tail(run.stderr),
            "test": _tail(tests.stderr),
            "replay": _tail(str(replay["stderr"])),
        },
    }


def _write_planner(workdir: Path, fixture: str, agent: str) -> Path:
    task: dict[str, Any] = {
        "title": f"Fix {fixture}",
        "objective": FIXTURES[fixture]["prompt"],
        "task_type": "implementation",
        "complexity": "small",
        "risk": "low",
        "required_context": "fixture files",
        "dependencies": [],
        "suggested_agent": agent,
        "validation": ["python -m pytest -q"],
    }
    if agent == "generic":
        task["command"] = f"{sys.executable} -c {shlex.quote(FIXTURES[fixture]['command'])}"
    payload = {
        "problem_summary": "local fixture bug",
        "architecture_assessment": "single-file Python fixture",
        "assumptions": [],
        "risks": [],
        "tasks": [task],
        "validation_strategy": ["python -m pytest -q"],
        "routing_strategy": agent,
        "estimated_cost": {"tokens": None, "usd": None},
        "requires_user_confirmation": True,
    }
    planner = workdir / "planner.py"
    planner.write_text(f"import json, sys\nsys.stdin.read()\nprint({json.dumps(payload)!r})\n", encoding="utf-8")
    return planner


def _verify_replay(store_dir: Path, run_id: str, workdir: Path, env: dict[str, str]) -> dict[str, Any]:
    replay_env = dict(env)
    replay_env.pop("POOR_CLI_PLANNER_COMMAND", None)
    replay_env["POOR_CLI_OFFLINE"] = "1"
    command = [sys.executable, "-m", "poor_cli", "--offline", "--store-dir", str(store_dir), "replay", run_id, "--verify", "--json"]
    result = subprocess.run(command, cwd=workdir, env=replay_env, text=True, capture_output=True, check=False)
    verified = False
    if result.returncode == 0:
        try:
            verified = bool(json.loads(result.stdout)["verification"]["verified"])
        except (KeyError, json.JSONDecodeError, TypeError):
            verified = False
    return {"verified": verified, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "command": command}


def _env_with_src() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not old else f"{src}{os.pathsep}{old}"
    return env


def _extract_run_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("run_id:"):
            return line.split(":", 1)[1].strip()
    return None


def _tail(value: str, limit: int = 4000) -> str:
    return value if len(value) <= limit else value[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
