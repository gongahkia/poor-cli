from __future__ import annotations

from .store import RunStore


def replay_summary(store: RunStore, run_id: str) -> dict[str, object]:
    run = store.get_run(run_id)
    events = store.list_events(run_id)
    tasks = store.list_tasks(run_id)
    state = {
        "run_id": run_id,
        "status": run["status"],
        "event_count": len(events),
        "tasks": {task["task_id"]: {"title": task["title"], "status": "pending", "agent": task.get("assigned_agent")} for task in tasks},
    }
    for event in events:
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
