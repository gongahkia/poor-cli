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

from poor_cli.cli import main as poor_main
from poor_cli.replay import replay_verify
from poor_cli.store import RunStore


def acceptance_payload() -> dict[str, Any]:
    with TemporaryDirectory(prefix="poor-cli-shims-") as temp:
        root = Path(temp)
        shims, bin_dir = root / "shims", root / "bin"
        _fake_binary(bin_dir, "claude")
        _fake_binary(bin_dir, "codex")
        install = poor_main(["shims", "install", "--dir", str(shims)])
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([str(shims), str(bin_dir), str(Path(sys.executable).parent), env.get("PATH", "")])
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        env["OPENAI_API_KEY"] = "sk-shimacceptance123456789"
        help_result = subprocess.run(
            [sys.executable, "-m", "poor_cli", "shims", "--help"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        claude = subprocess.run(["claude", "-p", "explain repo"], cwd=root, env=env, text=True, capture_output=True, check=False)
        codex = subprocess.run(["codex", "exec", "review diff"], cwd=root, env=env, text=True, capture_output=True, check=False)
        store = RunStore(root / ".poor-cli" / "v6")
        try:
            runs = store.list_runs()
            replayed = {run["user_goal"]: replay_verify(store, run["run_id"])["verified"] is True for run in runs}
            secret_clean = not any(
                b"sk-shimacceptance123456789" in path.read_bytes() for path in (root / ".poor-cli").rglob("*") if path.is_file()
            )
        finally:
            store.close()
    checks = {
        "help_commands": all(token in help_result.stdout for token in ("install", "doctor", "uninstall")),
        "install_ok": install == 0,
        "claude_capture": claude.returncode == 0 and replayed.get("explain repo") is True,
        "codex_capture": codex.returncode == 0 and replayed.get("review diff") is True,
        "secret_clean": secret_clean,
    }
    return {"schema_version": "poor-cli-shim-capture-acceptance-v1", "accepted": all(checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/shim_capture_acceptance.py")
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
