from __future__ import annotations

from pathlib import Path

from poor_cli.store import RunStore


def test_store_events_and_cas_round_trip(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={"max": None})
    event = store.append_event(run_id, "run.created", {"ok": True})
    artifact = store.put_artifact(run_id=run_id, kind="test", data={"value": 1})

    assert store.list_events(run_id)[0]["event_id"] == event.event_id
    assert store.artifact_payload(artifact.artifact_id) == b'{"value":1}'
    assert store.get_run(run_id)["status"] == "created"
    store.close()
