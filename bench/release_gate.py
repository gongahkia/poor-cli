#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

CUTS = {
    "v6.1": ["provider profiles", "route schema", "provider-backed runner", "doctor tests"],
    "v6.2": ["parallel DAG", "worktree swarm", "artifacts", "cleanup"],
    "v6.3": ["Fusion", "Kimi", "web tools", "review/verifier lanes", "benchmark reports"],
    "v6.4": ["RPC", "MCP hosting", "TUI panels", "prompt packs"],
}


def audit(root: Path) -> dict[str, Any]:
    checks = {
        "roadmap_no_unchecked_release_rows": _roadmap_release_done(root),
        "examples_doc": (root / "docs" / "examples.md").exists(),
        "prompt_packs_doc": (root / "docs" / "prompt-packs.md").exists(),
        "dogfood_gate": _command_ok(root, ["python", "bench/dogfood_report.py"]),
        "claims_gate": _command_ok(root, ["python", "bench/claims_gate.py", "README.md", "docs/benchmarks.md"]),
    }
    return {
        "schema_version": "poor-cli-release-gate-v1",
        "cuts": CUTS,
        "checks": checks,
        "accepted": all(checks.values()),
    }


def _roadmap_release_done(root: Path) -> bool:
    text = (root / "WORKON-PIVOT-ASAP.md").read_text(encoding="utf-8")
    return all(f"- [x] P22-00{index}" in text for index in range(1, 6))


def _command_ok(root: Path, command: list[str]) -> bool:
    result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/release_gate.py")
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = audit(Path.cwd())
    body = json.dumps(payload, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
