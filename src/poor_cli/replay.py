from __future__ import annotations

import hashlib
import json

from .store import RunStore


class ReplayError(RuntimeError):
    pass


def replay_summary(store: RunStore, run_id: str, from_event: str | None = None) -> dict[str, object]:
    store.get_run(run_id)
    events = _event_window(store.list_events(run_id), from_event)
    tasks = store.list_tasks(run_id)
    state = {
        "run_id": run_id,
        "status": "created",
        "event_count": len(events),
        "from_event": from_event,
        "tasks": {task["task_id"]: {"title": task["title"], "status": "pending", "agent": task.get("assigned_agent")} for task in tasks},
    }
    for event in events:
        if event["type"] == "plan.created":
            state["status"] = "planned"
        elif event["type"] == "run.completed":
            state["status"] = "completed"
        elif event["type"] == "run.failed":
            state["status"] = "failed"
        elif event["type"] == "run.cancelled":
            state["status"] = "cancelled"
        task_id = event.get("task_id")
        if task_id and task_id in state["tasks"]:
            if event["type"] == "task.assigned":
                state["tasks"][task_id]["status"] = "assigned"
                state["tasks"][task_id]["agent"] = event["payload"].get("agent")
            elif event["type"] == "task.completed":
                state["tasks"][task_id]["status"] = "completed"
            elif event["type"] == "task.failed":
                state["tasks"][task_id]["status"] = "failed"
            elif event["type"] == "task.skipped":
                state["tasks"][task_id]["status"] = "skipped"
    return state


def _event_window(events: list[dict[str, object]], from_event: str | None) -> list[dict[str, object]]:
    if from_event is None:
        return events
    for index, event in enumerate(events):
        if event.get("event_id") == from_event:
            return events[index:]
    raise ReplayError(f"unknown replay event: {from_event}")


def replay_verify(store: RunStore, run_id: str) -> dict[str, object]:
    store.get_run(run_id)
    events = store.list_events(run_id)
    artifacts = store.list_artifacts(run_id)
    event_bytes = _verify_event_mirror(store, run_id, events)
    trace = hashlib.sha256()
    trace.update(b"events\x00")
    trace.update(event_bytes)
    artifact_bytes = 0
    for artifact in artifacts:
        payload = store.artifact_payload(str(artifact["artifact_id"]))
        artifact_bytes += len(payload)
        trace.update(f"artifact\x00{artifact['artifact_id']}\x00{artifact['sha256']}\x00".encode())
        trace.update(payload)
    return {
        "verified": True,
        "event_count": len(events),
        "artifact_count": len(artifacts),
        "artifact_bytes": artifact_bytes,
        "trace_sha256": trace.hexdigest(),
    }


def _verify_event_mirror(store: RunStore, run_id: str, events: list[dict[str, object]]) -> bytes:
    path = store.runs_root / run_id / "events.jsonl"
    if not path.exists():
        raise ReplayError(f"missing replay event mirror: {path}")
    raw = path.read_bytes()
    lines = raw.splitlines()
    if len(lines) != len(events):
        raise ReplayError(f"event mirror length mismatch: {len(lines)} != {len(events)}")
    for line, event in zip(lines, events, strict=True):
        try:
            mirrored = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayError(f"invalid event mirror JSON: {exc}") from exc
        if mirrored.get("event_id") != event.get("event_id"):
            raise ReplayError(f"event mirror mismatch: {mirrored.get('event_id')} != {event.get('event_id')}")
    return raw
