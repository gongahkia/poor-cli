from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from poor_cli.cli import main
from poor_cli.store import RunStore


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
    assert payload["context_artifacts"]
    assert payload["handoff_artifacts"]
    run_store = RunStore(store)
    try:
        assert run_store.list_artifacts(run_id, "agent.input")
        assert run_store.list_artifacts(run_id, "agent.result")
        assert run_store.list_artifacts(run_id, "handoff.packet")
    finally:
        run_store.close()

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


def test_cli_main_in_process_run_inspect_replay(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n"
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "run", "test goal", "--yes"]) == 0
    run_output = capsys.readouterr().out
    run_id = next(line.split(":", 1)[1].strip() for line in run_output.splitlines() if line.startswith("run_id:"))

    assert main(["--store-dir", str(store), "inspect", run_id, "--events", "--context"]) == 0
    inspect_output = capsys.readouterr().out
    assert "agent.completed" in inspect_output
    assert "handoff " in inspect_output

    assert main(["--store-dir", str(store), "replay", run_id]) == 0
    replay_output = capsys.readouterr().out
    assert "completed" in replay_output

    assert main(["--store-dir", str(store), "replay", run_id, "--verify", "--json"]) == 0
    first_verify = capsys.readouterr().out
    assert main(["--store-dir", str(store), "replay", run_id, "--verify", "--json"]) == 0
    second_verify = capsys.readouterr().out
    assert first_verify == second_verify
    assert json.loads(first_verify)["verification"]["verified"] is True


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


def test_cli_run_without_yes_records_confirmation_event(tmp_path: Path) -> None:
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

    result = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "run", "test goal"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    run_id = next(line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if line.startswith("run_id:"))
    run_store = RunStore(store)
    try:
        events = [event["type"] for event in run_store.list_events(run_id)]
        assert result.returncode == 1
        assert "run.confirmation_required" in events
        assert "agent.started" not in events
        assert run_store.get_run(run_id)["status"] == "awaiting_confirmation"
    finally:
        run_store.close()


def test_cli_plan_failure_records_structured_events(tmp_path: Path) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text("import sys\nsys.stderr.write('planner broke')\nsys.exit(2)\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["POOR_CLI_PLANNER_COMMAND"] = f"{sys.executable} {planner}"
    store = tmp_path / "store"

    result = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "plan", "test goal"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    run_store = RunStore(store)
    try:
        run = run_store.list_runs()[0]
        events = [event["type"] for event in run_store.list_events(run["run_id"])]
        assert result.returncode == 1
        assert run["status"] == "failed"
        assert "planner.failed" in events
        assert "run.failed" in events
        assert run_store.list_artifacts(run["run_id"], "planner.error")
    finally:
        run_store.close()
