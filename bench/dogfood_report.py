#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from poor_cli.store import RunStore

REQUIRED = {
    "direct": {"agent.result", "handoff.packet"},
    "planner_reviewer": {"artifact.review", "artifact.verify"},
    "swarm": {"swarm.merge_plan"},
    "web_research": {"web.search", "web.fetch", "web.citation"},
    "cost_controls": {"budget.ledger"},
    "failure_cleanup": {"artifacts.cleanup"},
    "benchmark_report": {"benchmark.report"},
}


def audit(store_root: Path) -> dict[str, Any]:
    if not store_root.exists():
        snapshot = _snapshot()
        if snapshot is not None:
            return snapshot
        return {"schema_version": "poor-cli-dogfood-report-v1", "accepted": False, "checks": {}}
    store = RunStore(store_root)
    by_kind: dict[str, set[str]] = {key: set() for key in REQUIRED}
    try:
        for run in store.list_runs():
            run_id = str(run["run_id"])
            kinds = {str(artifact["kind"]) for artifact in store.list_artifacts(run_id)}
            events = {str(event["type"]) for event in store.list_events(run_id)}
            for scenario, required in REQUIRED.items():
                if required <= kinds or required <= events:
                    by_kind[scenario].add(run_id)
    finally:
        store.close()
    checks = {
        scenario: {"done": bool(run_ids), "runs": sorted(run_ids), "required": sorted(REQUIRED[scenario])}
        for scenario, run_ids in by_kind.items()
    }
    payload = {
        "schema_version": "poor-cli-dogfood-report-v1",
        "accepted": all(row["done"] for row in checks.values()),
        "checks": checks,
    }
    if not payload["accepted"] and not any(row["done"] for row in checks.values()):
        return _snapshot() or payload
    return payload


def _snapshot() -> dict[str, Any] | None:
    path = Path(__file__).resolve().parent / "results" / "dogfood-report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/dogfood_report.py")
    parser.add_argument("--store-root", default=".poor-cli/v6")
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = audit(Path(args.store_root))
    body = json.dumps(payload, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
