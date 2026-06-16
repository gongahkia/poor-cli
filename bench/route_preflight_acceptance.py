#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from poor_cli.replay import replay_verify
from poor_cli.route_policy import preflight_route
from poor_cli.store import RunStore


def acceptance_payload() -> dict[str, Any]:
    with TemporaryDirectory(prefix="poor-cli-route-preflight-") as temp:
        root = Path(temp)
        route = {"profile": "local", "model": "qwen", "provider_kind": "vllm", "fallbacks": []}
        preflight = preflight_route("codex", ["exec", "fix tests in src/parser.py"], "tty", root, {}, route=route)
        bin_dir = root / "bin"
        _fake_binary(bin_dir, "codex")
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([str(bin_dir), str(Path(sys.executable).parent), env.get("PATH", "")])
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        store_dir = root / "store"
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "poor_cli",
                "--store-dir",
                str(store_dir),
                "shims",
                "exec",
                "codex",
                "--",
                "exec",
                "fix tests in src/parser.py",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        risky = subprocess.run(
            [
                sys.executable,
                "-m",
                "poor_cli",
                "--store-dir",
                str(store_dir),
                "shims",
                "exec",
                "codex",
                "--",
                "exec",
                "migrate auth schema",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        explain = subprocess.run(
            [
                sys.executable,
                "-m",
                "poor_cli",
                "route",
                "explain",
                "--shim-agent",
                "codex",
                "--shim-arg",
                "exec",
                "--shim-arg",
                "fix tests",
                "--json",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        store = RunStore(store_dir)
        try:
            rows = store.list_runs()
            run_id = next((row["run_id"] for row in rows if row["user_goal"] == "fix tests in src/parser.py"), "")
            preflight_artifacts = store.list_artifacts(run_id, "route.preflight") if run_id else []
            interrupted = any(row["status"] == "awaiting_confirmation" and row["user_goal"] == "migrate auth schema" for row in rows)
            verified = bool(run_id) and replay_verify(store, run_id)["verified"] is True
        finally:
            store.close()
    explained = json.loads(explain.stdout) if explain.returncode == 0 else {}
    checks = {
        "preflight_labels": {"small-edit", "test-fix", "needs-graph"} <= set(preflight["labels"]),
        "preflight_selected_route": preflight["selected_route"] == "graph-enriched",
        "pass_through_command": preflight["pass_through_command"] == ["codex", "exec", "fix tests in src/parser.py"],
        "shim_records_preflight_artifact": run.returncode == 0 and bool(preflight_artifacts) and verified,
        "high_risk_interrupts": risky.returncode == 2 and interrupted,
        "route_explain_cli": explained.get("preflight", {}).get("command") == "codex",
    }
    return {"schema_version": "poor-cli-route-preflight-acceptance-v1", "accepted": all(checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/route_preflight_acceptance.py")
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = acceptance_payload()
    body = json.dumps(payload, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    return 0 if payload["accepted"] else 1


def _fake_binary(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(f"#!/bin/sh\ncat >/dev/null\nprintf 'fake-{name}:%s\\n' \"$*\"\n", encoding="utf-8")
    path.chmod(0o755)


if __name__ == "__main__":
    raise SystemExit(main())
