#!/usr/bin/env python3
"""Offline failure-injection matrix for harness recovery behavior."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

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
