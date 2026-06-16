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


def scan_claims(paths: list[Path]) -> dict[str, Any]:
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
            if DISALLOWED_RE.search(line):
                violations.append({"kind": "disallowed_claim", "path": str(path), "line": lineno, "text": line.strip()})
            if PHASE3_UNBACKED_RE.search(line) and "bench/results/phase3" not in context:
                violations.append({"kind": "unbacked_phase3_claim", "path": str(path), "line": lineno, "text": line.strip()})
    return {"schema_version": "poor-cli-claims-gate-v1", "accepted": not violations, "violations": violations}


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/claims_gate.py")
    parser.add_argument("paths", nargs="*", default=["README.md", "docs/benchmarks.md"])
    args = parser.parse_args()
    payload = scan_claims([Path(path) for path in args.paths])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
