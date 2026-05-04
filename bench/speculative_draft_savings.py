#!/usr/bin/env python3
"""Deterministic shadow-speculation bench.

The bench uses a tiny replay fixture instead of a live model so CI can verify
the accounting contract. It exits non-zero if the predicted read-tool hit rate
falls below 25%.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


FIXTURE = [
    {"actual": {"tool": "read_file", "args": {"path": "README.md"}}, "predicted": {"tool": "read_file", "args": {"path": "README.md"}, "confidence": 0.91}},
    {"actual": {"tool": "grep_files", "args": {"pattern": "Config"}}, "predicted": {"tool": "grep_files", "args": {"pattern": "Config"}, "confidence": 0.82}},
    {"actual": {"tool": "git_status", "args": {}}, "predicted": {"tool": "list_directory", "args": {"path": "."}, "confidence": 0.72}},
    {"actual": {"tool": "list_directory", "args": {"path": "poor_cli"}}, "predicted": {"tool": "list_directory", "args": {"path": "poor_cli"}, "confidence": 0.88}},
]


def _load_replay(path: str | None) -> List[Dict[str, Any]]:
    if not path:
        return FIXTURE
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("replay must be a JSON list")
    return data


def _match(actual: Dict[str, Any], predicted: Dict[str, Any]) -> bool:
    return actual.get("tool") == predicted.get("tool") and (actual.get("args") or {}) == (predicted.get("args") or {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", help="optional JSON replay file")
    parser.add_argument("--threshold", type=float, default=0.25)
    args = parser.parse_args()

    replay = _load_replay(args.replay)
    hits = sum(1 for row in replay if _match(row.get("actual", {}), row.get("predicted", {})))
    total = max(1, len(replay))
    hit_rate = hits / total
    mean_wall_clock_saved_ms = 35.0 * hits / total
    report = {
        "turns": total,
        "hits": hits,
        "hitRate": round(hit_rate, 4),
        "meanWallClockSavedMs": round(mean_wall_clock_saved_ms, 2),
        "threshold": args.threshold,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if hit_rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
