from __future__ import annotations

import json
from typing import Any

from .store import RunStore


def diff_runs(store: RunStore, run_a: str, run_b: str) -> dict[str, Any]:
    left, right = _snapshot(store, run_a), _snapshot(store, run_b)
    changes = []
    for key in ("route", "context", "plan", "artifacts", "repo_delta"):
        if left[key] != right[key]:
            changes.append(
                {
                    "section": key,
                    "classification": "behavior-changing",
                    "before": left[key],
                    "after": right[key],
                }
            )
    return {
        "schema_version": "poor-cli-run-diff-v1",
        "run_a": run_a,
        "run_b": run_b,
        "changed": bool(changes),
        "changes": changes,
        "summary": {"behavior_changing": len(changes), "benign": 0},
    }


def fork_run(store: RunStore, source_run_id: str) -> dict[str, Any]:
    source = store.get_run(source_run_id)
    run_id = store.create_run(
        user_goal=f"fork of {source_run_id}: {source['user_goal']}",
        repo_path=_path(source["repo_path"]),
        git_commit_start=source.get("git_commit_start"),
        mode=str(source.get("mode") or "balanced"),
        budget=source.get("budget") if isinstance(source.get("budget"), dict) else {},
    )
    payload = {"schema_version": "poor-cli-run-fork-v1", "source_run_id": source_run_id, "fork_run_id": run_id}
    artifact = store.put_artifact(run_id=run_id, kind="run.fork", data=payload)
    store.append_event(run_id, "run.forked", {**payload, "artifact_id": artifact.artifact_id})
    store.set_run_status(run_id, "forked", f"forked from {source_run_id}")
    return payload


def handle_runs_command(args: Any, store: RunStore) -> int:
    if args.runs_command == "diff":
        payload = diff_runs(store, args.run_a, args.run_b)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"runs diff: {args.run_a} {args.run_b} changed={payload['changed']}")
            for change in payload["changes"]:
                print(f"- {change['section']}: {change['classification']}")
        return 1 if args.fail_on_change and payload["changed"] else 0
    if args.runs_command == "fork":
        payload = fork_run(store, args.run_id)
        text = json.dumps(payload, indent=2, sort_keys=True) if args.json else f"forked: {payload['source_run_id']} -> {payload['fork_run_id']}"
        print(text)
        return 0
    for run in store.list_runs(failed_only=args.failed, prompt_prefix=args.prefix):
        print(f"{run['run_id']}\t{run['status']}\t{run['created_at']}\t{run['user_goal'][:80]}")
    return 0


def _snapshot(store: RunStore, run_id: str) -> dict[str, Any]:
    store.get_run(run_id)
    events = store.list_events(run_id)
    artifacts = store.list_artifacts(run_id)
    return {
        "route": _events(events, {"route.selected", "route.policy.selected"}),
        "context": _artifacts(artifacts, {"context.packet", "graph.context", "handoff.packet"}),
        "plan": [
            {
                "title": task["title"],
                "type": task["task_type"],
                "risk": task["risk"],
                "deps": task["dependencies"],
                "status": task["status"],
            }
            for task in store.list_tasks(run_id)
        ],
        "artifacts": _artifacts(artifacts, None),
        "repo_delta": _artifacts(artifacts, {"artifact.worker.patch", "artifact.worker.changed_files"}),
    }


def _events(events: list[dict[str, Any]], kinds: set[str]) -> list[dict[str, Any]]:
    return [
        {"type": event["type"], "task_id": event.get("task_id"), "payload": event["payload"]} for event in events if event["type"] in kinds
    ]


def _artifacts(artifacts: list[dict[str, Any]], kinds: set[str] | None) -> list[dict[str, Any]]:
    return [
        {"kind": artifact["kind"], "task_id": artifact.get("task_id"), "sha256": artifact["sha256"], "size": artifact["size"]}
        for artifact in artifacts
        if kinds is None or artifact["kind"] in kinds
    ]


def _path(value: Any):
    from pathlib import Path

    return Path(str(value))
