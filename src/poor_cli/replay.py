from __future__ import annotations

from .store import RunStore


class ReplayError(RuntimeError):
    pass


def replay_summary(store: RunStore, run_id: str, from_event: str | None = None) -> dict[str, object]:
    run = store.get_run(run_id)
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
