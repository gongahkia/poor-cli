from __future__ import annotations

from pathlib import Path

import pytest

from poor_cli.models import TaskSpec, make_id
from poor_cli.replay import ReplayError, replay_summary, replay_verify
from poor_cli.store import RunStore


def test_replay_summary_reconstructs_state_from_events(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    task_id = make_id("task")
    store.insert_tasks(
        run_id,
        [
            TaskSpec(
                task_id=task_id,
                title="Task",
                objective="obj",
            )
        ],
    )
    store.append_event(run_id, "plan.created", {"task_count": 1})
    assigned = store.append_event(run_id, "task.assigned", {"agent": "generic"}, task_id)
    store.append_event(run_id, "task.completed", {"result_artifact_id": "art_1"}, task_id)
    store.append_event(run_id, "run.completed", {"summary": "done"})

    full = replay_summary(store, run_id)
    partial = replay_summary(store, run_id, assigned.event_id)

    assert full["status"] == "completed"
    assert full["tasks"][task_id]["status"] == "completed"
    assert full["tasks"][task_id]["agent"] == "generic"
    assert partial["event_count"] == 3
    assert partial["tasks"][task_id]["status"] == "completed"
    store.close()


def test_replay_summary_rejects_unknown_start_event(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})

    with pytest.raises(ReplayError):
        replay_summary(store, run_id, "evt_missing")

    store.close()


def test_replay_verify_checks_event_mirror_and_cas(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    store.append_event(run_id, "run.created", {"ok": True})
    store.put_artifact(run_id=run_id, kind="note", data={"value": 1})

    first = replay_verify(store, run_id)
    second = replay_verify(store, run_id)

    assert first == second
    assert first["verified"] is True
    assert first["event_count"] == 1
    assert first["artifact_count"] == 1
    store.close()


def test_replay_verify_rejects_event_mirror_mismatch(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    store.append_event(run_id, "run.created", {"ok": True})
    mirror = tmp_path / "store" / "runs" / run_id / "events.jsonl"
    mirror.write_text('{"event_id":"evt_wrong"}\n', encoding="utf-8")

    with pytest.raises(ReplayError):
        replay_verify(store, run_id)

    store.close()
