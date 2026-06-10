#!/usr/bin/env python3
"""Backend worker integration template for Swee SG.

Dry-run mode:
  python3 examples/integration/backend-worker-template.py --dry-run

Live mode after `npm run build`:
  python3 examples/integration/backend-worker-template.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, TypedDict


LATEST_PROTOCOL_VERSION = "2025-11-25"


class WorkerDecision(TypedDict, total=False):
    kind: str
    reason: str
    retryAfterSec: int


class JsonRpcStdioClient:
    def __init__(self, command: list[str], cwd: Path, env: dict[str, str]) -> None:
        self._process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 1

    def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        if self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=5)

    def _send(self, message: dict[str, Any]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("MCP process stdin is not available.")
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        if self._process.stdout is None:
            raise RuntimeError("MCP process stdout is not available.")

        while True:
            line = self._process.stdout.readline()
            if line == "":
                stderr = ""
                if self._process.stderr is not None:
                    stderr = self._process.stderr.read()
                raise RuntimeError(f"MCP process closed unexpectedly.\n{stderr}")

            payload = json.loads(line)
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                raise RuntimeError(json.dumps(payload["error"], indent=2))
            return payload["result"]

    def initialize(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "swee-backend-worker-template-python", "version": "0.1.0"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})


def get_text(contents: list[dict[str, Any]]) -> str:
    for item in contents:
        text = item.get("text")
        if isinstance(text, str):
            return text
    raise RuntimeError("Expected text content from MCP response.")


def call_pulse_snapshot(client: JsonRpcStdioClient, focus: str, area: str | None = None) -> dict[str, Any]:
    arguments: dict[str, Any] = {"focus": focus}
    if area:
        arguments["area"] = area
    result = client.call_tool("swee_pulse_snapshot", arguments)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return json.loads(get_text(result["content"]))


def decide(payload: dict[str, Any]) -> WorkerDecision:
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    signals = snapshot.get("signals") if isinstance(snapshot, dict) else []
    source_health = snapshot.get("sourceHealth") if isinstance(snapshot, dict) else []
    gaps = snapshot.get("gaps") if isinstance(snapshot, dict) else []

    if any(isinstance(signal, dict) and signal.get("severity") == "disrupted" for signal in signals):
        return {"kind": "escalate", "reason": "Pulse contains disrupted signals."}
    if any(isinstance(signal, dict) and signal.get("severity") == "watch" for signal in signals):
        return {"kind": "monitor", "reason": "Pulse contains watch-level signals."}
    if gaps or any(isinstance(source, dict) and source.get("status") == "gap" for source in source_health):
        return {"kind": "source_gap", "reason": "Pulse source gaps need review.", "retryAfterSec": 300}
    return {"kind": "complete", "reason": "No watch-level Pulse signals."}


def run_dry() -> None:
    synthetic = [
        ("job-1", {"snapshot": {"signals": [{"severity": "watch"}], "sourceHealth": [], "gaps": []}}),
        ("job-2", {"snapshot": {"signals": [], "sourceHealth": [{"status": "gap"}], "gaps": [{"code": "SOURCE_EMPTY"}]}}),
        ("job-3", {"snapshot": {"signals": [], "sourceHealth": [{"status": "ready"}], "gaps": []}}),
    ]
    for job_id, payload in synthetic:
        decision = decide(payload)
        print(f"[dry-run] {job_id} -> {decision['kind']} ({decision.get('reason', '')})")


def run_live() -> None:
    root = Path(__file__).resolve().parents[2]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    client.initialize()
    try:
        jobs = [("job-1", "all", "Bedok"), ("job-2", "weather", "Ang Mo Kio"), ("job-3", "mobility", None)]
        for job_id, focus, area in jobs:
            payload = call_pulse_snapshot(client, focus, area)
            decision = decide(payload)
            print(f"[live] {job_id} -> {decision['kind']} ({decision.get('reason', '')})")
    finally:
        client.close()


def main() -> None:
    if "--dry-run" in sys.argv:
        run_dry()
        return
    run_live()


if __name__ == "__main__":
    main()
