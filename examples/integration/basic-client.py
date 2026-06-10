#!/usr/bin/env python3
"""Minimal stdlib-only MCP client example for Swee SG.

Run after `npm run build`:
  python3 examples/integration/basic-client.py
"""

from __future__ import annotations

import json
import os
import subprocess
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
                "clientInfo": {"name": "swee-basic-client-python", "version": "0.1.0"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self._request("resources/read", {"uri": uri})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})


def get_text(contents: list[dict[str, Any]]) -> str:
    for item in contents:
        text = item.get("text")
        if isinstance(text, str):
            return text
    raise RuntimeError("Expected text content from MCP response.")


def read_json_resource(client: JsonRpcStdioClient, uri: str) -> Any:
    result = client.read_resource(uri)
    return json.loads(get_text(result["contents"]))


def call_tool_payload(client: JsonRpcStdioClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = client.call_tool(name, arguments)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return json.loads(get_text(result["content"]))


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    client.initialize()
    try:
        runtime = read_json_resource(client, "sg://runtime")
        recipes = read_json_resource(client, "sg://recipes")
        pulse = call_tool_payload(client, "swee_pulse_snapshot", {"focus": "all", "area": "Bedok"})
        shield = call_tool_payload(client, "swee_shield_scan_tools", {})

        snapshot = pulse["snapshot"]
        print("connected to Swee SG")
        print(f"runtime: {runtime.get('schemaVersion', 'unknown')}")
        print(f"recipes: {', '.join(recipe['name'] for recipe in recipes)}")
        print(f"signals: {len(snapshot.get('signals', []))}")
        print(f"source health rows: {len(snapshot.get('sourceHealth', []))}")
        print(f"shield findings: {len(shield.get('findings', []))}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
