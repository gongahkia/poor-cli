#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from poor_cli.cli import main as poor_main
from poor_cli.replay import replay_verify
from poor_cli.store import RunStore

PROMPT = "inspect repo"


def dogfood_payload(*, confirm_live_agents: bool, shims_dir: Path | None = None, timeout_seconds: int = 180) -> dict[str, Any]:
    real = {name: shutil.which(name) for name in ("claude", "codex")}
    if not confirm_live_agents:
        return {
            "schema_version": "poor-cli-shim-live-dogfood-v1",
            "accepted": False,
            "blocked_by": "--confirm-live-agents",
            "real_binaries": real,
            "commands": ['claude "inspect repo"', 'codex exec "inspect repo"'],
        }
    if not all(real.values()):
        return {"schema_version": "poor-cli-shim-live-dogfood-v1", "accepted": False, "real_binaries": real, "runs": []}
    with TemporaryDirectory(prefix="poor-cli-live-shims-") as tmp:
        root = shims_dir or Path(tmp) / "shims"
        install = poor_main(["shims", "install", "--dir", str(root)])
        env = os.environ.copy()
        env["POOR_CLI_SHIMS_DIR"] = str(root)
        env["PATH"] = os.pathsep.join([str(root), env.get("PATH", "")])
        store_root = Path.cwd() / ".poor-cli" / "v6"
        before = _run_ids(store_root)
        commands = {
            "claude": ["claude", PROMPT],
            "codex": ["codex", "exec", PROMPT],
        }
        results = {agent: _run(command, env, timeout_seconds) for agent, command in commands.items()}
        runs = _captured_runs(store_root, before)
    checks = {
        "install_ok": install == 0,
        "claude_ok": results["claude"]["returncode"] == 0 and _agent_verified(runs, "claude"),
        "codex_ok": results["codex"]["returncode"] == 0 and _agent_verified(runs, "codex"),
    }
    return {
        "schema_version": "poor-cli-shim-live-dogfood-v1",
        "accepted": all(checks.values()),
        "checks": checks,
        "real_binaries": real,
        "results": results,
        "runs": runs,
        "store_dir": str(store_root),
    }


def _run(command: list[str], env: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    proc = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
    return {"command": command, "returncode": proc.returncode, "timed_out": timed_out, "stdout": stdout[-4000:], "stderr": stderr[-4000:]}


def _run_ids(store_root: Path) -> set[str]:
    if not (store_root / "runs.sqlite3").exists():
        return set()
    store = RunStore(store_root)
    try:
        return {str(run["run_id"]) for run in store.list_runs()}
    finally:
        store.close()


def _captured_runs(store_root: Path, before: set[str]) -> list[dict[str, Any]]:
    if not (store_root / "runs.sqlite3").exists():
        return []
    store = RunStore(store_root)
    rows = []
    try:
        for run in store.list_runs():
            run_id = str(run["run_id"])
            if run_id in before or run.get("user_goal") != PROMPT:
                continue
            preflight = _preflight(store, run_id)
            verification = replay_verify(store, run_id)
            rows.append(
                {
                    "run_id": run_id,
                    "agent": preflight.get("command", ""),
                    "status": run.get("status", ""),
                    "verified": bool(verification.get("verified")),
                    "trace_sha256": verification.get("trace_sha256", ""),
                }
            )
    finally:
        store.close()
    return rows


def _preflight(store: RunStore, run_id: str) -> dict[str, Any]:
    artifacts = store.list_artifacts(run_id, "route.preflight")
    if not artifacts:
        return {}
    return json.loads(store.artifact_payload(artifacts[-1]["artifact_id"]))


def _agent_verified(runs: list[dict[str, Any]], agent: str) -> bool:
    return any(run["agent"] == agent and run["verified"] for run in runs)


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/shim_live_dogfood.py")
    parser.add_argument("--confirm-live-agents", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = dogfood_payload(confirm_live_agents=args.confirm_live_agents, timeout_seconds=args.timeout_seconds)
    body = json.dumps(payload, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
