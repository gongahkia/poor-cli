#!/usr/bin/env python3
"""Fail docs claims that cite benchmark numbers without reproducibility context."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CLAIM_RE = re.compile(r"(\d+(?:\.\d+)?%|\d+/\d+|p95|mean cost|pass rate|resolved)", re.I)
REQUIRED_RE = re.compile(r"(20\d\d-\d\d-\d\d|run_|bench/|task set|config)", re.I)
DISALLOWED_RE = re.compile(
    r"(\bbest\b|\bSOTA\b|state[- ]of[- ]the[- ]art|first local replay cli|first replay cli|superior to|better than)",
    re.I,
)
PHASE3_UNBACKED_RE = re.compile(r"((phase ?3|linux/cuda|local[- ]gpu).{0,48}\b(done|complete|ready|passed|supported)\b)", re.I)
POLICY_LINE_RE = re.compile(r"(do not claim|disallowed without evidence|not claim|before .*evidence|requires|blocked|missing)", re.I)
REPLAY_CLAIM_RE = re.compile(
    r"(records? replayable artifacts|replayable artifacts|replay(?:ed)? offline|verified offline|checked offline)", re.I
)
GRAPH_CLAIM_RE = re.compile(r"(graph-aware context|graph context|graph tools)", re.I)
LOCAL_PROVIDER_CLAIM_RE = re.compile(r"(supports local provider routes|local provider routes)", re.I)
TASK_SET_CLAIM_RE = re.compile(r"\bmeasured on task set\b", re.I)


def scan_claims(paths: list[Path], *, root: Path | None = None) -> dict[str, Any]:
    evidence_root = root or Path.cwd()
    violations = []
    for path in paths:
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            context = "\n".join(lines[max(0, lineno - 8) : min(len(lines), lineno + 2)])
            if CLAIM_RE.search(line) and not REQUIRED_RE.search(context) and "requires" not in line.lower():
                violations.append({"kind": "missing_reproducibility_context", "path": str(path), "line": lineno, "text": line.strip()})
            if POLICY_LINE_RE.search(line):
                continue
            violations.extend(_allowed_claim_violations(evidence_root, path, lineno, line, context))
            if DISALLOWED_RE.search(line):
                violations.append({"kind": "disallowed_claim", "path": str(path), "line": lineno, "text": line.strip()})
            if PHASE3_UNBACKED_RE.search(line) and "bench/results/phase3" not in context:
                violations.append({"kind": "unbacked_phase3_claim", "path": str(path), "line": lineno, "text": line.strip()})
    return {"schema_version": "poor-cli-claims-gate-v1", "accepted": not violations, "violations": violations}


def _allowed_claim_violations(root: Path, path: Path, lineno: int, line: str, context: str) -> list[dict[str, Any]]:
    checks = (
        ("missing_replay_evidence", REPLAY_CLAIM_RE, _json_true(root / "bench/results/replay-verify-acceptance.json", "accepted")),
        ("missing_graph_evidence", GRAPH_CLAIM_RE, _json_true(root / "bench/results/graph-vs-grep-synthetic.json", "accepted")),
        ("missing_local_provider_evidence", LOCAL_PROVIDER_CLAIM_RE, _phase3_target_host_green(root)),
    )
    violations = [
        {"kind": kind, "path": str(path), "line": lineno, "text": line.strip()}
        for kind, regex, accepted in checks
        if regex.search(line) and not accepted
    ]
    if TASK_SET_CLAIM_RE.search(line) and "bench/" not in context:
        violations.append({"kind": "missing_task_set_evidence", "path": str(path), "line": lineno, "text": line.strip()})
    return violations


def _phase3_target_host_green(root: Path) -> bool:
    readiness = _read_json(root / "bench/results/phase3-readiness.json")
    closeout = _read_json(root / "bench/results/phase3-closeout.json")
    adapters = readiness.get("checks", {}).get("provider_adapters", {}) if isinstance(readiness.get("checks"), dict) else {}
    return bool(adapters.get("ready")) and bool(readiness.get("ready")) and bool(closeout.get("accepted"))


def _json_true(path: Path, key: str) -> bool:
    return bool(_read_json(path).get(key))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/claims_gate.py")
    parser.add_argument("paths", nargs="*", default=["README.md", "docs/benchmarks.md"])
    args = parser.parse_args()
    payload = scan_claims([Path(path) for path in args.paths])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
