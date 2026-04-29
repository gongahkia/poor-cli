#!/usr/bin/env python3
"""SME diligence dashboard outcome (job-runner pattern, blocked-state recovery).

Run after `npm run build`:
  python3 examples/integration/outcomes/sme_diligence_dashboard.py "DP ARCHITECTS PTE LTD"

This pattern is designed for backend workers / batch jobs that need to:
- Loop over a queue of company identifiers.
- Call sg_query and recover from blocked / unsupported / failed outcomes.
- Persist the brief envelope and risk flags for downstream review.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


LATEST_PROTOCOL_VERSION = "2025-11-25"


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

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("MCP process not available.")
        self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
        self._process.stdin.flush()
        while True:
            line = self._process.stdout.readline()
            if line == "":
                raise RuntimeError("MCP process closed unexpectedly.")
            payload = json.loads(line)
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                raise RuntimeError(json.dumps(payload["error"], indent=2))
            return payload["result"]

    def initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "sme-diligence-job", "version": "0.1.0"},
        })
        if self._process.stdin is not None:
            self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            self._process.stdin.flush()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})


def call_payload(client: JsonRpcStdioClient, name: str, arguments: dict[str, Any]) -> Any:
    result = client.call_tool(name, arguments)
    structured = result.get("structuredContent")
    if structured is not None:
        return structured.get("record", structured)
    text_content = next((c for c in result.get("content", []) if c.get("type") == "text"), None)
    if text_content is None:
        return None
    return json.loads(text_content["text"])


def render_brief(label: str, brief: dict[str, Any]) -> None:
    print(f"\n=== {label} :: {brief.get('title', '(no title)')} ===")
    for item in brief.get("summary", []):
        print(f"  - {item['label']}: {item['value']!r} [{item['source']}]")
    for flag in brief.get("riskFlags") or []:
        print(f"  ! [{flag['severity'].upper()}] {flag['code']}: {flag['message']}")
    for gap in brief.get("gaps") or []:
        print(f"  ? gap {gap['code']}: {gap['message']}")
    for check in brief.get("nextChecks") or []:
        print(f"  -> next: {check['tool']} ({check['reason']})")


def process_target(client: JsonRpcStdioClient, target: str) -> dict[str, Any]:
    """Job-runner unit of work: returns a record describing the outcome."""
    try:
        dossier = call_payload(client, "sg_business_dossier", {
            "companyName": target,
            "format": "json",
        })
    except RuntimeError as error:
        return {"target": target, "status": "failed", "error": str(error)}

    if not isinstance(dossier, dict):
        return {"target": target, "status": "failed", "error": "Unexpected dossier shape."}

    render_brief(target, dossier)

    risk_flags = dossier.get("riskFlags") or []
    next_checks = dossier.get("nextChecks") or []
    return {
        "target": target,
        "status": "completed",
        "riskFlagCount": len(risk_flags),
        "highSeverity": [flag["code"] for flag in risk_flags if flag.get("severity") == "high"],
        "nextChecks": [check["tool"] for check in next_checks],
    }


def main() -> None:
    targets = sys.argv[1:] or ["DP ARCHITECTS PTE LTD"]
    root = Path(__file__).resolve().parents[3]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    try:
        client.initialize()
        results = [process_target(client, target) for target in targets]
        print("\n=== job summary ===")
        print(json.dumps(results, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
