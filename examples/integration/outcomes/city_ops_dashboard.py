#!/usr/bin/env python3
"""City operations outcome example for Swee SG."""

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
                "clientInfo": {"name": "city-ops-dashboard-python", "version": "0.1.0"},
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


def call_payload(client: JsonRpcStdioClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = client.call_tool(name, arguments)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return json.loads(get_text(result["content"]))


def render_snapshot(area: str, snapshot: dict[str, Any]) -> None:
    print(f"\n=== Swee Pulse for {area} ===")
    for signal in snapshot.get("signals", [])[:10]:
        if isinstance(signal, dict):
            print(f"  - [{signal.get('severity', 'unknown')}] {signal.get('title', '(untitled)')} ({signal.get('sourceTool', 'unknown')})")
    gaps = snapshot.get("gaps", [])
    if gaps:
        print("Gaps:")
        for gap in gaps:
            if isinstance(gap, dict):
                print(f"  - {gap.get('code', 'UNKNOWN_GAP')}: {gap.get('message', '')}")


def main() -> None:
    area = sys.argv[1] if len(sys.argv) > 1 else "Bedok"
    root = Path(__file__).resolve().parents[3]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    client.initialize()
    try:
        pulse = call_payload(client, "swee_pulse_snapshot", {"focus": "all", "area": area})
        render_snapshot(area, pulse["snapshot"])
        audits = call_payload(client, "swee_shield_audit_lookup", {"limit": 5})
        print(f"\nRecent Shield audit rows: {len(audits.get('records', []))}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
