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
        "strategy_doc": _strategy_doc_ready(root),
        "strategy_refs": _strategy_refs_ready(root),
        "examples_doc": (root / "docs" / "examples.md").exists(),
        "prompt_packs_doc": (root / "docs" / "prompt-packs.md").exists(),
        "dogfood_gate": _json_accepted(root / "bench" / "results" / "dogfood-report.json"),
        "claims_gate": _command_ok(
            root,
            ["python", "bench/claims_gate.py", "README.md", "docs/benchmarks.md", "docs/launch.md", "docs/index.md"],
        ),
    }
    return {
        "schema_version": "poor-cli-release-gate-v1",
        "cuts": CUTS,
        "checks": checks,
        "accepted": all(checks.values()),
    }


def _strategy_doc_ready(root: Path) -> bool:
    path = root / "TODO.md"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8").lower()
    required = (
        "verifiable run-record for coding agents",
        "router is the capture mechanism",
        "reproducible local-gpu benchmark",
        "competitive landscape",
        "batch b",
        "replay hardening",
    )
    return all(item in text for item in required) and not (root / "IDEA.md").exists()


def _strategy_refs_ready(root: Path) -> bool:
    paths = [root / "README.md", root / "docs" / "launch.md"]
    for path in paths:
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8")
        if "IDEA.md" in text:
            return False
    readme = (root / "README.md").read_text(encoding="utf-8")
    launch = (root / "docs" / "launch.md").read_text(encoding="utf-8")
    return "[`TODO.md`](TODO.md)" in readme and "README points at `TODO.md`" in launch


def _command_ok(root: Path, command: list[str]) -> bool:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=60, check=False)
    return result.returncode == 0


def _json_accepted(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(payload.get("accepted"))


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
