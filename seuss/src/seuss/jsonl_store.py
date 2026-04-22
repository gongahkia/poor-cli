from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from seuss.utils import ensure_parent_dir


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def append_jsonl(path: Path, records: Iterable[dict]) -> int:
    ensure_parent_dir(path)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            count += 1
    return count


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    ensure_parent_dir(path)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            count += 1
    return count


def touch_jsonl(path: Path) -> None:
    ensure_parent_dir(path)
    if not path.exists():
        path.write_text("", encoding="utf-8")
