#!/usr/bin/env python3
"""Backend worker integration template for Dude MCP.

Demonstrates explicit handling for completed / blocked / unsupported / failed
sg_query outcomes in Python services.

Dry-run mode (CI friendly):
  python3 examples/integration/backend-worker-template.py --dry-run

Live mode (requires built server):
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


class QueryBlocker(TypedDict):
    field: str
    directTool: str
    suggestedPrompt: str


class QueryFailedStep(TypedDict, total=False):
    tool: str
    error: dict[str, Any]


class QueryOutcome(TypedDict, total=False):
    status: str
    workflow: str
    reason: str
    suggestion: str
    blockers: list[QueryBlocker]
    failedStep: QueryFailedStep | None


class WorkerDecision(TypedDict, total=False):
    kind: str
    reason: str
    blockers: list[QueryBlocker]
    retryAfterSec: int
    suggestion: str


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
                    "name": "backend-worker-template-python",
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


def call_query(client: JsonRpcStdioClient, prompt: str) -> QueryOutcome:
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


def lookup_retryable(ops_taxonomy: dict[str, Any], code: str | None) -> bool:
    if code is None:
        return False
    error_codes = ops_taxonomy.get("errorCodes")
    if not isinstance(error_codes, list):
        return False
    for entry in error_codes:
        if isinstance(entry, dict) and entry.get("code") == code:
            return bool(entry.get("retryable"))
    return False


def decide(outcome: QueryOutcome, ops_taxonomy: dict[str, Any]) -> WorkerDecision:
    status = outcome.get("status")
    if status == "completed":
        return {"kind": "completed", "reason": "workflow completed"}
    if status == "blocked":
        blockers = outcome.get("blockers") or []
        return {
            "kind": "needs_input",
            "reason": outcome.get("reason", "Missing required fields."),
            "blockers": blockers,
        }
    if status == "unsupported":
        return {
            "kind": "fallback_discovery",
            "reason": outcome.get("reason", "Prompt outside bounded workflows."),
            "suggestion": outcome.get("suggestion", "Try sg://recipes or direct sg_* tools."),
        }
    if status == "failed":
        failed = outcome.get("failedStep") or {}
        error = failed.get("error") if isinstance(failed, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        retryable = bool(error.get("retryable")) if isinstance(error, dict) else False
        retryable = retryable or lookup_retryable(ops_taxonomy, code if isinstance(code, str) else None)
        reason = error.get("message") if isinstance(error, dict) else None
        if not isinstance(reason, str):
            reason = outcome.get("reason", "Workflow failed.")
        if retryable:
            return {
                "kind": "retryable_failure",
                "reason": reason,
                "retryAfterSec": 30,
            }
        return {"kind": "terminal_failure", "reason": reason}
    return {"kind": "terminal_failure", "reason": f"Unhandled sg_query status: {status}"}


def run_dry() -> None:
    ops_taxonomy = {
        "errorCodes": [
            {"code": "UPSTREAM_TIMEOUT", "retryable": True},
            {"code": "VALIDATION_ERROR", "retryable": False},
        ]
    }
    synthetic: list[tuple[str, QueryOutcome]] = [
        ("job-1", {"status": "completed", "workflow": "business_dossier"}),
        (
            "job-2",
            {
                "status": "blocked",
                "reason": "Need one company or UEN identifier.",
                "blockers": [
                    {
                        "field": "entityName",
                        "directTool": "sg_business_dossier",
                        "suggestedPrompt": "Business dossier for DP Architects",
                    }
                ],
            },
        ),
        ("job-3", {"status": "unsupported", "reason": "Prompt is outside bounded workflows."}),
        (
            "job-4",
            {
                "status": "failed",
                "failedStep": {"tool": "sg_business_dossier", "error": {"code": "UPSTREAM_TIMEOUT", "message": "ACRA timed out"}},
            },
        ),
    ]
    for job_id, outcome in synthetic:
        decision = decide(outcome, ops_taxonomy)
        print(f"[dry-run] {job_id} -> {decision['kind']} ({decision.get('reason', '')})")


def run_live() -> None:
    root = Path(__file__).resolve().parents[2]
    server_entry = root / "packages" / "mcp-server" / "dist" / "index.js"
    env = os.environ.copy()
    env["SG_APIS_LOG_LEVEL"] = "error"

    client = JsonRpcStdioClient(["node", str(server_entry)], root, env)
    client.initialize()
    try:
        ops_taxonomy = read_json_resource(client, "sg://ops-taxonomy")
        prompts = [
            ("job-1", "Architecture firm diligence for DP Architects"),
            ("job-2", "Run business diligence"),
            ("job-3", "Compare GDP and CPI in Singapore"),
            ("job-4", "Business dossier for ABC CONSTRUCTION PTE LTD"),
        ]
        for job_id, prompt in prompts:
            outcome = call_query(client, prompt)
            decision = decide(outcome, ops_taxonomy)
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
