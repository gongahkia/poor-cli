#!/usr/bin/env python3
"""Queue consumer integration template for sg-apis-mcp.

Demonstrates deterministic queue action mapping from sg_query outcomes:
- completed -> ack
- blocked -> park_for_input
- unsupported -> route_to_discovery_lane
- failed(retryable) -> retry_later
- failed(non-retryable) -> dead_letter

Dry-run mode (CI friendly):
  python3 examples/integration/queue-consumer-template.py --dry-run

Live mode (requires built server):
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
    prompt: str


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
        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })

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
                "clientInfo": {
                    "name": "queue-consumer-template-python",
                    "version": "0.1.0",
                },
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


def query(client: JsonRpcStdioClient, prompt: str) -> dict[str, Any]:
    result = client.call_tool(
        "sg_query",
        {
            "query": prompt,
            "mode": "execute",
            "format": "json",
            "includeContextIds": True,
        },
    )
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return json.loads(get_text(result["content"]))


def to_queue_action(outcome: dict[str, Any]) -> tuple[str, str]:
    status = outcome.get("status")
    if status == "completed":
        return ("ack", "workflow completed")
    if status == "blocked":
        return ("park_for_input", outcome.get("reason", "missing required fields"))
    if status == "unsupported":
        return ("route_to_discovery_lane", outcome.get("reason", "outside bounded workflows"))
    if status == "failed":
        failed_step = outcome.get("failedStep") or {}
        error = failed_step.get("error") if isinstance(failed_step, dict) else {}
        retryable = bool(error.get("retryable")) if isinstance(error, dict) else False
        detail = error.get("message") if isinstance(error, dict) else None
        if not isinstance(detail, str):
            detail = outcome.get("reason", "workflow failed")
        return ("retry_later" if retryable else "dead_letter", detail)
    return ("dead_letter", f"unhandled status: {status}")


def run_jobs(jobs: list[QueueJob], outcomes: list[dict[str, Any]]) -> None:
    if len(jobs) != len(outcomes):
        raise RuntimeError("jobs and outcomes length mismatch")
    for job, outcome in zip(jobs, outcomes):
        action, detail = to_queue_action(outcome)
        print(f"{job.id}: {action} - {detail}")


def run_dry() -> None:
    jobs = [
        QueueJob("job-1", "Architecture firm diligence for DP Architects"),
        QueueJob("job-2", "Find a social service office near me"),
        QueueJob("job-3", "Compare GDP and CPI in Singapore"),
        QueueJob("job-4", "Transport status in Singapore right now"),
    ]
    synthetic = [
        {"status": "completed"},
        {"status": "blocked", "reason": "Need a planning area or postal code."},
        {"status": "unsupported", "reason": "Prompt outside bounded workflows."},
        {"status": "failed", "failedStep": {"error": {"message": "LTA timed out", "retryable": True}}},
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
        jobs = [
            QueueJob("job-1", "Architecture firm diligence for DP Architects"),
            QueueJob("job-2", "Find a social service office near me"),
            QueueJob("job-3", "Compare GDP and CPI in Singapore"),
            QueueJob("job-4", "Find datasets about a definitely unknown topic"),
        ]
        outcomes = [query(client, job.prompt) for job in jobs]
        run_jobs(jobs, outcomes)
    finally:
        client.close()


def main() -> None:
    if "--dry-run" in sys.argv:
        run_dry()
        return
    run_live()


if __name__ == "__main__":
    main()
