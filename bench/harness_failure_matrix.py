#!/usr/bin/env python3
# ruff: noqa: E402
"""Offline failure-injection matrix for harness recovery behavior."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.providers.base import FunctionCall, ProviderResponse


class _ProviderStub:
    @staticmethod
    def format_tool_results(payload):
        return payload


def _default_scenarios() -> List[Dict[str, Any]]:
    return [
        {
            "name": "unknown_tool",
            "prompt": "execute unknown tool",
            "calls": [{"name": "no_such_tool_xyz", "arguments": {}}],
            "expectHandledError": True,
            "expectedKeywords": ["unknown tool", "error"],
        },
        {
            "name": "read_missing_file",
            "prompt": "read file that does not exist",
            "calls": [{"name": "read_file", "arguments": {"file_path": "tmp/no-such-file.txt"}}],
            "expectHandledError": True,
            "expectedKeywords": ["not found", "no such file", "error"],
        },
        {
            "name": "bash_timeout",
            "prompt": "run command that times out",
            "calls": [{"name": "bash", "arguments": {"command": "sleep 2", "timeout": 1}}],
            "expectHandledError": True,
            "expectedKeywords": ["timeout", "timed out", "error"],
        },
        {
            "name": "cancellation_race_injected",
            "prompt": "simulate cancellation while tool is running",
            "calls": [{"name": "read_file", "arguments": {"file_path": "README.md", "start_line": 1, "end_line": 40}}],
            "expectHandledError": True,
            "expectedKeywords": ["cancelled", "cancel"],
            "injectHangMs": 1200,
            "cancelAfterMs": 80,
        },
        {
            "name": "mcp_timeout_injected",
            "prompt": "simulate mcp timeout on tool call",
            "calls": [{"name": "read_file", "arguments": {"file_path": "README.md", "start_line": 1, "end_line": 30}}],
            "expectHandledError": True,
            "expectedKeywords": ["mcp request timed out", "timeout"],
            "injectMcpTimeout": True,
        },
    ]


def _normalize_call_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(arguments)
    for key in ("file_path", "path"):
        value = normalized.get(key)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or "://" in text:
            continue
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        normalized[key] = str(candidate)
    return normalized


async def _run_one(core: PoorCLICore, scenario: Dict[str, Any], idx: int, *, max_scenario_ms: float) -> Dict[str, Any]:
    name = str(scenario.get("name", f"scenario_{idx}") or f"scenario_{idx}")
    prompt = str(scenario.get("prompt", "") or "")
    calls = scenario.get("calls", [])
    expected_keywords = [str(token).lower() for token in scenario.get("expectedKeywords", [])]
    expect_handled_error = bool(scenario.get("expectHandledError", True))
    request_id = f"failure-{idx}"
    function_calls: List[FunctionCall] = []
    for call_idx, payload in enumerate(calls):
        if not isinstance(payload, dict):
            continue
        tool_name = str(payload.get("name", "") or "").strip()
        if not tool_name:
            continue
        args = payload.get("arguments", {})
        if not isinstance(args, dict):
            args = {}
        function_calls.append(
            FunctionCall(
                id=f"{request_id}-{call_idx}",
                name=tool_name,
                arguments=_normalize_call_arguments(args),
            )
        )
    if not function_calls:
        return {
            "name": name,
            "handled": False,
            "reason": "no_calls",
            "latencyMs": 0.0,
            "errorCount": 0,
            "stuck": False,
        }

    await core._activate_tools_for_prompt(prompt)

    async def _permission(tool_name: str, _args: Dict[str, Any], _request_id: str) -> bool:
        if bool(scenario.get("denyWrites")) and str(tool_name or "").strip() in {"write_file", "edit_file", "delete_file"}:
            return False
        return True

    core._permission_callback = _permission
    if bool(scenario.get("cancelBeforeRun")):
        core.cancel_request(request_id)
    cancel_after_ms = max(0, int(scenario.get("cancelAfterMs", 0) or 0))
    inject_hang_ms = max(0, int(scenario.get("injectHangMs", 0) or 0))
    inject_mcp_timeout = bool(scenario.get("injectMcpTimeout", False))
    original_execute = core._execute_single_call_events
    cancel_task: Optional[asyncio.Task] = None

    async def _cancel_later() -> None:
        await asyncio.sleep(float(cancel_after_ms) / 1000.0)
        core.cancel_request(request_id)

    async def _execute_injected(function_call: FunctionCall, *args, **kwargs):
        if inject_mcp_timeout:
            return [], {
                "id": function_call.id,
                "name": function_call.name,
                "result": "Error: MCP request timed out after 2.0 seconds",
            }
        if inject_hang_ms > 0:
            remaining_ms = inject_hang_ms
            step_ms = 50
            while remaining_ms > 0:
                await asyncio.sleep(min(step_ms, remaining_ms) / 1000.0)
                remaining_ms -= step_ms
                cancel_event = core._cancel_events.get(request_id)
                if cancel_event and cancel_event.is_set():
                    return [], {
                        "id": function_call.id,
                        "name": function_call.name,
                        "result": "Error: Request cancelled during tool execution",
                    }
        return await original_execute(function_call, *args, **kwargs)

    if inject_mcp_timeout or inject_hang_ms > 0:
        core._execute_single_call_events = _execute_injected
    if cancel_after_ms > 0:
        cancel_task = asyncio.create_task(_cancel_later())

    started = time.perf_counter()
    try:
        payload = await core._handle_function_calls_events(
            ProviderResponse(function_calls=function_calls),
            iteration=1,
            max_iterations=4,
            request_id=request_id,
            user_request=prompt,
            turn_diagnostics=None,
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "name": name,
            "handled": False,
            "reason": f"exception:{type(exc).__name__}",
            "latencyMs": round(elapsed_ms, 6),
            "errorCount": 1,
            "stuck": elapsed_ms > max_scenario_ms,
        }
    finally:
        core._execute_single_call_events = original_execute
        if cancel_task is not None:
            if not cancel_task.done():
                cancel_task.cancel()
                try:
                    await cancel_task
                except asyncio.CancelledError:
                    pass
        core._permission_callback = None
        core._clear_cancel_event(request_id)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if not isinstance(payload, list):
        payload = []
    results = [str((item or {}).get("result", "") or "") for item in payload]
    joined = "\n".join(results).lower()
    error_count = sum(1 for text in results if text.strip().startswith("Error:") or "denied" in text.lower())
    keyword_hit = any(keyword in joined for keyword in expected_keywords) if expected_keywords else True
    if expect_handled_error:
        handled = keyword_hit or error_count > 0
    else:
        handled = error_count == 0
    preview = joined[:240]
    return {
        "name": name,
        "handled": handled,
        "reason": "" if handled else "unexpected_outcome",
        "latencyMs": round(elapsed_ms, 6),
        "errorCount": error_count,
        "resultPreview": preview,
        "stuck": elapsed_ms > max_scenario_ms,
    }


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    scenarios = _default_scenarios()
    core = PoorCLICore()
    core.config = Config()
    core.config.agentic.auto_lint = False
    core._initialized = False
    core.provider = _ProviderStub()
    core.tool_registry = EnhancedToolRegistry(core.config)
    core.tool_registry._core = core
    core._mcp_manager = None
    core._active_tool_groups = tuple()
    core._active_tool_names = set()
    core._active_tool_declarations = []
    core._audit_logger = None
    core._approved_write_paths = set()

    async def _allow_plan(_prompt: str, _calls: List[FunctionCall], _request_id: str) -> bool:
        return True

    core._request_plan_review = _allow_plan
    rows: List[Dict[str, Any]] = []
    max_scenario_ms = max(1.0, float(args.max_scenario_latency_ms))
    for idx, scenario in enumerate(scenarios):
        rows.append(await _run_one(core, scenario, idx, max_scenario_ms=max_scenario_ms))
    recovered = sum(1 for row in rows if bool(row.get("handled")))
    total = len(rows)
    recovery_rate = recovered / float(total or 1)
    stuck_count = sum(1 for row in rows if bool(row.get("stuck")))
    mean_latency = sum(float(row.get("latencyMs", 0.0) or 0.0) for row in rows) / float(total or 1)
    regressions: List[str] = []
    if recovery_rate < float(args.min_recovery_success_rate):
        regressions.append(
            f"recoverySuccessRate {recovery_rate:.3f} < min {float(args.min_recovery_success_rate):.3f}"
        )
    if stuck_count > int(args.max_stuck_count):
        regressions.append(f"stuckCount {stuck_count} > max {int(args.max_stuck_count)}")
    if mean_latency > float(args.max_mean_recovery_latency_ms):
        regressions.append(
            f"meanRecoveryLatencyMs {mean_latency:.3f} > max {float(args.max_mean_recovery_latency_ms):.3f}"
        )
    return {
        "scenarioCount": total,
        "recoverySuccessCount": recovered,
        "recoverySuccessRate": recovery_rate,
        "stuckCount": stuck_count,
        "meanRecoveryLatencyMs": mean_latency,
        "rows": rows,
        "regressions": regressions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/harness_failure_matrix.py")
    parser.add_argument("--min-recovery-success-rate", type=float, default=0.8)
    parser.add_argument("--max-stuck-count", type=int, default=0)
    parser.add_argument("--max-scenario-latency-ms", type=float, default=8000.0)
    parser.add_argument("--max-mean-recovery-latency-ms", type=float, default=2500.0)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    payload = asyncio.run(_run(args))
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")
    regressions = payload.get("regressions", [])
    if isinstance(regressions, list) and regressions:
        for item in regressions:
            print(f"[harness-failure-matrix] {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
