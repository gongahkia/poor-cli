from __future__ import annotations

import hashlib
import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .store import RunStore

REPLAY_VERIFY_SCHEMA_VERSION = "poor-cli-replay-verify-v1"


class ReplayError(RuntimeError):
    pass


def replay_summary(store: RunStore, run_id: str, from_event: str | None = None) -> dict[str, Any]:
    store.get_run(run_id)
    events = _event_window(store.list_events(run_id), from_event)
    tasks = store.list_tasks(run_id)
    task_state: dict[str, dict[str, Any]] = {
        str(task["task_id"]): {"title": task["title"], "status": "pending", "agent": task.get("assigned_agent")} for task in tasks
    }
    state: dict[str, Any] = {
        "run_id": run_id,
        "status": "created",
        "event_count": len(events),
        "from_event": from_event,
        "tasks": task_state,
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
        if isinstance(task_id, str) and task_id in task_state:
            if event["type"] == "task.assigned":
                task_state[task_id]["status"] = "assigned"
                task_state[task_id]["agent"] = event["payload"].get("agent")
            elif event["type"] == "task.completed":
                task_state[task_id]["status"] = "completed"
            elif event["type"] == "task.failed":
                task_state[task_id]["status"] = "failed"
            elif event["type"] == "task.skipped":
                task_state[task_id]["status"] = "skipped"
    return state


def _event_window(events: list[dict[str, Any]], from_event: str | None) -> list[dict[str, Any]]:
    if from_event is None:
        return events
    for index, event in enumerate(events):
        if event.get("event_id") == from_event:
            return events[index:]
    raise ReplayError(f"unknown replay event: {from_event}")


def replay_verify(store: RunStore, run_id: str) -> dict[str, object]:
    run = store.get_run(run_id)
    with _no_network_guard() as network_attempts:
        events = store.list_events(run_id)
        artifacts = store.list_artifacts(run_id)
        event_bytes = _verify_event_mirror(store, run_id, events)
        trace = hashlib.sha256()
        trace.update(b"events\x00")
        trace.update(event_bytes)
        artifact_bytes = 0
        for artifact in artifacts:
            payload = store.artifact_payload(str(artifact["artifact_id"]))
            _verify_run_blob(store, run_id, str(artifact["sha256"]), payload)
            artifact_bytes += len(payload)
            trace.update(f"artifact\x00{artifact['artifact_id']}\x00{artifact['sha256']}\x00".encode())
            trace.update(payload)
    return {
        "schema_version": REPLAY_VERIFY_SCHEMA_VERSION,
        "verified": True,
        "record_schema_version": run.get("schema_version", "poor-cli-record-v0"),
        "event_count": len(events),
        "artifact_count": len(artifacts),
        "artifact_bytes": artifact_bytes,
        "trace_sha256": trace.hexdigest(),
        "network": {"asserted": True, "attempts": len(network_attempts)},
        "deterministic_scope": {
            "reconstructs": "run metadata, event order, task state, artifact hashes, per-run CAS mirror",
            "does_not_rerun": "planner, providers, shell agents, tools, validation commands",
        },
    }


@contextmanager
def _no_network_guard() -> Iterator[list[str]]:
    attempts: list[str] = []
    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def block_create_connection(address: object, *args: object, **kwargs: object) -> object:
        attempts.append(f"create_connection:{address!r}")
        raise ReplayError(f"network touched during replay verification: {address!r}")

    def block_connect(sock: socket.socket, address: object) -> None:
        attempts.append(f"connect:{address!r}")
        raise ReplayError(f"network touched during replay verification: {address!r}")

    def block_connect_ex(sock: socket.socket, address: object) -> int:
        attempts.append(f"connect_ex:{address!r}")
        raise ReplayError(f"network touched during replay verification: {address!r}")

    socket.create_connection = block_create_connection
    socket.socket.connect = block_connect
    socket.socket.connect_ex = block_connect_ex
    try:
        yield attempts
    finally:
        socket.create_connection = original_create_connection
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex


def _verify_event_mirror(store: RunStore, run_id: str, events: list[dict[str, Any]]) -> bytes:
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


def _verify_run_blob(store: RunStore, run_id: str, digest: str, payload: bytes) -> None:
    path = store.runs_root / run_id / "cas" / digest
    if not path.exists():
        raise ReplayError(f"missing replay CAS mirror: {path}")
    if path.read_bytes() != payload:
        raise ReplayError(f"replay CAS mirror mismatch: {digest}")
