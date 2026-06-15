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


def scan_claims(paths: list[Path]) -> dict[str, Any]:
    violations = []
    for path in paths:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CLAIM_RE.search(line) and not REQUIRED_RE.search(line):
                violations.append({"path": str(path), "line": lineno, "text": line.strip()})
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
