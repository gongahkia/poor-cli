#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED = {
    "direct": {"agent.result", "handoff.packet"},
    "planner_reviewer": {"artifact.review", "artifact.verify"},
    "swarm": {"artifact.swarm.merge_plan"},
    "web_research": {"web.search", "web.fetch", "web.citation"},
    "cost_controls": {"budget.ledger"},
    "failure_cleanup": {"artifacts.cleanup"},
    "benchmark_report": {"benchmark.report"},
}


def audit(store_root: Path) -> dict[str, Any]:
    runs = sorted((store_root / "runs").glob("*")) if (store_root / "runs").exists() else []
    by_kind: dict[str, set[str]] = {key: set() for key in REQUIRED}
    for run in runs:
        kinds = _artifact_kinds(run)
        events = _event_types(run)
        for scenario, required in REQUIRED.items():
            if required <= kinds or required <= events:
                by_kind[scenario].add(run.name)
    checks = {
        scenario: {"done": bool(run_ids), "runs": sorted(run_ids), "required": sorted(REQUIRED[scenario])}
        for scenario, run_ids in by_kind.items()
    }
    return {
        "schema_version": "poor-cli-dogfood-report-v1",
        "accepted": all(row["done"] for row in checks.values()),
        "checks": checks,
    }


def _artifact_kinds(run: Path) -> set[str]:
    events = _events(run)
    return {str(event.get("payload", {}).get("kind") or "") for event in events if event.get("type") == "artifact.created"}


def _event_types(run: Path) -> set[str]:
    return {str(event.get("type") or "") for event in _events(run)}


def _events(run: Path) -> list[dict[str, Any]]:
    path = run / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
