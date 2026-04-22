from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jsonl_store import read_jsonl
from seuss.pathing import resolve_training_queue_path
from seuss.utils import shorten


def _top_phrases(fragments: list[dict], limit: int) -> list[tuple[str, int]]:
    phrase_rows = [row for row in fragments if row.get("segment_type") == "phrase"]
    counts = Counter(row.get("normalized_text", "") for row in phrase_rows)
    return [(phrase, n) for phrase, n in counts.most_common(limit) if phrase]


def _recent_runs(runs_dir: Path, limit: int) -> list[dict]:
    if not runs_dir.exists():
        return []
    files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows: list[dict] = []
    for file_path in files[:limit]:
        rows.append(json.loads(file_path.read_text(encoding="utf-8")))
    return rows


def _summary(
    fragments: list[dict],
    memories: list[dict],
    queue: list[dict],
    ingest_stats: dict | None,
    runs_dir: Path,
    limit: int,
) -> int:
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

    top = _top_phrases(fragments, limit=limit)
    print("Top phrases:")
    if not top:
        print("  (none)")
    else:
        for phrase, count in top:
            print(f"  {count:>5}  {shorten(phrase, 96)}")

    pending = [row for row in queue if row.get("approval_status") == "pending"]
    approved = [row for row in queue if row.get("approval_status") == "approved"]
    rejected = [row for row in queue if row.get("approval_status") == "rejected"]
    print("Queue summary:")
    print(f"  pending={len(pending)} approved={len(approved)} rejected={len(rejected)}")
    print("Recent queue items:")
    if not queue:
        print("  (none)")
    else:
        for row in queue[-limit:]:
            status = row.get("approval_status", "unknown")
            print(
                f"  {row.get('id')}  {status}  {row.get('source')}  "
                f"{shorten(row.get('text', ''), 96)}"
            )

    print("Recent runs:")
    recent_runs = _recent_runs(runs_dir, limit=limit)
    if not recent_runs:
        print("  (none)")
    else:
        for row in recent_runs:
            metrics = row.get("metrics", {})
            print(
                f"  {row.get('id')}  level={row.get('level')}  "
                f"copy_hits={metrics.get('exact_copy_ngram_hits', 'n/a')}  "
                f"repetition={metrics.get('repetition_score', 'n/a')}"
            )

    if ingest_stats:
        redactions = ingest_stats.get("redaction_totals", {})
        print("Redaction summary (last ingest):")
        print(f"  emails={redactions.get('emails', 0)}")
        print(f"  phone_numbers={redactions.get('phone_numbers', 0)}")
        print(f"  urls={redactions.get('urls', 0)}")
        print(f"  custom_patterns={redactions.get('custom_patterns', 0)}")

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
    for row in _recent_runs(runs_dir, limit=limit):
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
    queue_path = resolve_training_queue_path(config, config_path, workspace)
    queue = read_jsonl(queue_path)
    stats_path = workspace / "corpus" / "ingest_stats.json"
    ingest_stats = None
    if stats_path.exists():
        ingest_stats = json.loads(stats_path.read_text(encoding="utf-8"))

    if mode is None:
        return _summary(
            fragments=fragments,
            memories=memories,
            queue=queue,
            ingest_stats=ingest_stats,
            runs_dir=workspace / "runs",
            limit=limit,
        )

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
