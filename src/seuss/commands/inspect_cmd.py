from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jsonl_store import read_jsonl
from seuss.utils import shorten


def _top_phrases(fragments: list[dict], limit: int) -> list[tuple[str, int]]:
    phrase_rows = [row for row in fragments if row.get("segment_type") == "phrase"]
    counts = Counter(row.get("normalized_text", "") for row in phrase_rows)
    return [(phrase, n) for phrase, n in counts.most_common(limit) if phrase]


def _summary(fragments: list[dict], memories: list[dict], queue: list[dict]) -> int:
    print(f"Corpus fragments: {len(fragments)}")
    print(f"Memory records: {len(memories)}")
    print(f"Training queue records: {len(queue)}")

    by_source = Counter(row.get("source", "unknown") for row in fragments)
    by_provenance = Counter(row.get("provenance", "unknown") for row in fragments)
    by_split = Counter(row.get("split", "unknown") for row in fragments)

    print("Fragments by source:")
    for key, value in sorted(by_source.items()):
        print(f"  {key}: {value}")

    print("Fragments by provenance:")
    for key, value in sorted(by_provenance.items()):
        print(f"  {key}: {value}")

    print("Fragments by split:")
    for key, value in sorted(by_split.items()):
        print(f"  {key}: {value}")

    return 0


def _inspect_queue(queue: list[dict], limit: int) -> int:
    pending = [row for row in queue if row.get("approval_status") == "pending"]
    approved = [row for row in queue if row.get("approval_status") == "approved"]
    rejected = [row for row in queue if row.get("approval_status") == "rejected"]
    print(f"Queue records: {len(queue)}")
    print(f"  pending: {len(pending)}")
    print(f"  approved: {len(approved)}")
    print(f"  rejected: {len(rejected)}")
    for row in queue[-limit:]:
        status = row.get("approval_status", "unknown")
        print(f"{row.get('id')}  {status}  {row.get('source')}  {shorten(row.get('text', ''))}")
    return 0


def _inspect_runs(runs_dir: Path, limit: int) -> int:
    if not runs_dir.exists():
        print("Runs directory does not exist.")
        return 0
    files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"Run files: {len(files)}")
    for file_path in files[:limit]:
        row = json.loads(file_path.read_text(encoding="utf-8"))
        metrics = row.get("metrics", {})
        print(
            f"{row.get('id')}  level={row.get('level')}  "
            f"copy_hits={metrics.get('exact_copy_ngram_hits', 'n/a')}  "
            f"repetition={metrics.get('repetition_score', 'n/a')}"
        )
    return 0


def run_inspect(config_path: Path, mode: str | None, source: str | None, limit: int) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    fragments = read_jsonl(workspace / "corpus" / "fragments.jsonl")
    memories = read_jsonl(workspace / "memory" / "memories.jsonl")
    queue = read_jsonl(workspace / "training_queue.jsonl")

    if mode is None:
        return _summary(fragments, memories, queue)

    if mode == "corpus":
        print(f"Corpus fragments: {len(fragments)}")
        by_type = Counter(row.get("segment_type", "unknown") for row in fragments)
        for key, value in sorted(by_type.items()):
            print(f"  {key}: {value}")
        return 0

    if mode == "source":
        if not source:
            raise ValueError("inspect source requires --source <name>")
        rows = [row for row in fragments if row.get("source") == source]
        print(f"Source '{source}' fragments: {len(rows)}")
        by_type = Counter(row.get("segment_type", "unknown") for row in rows)
        for key, value in sorted(by_type.items()):
            print(f"  {key}: {value}")
        return 0

    if mode == "phrases":
        top = _top_phrases(fragments, limit=limit)
        for phrase, count in top:
            print(f"{count:>5}  {phrase}")
        return 0

    if mode == "queue":
        return _inspect_queue(queue, limit=limit)

    if mode == "runs":
        return _inspect_runs(workspace / "runs", limit=limit)

    raise ValueError(f"Unknown inspect mode: {mode}")
