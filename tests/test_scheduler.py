from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

from poor_cli.cli import main
from poor_cli.config import add_provider, empty_config, provider_preset, save_repo_config
from poor_cli.providers import CachedReplayProvider, ProviderRequest, ProviderResponse
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
        assert any(event["type"] == "scheduler.queue_snapshot" for event in events)
        ledger = json.loads(store.artifact_payload(store.list_artifacts(run_id, "scheduler.ledger")[-1]["artifact_id"]))
        assert ledger["queue"]["provider_or_route_cap_waits"] >= 1
    finally:
        store.close()


def test_provider_retry_backoff_for_rate_limit(tmp_path: Path, monkeypatch) -> None:
    config = empty_config()
    profile = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    profile["openai"]["limits"] = {"max_retries": 1, "backoff_initial_seconds": 0, "backoff_max_seconds": 0}
    config = add_provider(config, "openai", profile["openai"])
    save_repo_config(config, tmp_path)
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    calls = {"count": 0}

    class Flaky:
        def call(self, request: ProviderRequest) -> ProviderResponse:
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError("https://api.test", 429, "rate limited", {}, None)
            return ProviderResponse(provider=request.provider, model=request.model, content="ok")

    response = CachedReplayProvider(store, run_id, Flaky()).call(ProviderRequest(provider="openai", model="gpt-5.5", prompt="p"))

    assert response.content == "ok"
    assert calls["count"] == 2
    events = [event["type"] for event in store.list_events(run_id)]
    assert "provider.rate_limited" in events
    assert "provider.backoff" in events
    assert "provider.retry" in events
    store.close()


def test_provider_does_not_retry_auth_failure(tmp_path: Path) -> None:
    config = empty_config()
    profile = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    profile["openai"]["limits"] = {"max_retries": 2, "backoff_initial_seconds": 0}
    config = add_provider(config, "openai", profile["openai"])
    save_repo_config(config, tmp_path)
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    calls = {"count": 0}

    class AuthFail:
        def call(self, request: ProviderRequest) -> ProviderResponse:
            calls["count"] += 1
            raise urllib.error.HTTPError("https://api.test", 401, "unauthorized", {}, None)

    try:
        CachedReplayProvider(store, run_id, AuthFail()).call(ProviderRequest(provider="openai", model="gpt-5.5", prompt="p"))
    except urllib.error.HTTPError:
        pass

    assert calls["count"] == 1
    assert "provider.retry" not in [event["type"] for event in store.list_events(run_id)]
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
