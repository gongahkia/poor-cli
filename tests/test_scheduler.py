from __future__ import annotations

import json
import sys
from pathlib import Path

from poor_cli.cli import main
from poor_cli.config import add_provider, empty_config, provider_preset, save_repo_config
from poor_cli.store import RunStore


def _planner(path: Path, tasks: list[dict[str, object]]) -> None:
    path.write_text(
        "import json, sys\nsys.stdin.read()\n"
        f"tasks = {tasks!r}\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':tasks,'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{}}))\n",
        encoding="utf-8",
    )


def test_parallel_scheduler_runs_independent_tasks_concurrently(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    cmd = f'{sys.executable} -c "import time; time.sleep(0.4)"'
    _planner(
        planner,
        [
            {"title": "A", "objective": "a", "suggested_agent": "generic", "command": cmd},
            {"title": "B", "objective": "b", "suggested_agent": "generic", "command": cmd},
        ],
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run", "parallel", "--yes", "--parallel", "2"]) == 0

    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    store = RunStore(tmp_path / "store")
    try:
        events = store.list_events(run_id)
        first_done = next(index for index, event in enumerate(events) if event["type"] == "task.completed")
        starts_before_done = [event for event in events[:first_done] if event["type"] == "scheduler.task_started"]
        assert len(starts_before_done) == 2
        assert all(task["status"] == "completed" for task in store.list_tasks(run_id))
        assert store.list_artifacts(run_id, "scheduler.ledger")
    finally:
        store.close()


def test_scheduler_blocks_failed_dependencies(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    bad = f'{sys.executable} -c "raise SystemExit(2)"'
    good = f"{sys.executable} -c \"print('should not run')\""
    _planner(
        planner,
        [
            {"title": "A", "objective": "a", "suggested_agent": "generic", "command": bad},
            {"title": "B", "objective": "b", "suggested_agent": "generic", "dependencies": ["A"], "command": good},
        ],
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run", "deps", "--yes", "--parallel", "2"]) == 2
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    store = RunStore(tmp_path / "store")
    try:
        statuses = {task["title"]: task["status"] for task in store.list_tasks(run_id)}
        assert statuses == {"A": "failed", "B": "blocked"}
        assert any(event["type"] == "task.blocked" for event in store.list_events(run_id))
    finally:
        store.close()


def test_scheduler_honors_provider_concurrency_cap(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    cmd = f'{sys.executable} -c "import time; time.sleep(0.1)"'
    _planner(
        planner,
        [
            {"title": "A", "objective": "a", "suggested_agent": "generic", "command": cmd},
            {"title": "B", "objective": "b", "suggested_agent": "generic", "command": cmd},
        ],
    )
    profile = provider_preset("openai-compatible", profile_id="limited", model="m", base_url="http://limited.test")
    profile["limited"]["limits"] = {"max_concurrent_requests": 1}
    config = add_provider(empty_config(), "limited", profile["limited"])
    config["routes"] = {"executor": {"profile": "limited", "model": "m"}}
    save_repo_config(config, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run", "profile cap", "--yes", "--parallel", "2"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    store = RunStore(tmp_path / "store")
    try:
        events = store.list_events(run_id)
        second_start = [i for i, event in enumerate(events) if event["type"] == "scheduler.task_started"][1]
        first_done = next(i for i, event in enumerate(events) if event["type"] == "task.completed")
        assert first_done < second_start
    finally:
        store.close()


def test_plan_emit_tasks_outputs_dag_json(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    _planner(planner, [{"title": "A", "objective": "a", "suggested_agent": "generic"}])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "plan", "emit", "--emit-tasks"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["run_id"].startswith("run_")
    assert payload["tasks"][0]["title"] == "A"
