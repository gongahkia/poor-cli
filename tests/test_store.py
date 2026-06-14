from __future__ import annotations

import json
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


def test_store_writes_run_meta_and_events_jsonl(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={"max": None})
    store.append_event(run_id, "run.created", {"ok": True})
    store.set_run_status(run_id, "completed", "done")

    run_dir = tmp_path / "store" / "runs" / run_id
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]

    assert meta["run_id"] == run_id
    assert meta["status"] == "completed"
    assert meta["final_summary"] == "done"
    assert events[0]["type"] == "run.created"
    assert events[0]["payload"] == {"ok": True}
    store.close()
