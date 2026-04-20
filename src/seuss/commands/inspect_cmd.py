from __future__ import annotations

from collections import Counter
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.jsonl_store import read_jsonl


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

    raise ValueError(f"Unknown inspect mode: {mode}")
