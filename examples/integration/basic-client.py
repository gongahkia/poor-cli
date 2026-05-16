#!/usr/bin/env python3
"""Minimal stdlib-only MCP client example for Dude MCP.

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
                    "name": "basic-python-client",
                    "version": "0.1.0",
                },
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


def call_tool_payload(client: JsonRpcStdioClient, name: str, arguments: dict[str, Any]) -> Any:
    result = client.call_tool(name, arguments)
    structured = result.get("structuredContent")
    if structured is not None:
        return structured
    return json.loads(get_text(result["content"]))


def call_query(client: JsonRpcStdioClient, query: str) -> dict[str, Any]:
    return call_tool_payload(
        client,
        "sg_query",
        {
            "query": query,
            "mode": "execute",
            "format": "json",
        },
    )


def log_query_outcome(label: str, outcome: dict[str, Any]) -> None:
    print(f"\n{label}")
    print(f"status: {outcome.get('status', 'unknown')}")
    if "workflow" in outcome:
        print(f"workflow: {outcome['workflow']}")
    if "toolsUsed" in outcome:
        print(f"tools: {', '.join(outcome['toolsUsed'])}")
    if "reason" in outcome:
        print(f"reason: {outcome['reason']}")
    if "suggestion" in outcome:
        print(f"suggestion: {outcome['suggestion']}")
    blockers = outcome.get("blockers") or []
    if blockers:
        first = blockers[0]
        print(f"first blocker: {first.get('field')} -> {first.get('directTool')}")
        print(f"recovery prompt: {first.get('suggestedPrompt')}")
    if "routingExplanation" in outcome:
        print(f"routing: {outcome['routingExplanation']}")
    failed_step = outcome.get("failedStep") or {}
    if "tool" in failed_step:
        print(f"failed step: {failed_step['tool']}")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    client.initialize()

    try:
        recipes = read_json_resource(client, "sg://recipes")
        runtime = read_json_resource(client, "sg://runtime")
        playbooks = read_json_resource(client, "sg://playbooks")
        health = call_tool_payload(client, "sg_health_check", {})

        print("connected to Dude MCP")
        print(f"cached {len(recipes)} recipes from sg://recipes")
        print(f"cached {len(playbooks)} playbooks from sg://playbooks")
        print(
            "runtime statuses: "
            + ", ".join(
                f"{entry['status']}:{'error' if entry['isError'] else 'ok'}"
                for entry in runtime.get("queryStatusContract", [])
            )
        )
        print(
            "release gates: "
            + ", ".join(runtime.get("releaseReadiness", {}).get("blockingCommands", []))
        )
        print(
            "health probes: "
            + ", ".join(
                f"{entry.get('api')}:{'up' if entry.get('reachable') else 'down'}"
                for entry in health.get("records", [])
            )
        )

        supported = call_query(client, 'Find a social service office named "Social Service Office @ Queenstown"')
        log_query_outcome("covered prompt via sg_query", supported)

        blocked = call_query(client, "Find a social service office near me")
        log_query_outcome("blocked prompt", blocked)

        unsupported = call_query(client, "Compare GDP and CPI in Singapore")
        log_query_outcome("unsupported prompt", unsupported)

        failed = call_query(client, "Find datasets about a definitely unknown topic")
        log_query_outcome("failed prompt", failed)

        direct_fallback = call_tool_payload(client, "sg_singstat_browse", {})
        print("\ndirect tool fallback")
        print("tool: sg_singstat_browse")
        print(f"records: {len(direct_fallback.get('records', []))}")

        direct_lookup = call_tool_payload(
            client,
            "sg_msf_social_service_offices",
            {
                "name": "Social Service Office @ Queenstown",
                "format": "json",
            },
        )
        print("\nexact-parameter direct lookup")
        print("tool: sg_msf_social_service_offices")
        print(f"records: {len(direct_lookup.get('records', []))}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
