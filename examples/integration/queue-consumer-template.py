#!/usr/bin/env python3
"""Queue consumer integration template for Swee SG.

Dry-run mode:
  python3 examples/integration/queue-consumer-template.py --dry-run

Live mode after `npm run build`:
  python3 examples/integration/queue-consumer-template.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LATEST_PROTOCOL_VERSION = "2025-11-25"


@dataclass(frozen=True)
class QueueJob:
    id: str
    focus: str
    area: str | None = None


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
                "clientInfo": {"name": "swee-queue-consumer-template-python", "version": "0.1.0"},
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


def pulse(client: JsonRpcStdioClient, job: QueueJob) -> dict[str, Any]:
    arguments: dict[str, Any] = {"focus": job.focus}
    if job.area:
        arguments["area"] = job.area
    result = client.call_tool("swee_pulse_snapshot", arguments)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return json.loads(get_text(result["content"]))


def to_queue_action(payload: dict[str, Any]) -> tuple[str, str]:
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    signals = snapshot.get("signals") if isinstance(snapshot, dict) else []
    source_health = snapshot.get("sourceHealth") if isinstance(snapshot, dict) else []
    gaps = snapshot.get("gaps") if isinstance(snapshot, dict) else []

    if any(isinstance(signal, dict) and signal.get("severity") == "disrupted" for signal in signals):
        return ("ack_escalated", "disrupted Pulse signal")
    if any(isinstance(signal, dict) and signal.get("severity") == "watch" for signal in signals):
        return ("ack_monitor", "watch-level Pulse signal")
    if gaps or any(isinstance(source, dict) and source.get("status") == "gap" for source in source_health):
        return ("retry_later", "source gap")
    return ("ack", "normal Pulse snapshot")


def run_jobs(jobs: list[QueueJob], payloads: list[dict[str, Any]]) -> None:
    if len(jobs) != len(payloads):
        raise RuntimeError("jobs and payloads length mismatch")
    for job, payload in zip(jobs, payloads):
        action, detail = to_queue_action(payload)
        print(f"{job.id}: {action} - {detail}")


def run_dry() -> None:
    jobs = [
        QueueJob("job-1", "all", "Bedok"),
        QueueJob("job-2", "weather", "Ang Mo Kio"),
        QueueJob("job-3", "mobility"),
    ]
    synthetic = [
        {"snapshot": {"signals": [{"severity": "watch"}], "sourceHealth": [], "gaps": []}},
        {"snapshot": {"signals": [], "sourceHealth": [{"status": "gap"}], "gaps": [{"code": "SOURCE_EMPTY"}]}},
        {"snapshot": {"signals": [], "sourceHealth": [{"status": "ready"}], "gaps": []}},
    ]
    run_jobs(jobs, synthetic)


def run_live() -> None:
    root = Path(__file__).resolve().parents[2]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    client.initialize()
    try:
        jobs = [QueueJob("job-1", "all", "Bedok"), QueueJob("job-2", "weather", "Ang Mo Kio"), QueueJob("job-3", "mobility")]
        payloads = [pulse(client, job) for job in jobs]
        run_jobs(jobs, payloads)
    finally:
        client.close()


def main() -> None:
    if "--dry-run" in sys.argv:
        run_dry()
        return
    run_live()


if __name__ == "__main__":
    main()
