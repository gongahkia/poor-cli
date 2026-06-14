from __future__ import annotations

from pathlib import Path

import pytest

from poor_cli.models import TaskSpec, make_id
from poor_cli.replay import ReplayError, replay_summary
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
