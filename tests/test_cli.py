from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_plan_run_inspect_replay(tmp_path: Path) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["POOR_CLI_PLANNER_COMMAND"] = f"{sys.executable} {planner}"
    store = tmp_path / "store"

    run = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "run", "test goal", "--yes"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    run_id = next(line.split(":", 1)[1].strip() for line in run.stdout.splitlines() if line.startswith("run_id:"))

    inspect = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "inspect", run_id, "--events", "--context", "--json"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(inspect.stdout)
    assert payload["run"]["status"] == "completed"
    assert payload["tasks"][0]["status"] == "completed"
    assert any(event["type"] == "agent.completed" for event in payload["events"])

    replay = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "replay", run_id, "--json"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    state = json.loads(replay.stdout)
    assert state["tasks"][payload["tasks"][0]["task_id"]]["status"] == "completed"


def test_cli_exposes_tui_help(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(tmp_path / "store"), "tui", "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--run-id" in result.stdout
