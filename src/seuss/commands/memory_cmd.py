from __future__ import annotations

import json
import uuid
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jsonl_store import append_jsonl, read_jsonl, write_jsonl
from seuss.utils import now_iso, shorten


def _queue_or_approve_training_examples(
    workspace: Path,
    config: dict,
    memories: list[dict],
) -> None:
    live_training_cfg = config.get("adaptation", {}).get("live_training_data", {})
    if not live_training_cfg.get("enabled", False):
        return

    require_approval = live_training_cfg.get("require_explicit_approval", True)

    queue_path = workspace / "training_queue.jsonl"
    approved_path = workspace / "approved_training.jsonl"

    if require_approval:
        queue_records = []
        for memory in memories:
            queue_records.append(
                {
                    "id": f"ex_{uuid.uuid4().hex[:12]}",
                    "text": memory["text"],
                    "source": memory.get("source", "live_chat"),
                    "provenance": "conversation_live",
                    "created_at": now_iso(),
                    "approval_status": "pending",
                    "quality_score": None,
                    "notes": [],
                }
            )
        append_jsonl(queue_path, queue_records)
        return

    approved_records = []
    for memory in memories:
        approved_records.append(
            {
                "id": f"ex_{uuid.uuid4().hex[:12]}",
                "text": memory["text"],
                "source": memory.get("source", "live_chat"),
                "provenance": "conversation_live",
                "created_at": now_iso(),
                "approval_status": "approved",
                "approved_at": now_iso(),
                "quality_score": None,
                "notes": ["auto_approved_by_config"],
            }
        )
    append_jsonl(approved_path, approved_records)


def run_memory_list(config_path: Path) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)
    memories = read_jsonl(workspace / "memory" / "memories.jsonl")
    print(f"Memory records: {len(memories)}")
    for row in memories[-50:]:
        print(f"{row.get('id')}  {row.get('kind')}  {shorten(row.get('text', ''))}")
    return 0


def run_memory_add(config_path: Path, text: str, kind: str) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    record = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "text": text.strip(),
        "source": "manual",
        "provenance": "memory_summary",
        "created_at": now_iso(),
        "confidence": 0.8,
        "approved_for_training": False,
    }

    append_jsonl(workspace / "memory" / "memories.jsonl", [record])
    _queue_or_approve_training_examples(workspace, config, [record])

    print(f"Memory added: {record['id']}")
    return 0


def run_memory_import(config_path: Path, import_path: Path, text_field: str) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    imported: list[dict] = []
    with import_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = str(row.get(text_field, "")).strip()
            if not text:
                continue
            imported.append(
                {
                    "id": f"mem_{uuid.uuid4().hex[:12]}",
                    "kind": "conversation",
                    "text": text,
                    "source": "live_chat",
                    "provenance": "conversation_live",
                    "created_at": now_iso(),
                    "confidence": 0.7,
                    "approved_for_training": False,
                }
            )

    append_jsonl(workspace / "memory" / "memories.jsonl", imported)
    _queue_or_approve_training_examples(workspace, config, imported)

    print(f"Imported memory records: {len(imported)}")
    return 0


def run_memory_delete(config_path: Path, memory_id: str) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    memory_path = workspace / "memory" / "memories.jsonl"
    memories = read_jsonl(memory_path)
    kept = [row for row in memories if row.get("id") != memory_id]

    if len(kept) == len(memories):
        print(f"Memory id not found: {memory_id}")
        return 1

    write_jsonl(memory_path, kept)
    print(f"Deleted memory: {memory_id}")
    return 0
