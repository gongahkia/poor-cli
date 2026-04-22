from __future__ import annotations

from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jsonl_store import append_jsonl, read_jsonl, write_jsonl
from seuss.pathing import resolve_approved_training_path, resolve_training_queue_path
from seuss.utils import now_iso, shorten


def _load_paths(config_path: Path) -> tuple[Path, Path]:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)
    return (
        resolve_training_queue_path(config, config_path, workspace),
        resolve_approved_training_path(workspace),
    )


def run_approve_list(config_path: Path, include_all: bool) -> int:
    queue_path, _ = _load_paths(config_path)
    queue = read_jsonl(queue_path)

    if not include_all:
        queue = [row for row in queue if row.get("approval_status") == "pending"]

    print(f"Queue records: {len(queue)}")
    for row in queue[-100:]:
        print(
            f"{row.get('id')}  {row.get('approval_status')}  {row.get('source')}  {shorten(row.get('text', ''))}"
        )
    return 0


def run_approve_accept(config_path: Path, record_id: str) -> int:
    queue_path, approved_path = _load_paths(config_path)
    queue = read_jsonl(queue_path)

    moved = []
    kept = []
    for row in queue:
        if row.get("id") == record_id and row.get("approval_status") == "pending":
            approved_row = dict(row)
            approved_row["approval_status"] = "approved"
            approved_row["approved_at"] = now_iso()
            moved.append(approved_row)
            continue
        kept.append(row)

    if not moved:
        print(f"Pending record not found: {record_id}")
        return 1

    append_jsonl(approved_path, moved)
    write_jsonl(queue_path, kept)
    print(f"Approved record: {record_id}")
    return 0


def run_approve_reject(config_path: Path, record_id: str) -> int:
    queue_path, _ = _load_paths(config_path)
    queue = read_jsonl(queue_path)

    found = False
    for row in queue:
        if row.get("id") == record_id and row.get("approval_status") == "pending":
            row["approval_status"] = "rejected"
            row["rejected_at"] = now_iso()
            found = True

    if not found:
        print(f"Pending record not found: {record_id}")
        return 1

    write_jsonl(queue_path, queue)
    print(f"Rejected record: {record_id}")
    return 0


def run_approve_accept_all(config_path: Path, source: str | None) -> int:
    queue_path, approved_path = _load_paths(config_path)
    queue = read_jsonl(queue_path)

    moved = []
    kept = []
    for row in queue:
        if row.get("approval_status") == "pending" and (not source or row.get("source") == source):
            approved_row = dict(row)
            approved_row["approval_status"] = "approved"
            approved_row["approved_at"] = now_iso()
            moved.append(approved_row)
            continue
        kept.append(row)

    append_jsonl(approved_path, moved)
    write_jsonl(queue_path, kept)
    print(f"Approved records: {len(moved)}")
    return 0
