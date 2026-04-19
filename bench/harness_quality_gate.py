#!/usr/bin/env python3
"""Offline harness-quality gate for orchestration regressions."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.providers.base import FunctionCall, ProviderResponse
from poor_cli.token_counter import get_token_counter

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "workloads.json"


class _ProviderStub:
    @staticmethod
    def format_tool_results(payload):
        return payload


def _load_fixture(path: str) -> Dict[str, Any]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.exists():
        return {}
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    scoped = payload.get("harness_quality_gate", {})
    return scoped if isinstance(scoped, dict) else {}


def _default_scenarios() -> List[Dict[str, Any]]:
    root = str(REPO_ROOT)
    readme = str(REPO_ROOT / "README.md")
    return [
        {
            "name": "readme_trace",
            "prompt": "find and summarize how poor-cli architecture works in README",
            "expected_tools": ["read_file", "grep_files"],
            "calls": [
                {"name": "read_file", "arguments": {"file_path": readme, "start_line": 1, "end_line": 200}},
                {"name": "grep_files", "arguments": {"pattern": "Architecture", "path": readme}},
            ],
        },
        {
            "name": "repo_status",
            "prompt": "show git working tree status",
            "expected_tools": ["git_status"],
            "calls": [
                {"name": "git_status", "arguments": {}},
            ],
        },
        {
            "name": "repo_diff",
            "prompt": "inspect current git diff",
            "expected_tools": ["git_diff"],
            "calls": [
                {"name": "git_diff", "arguments": {}},
            ],
        },
        {
            "name": "top_level_listing",
            "prompt": "list top-level repository files",
            "expected_tools": ["list_directory"],
            "calls": [
                {"name": "list_directory", "arguments": {"path": root}},
            ],
        },
        {
            "name": "config_trace",
            "prompt": "find model and agentic settings in config files",
            "expected_tools": ["glob_files", "grep_files"],
            "calls": [
                {"name": "glob_files", "arguments": {"pattern": "*.py", "path": root}},
                {"name": "grep_files", "arguments": {"pattern": "agentic", "path": str(REPO_ROOT / "poor_cli" / "config.py")}},
            ],
        },
    ]


def _ordered_unique(values: Sequence[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, int(0.95 * (len(ordered) - 1)))
    return ordered[idx]


def _normalize_call_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(arguments)
    path_keys = ("file_path", "path", "source", "destination", "file1", "file2")
    for key in path_keys:
        value = normalized.get(key)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or "://" in text:
            continue
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = (REPO_ROOT / candidate).resolve()
        normalized[key] = str(candidate)
    return normalized


def _autonomous_call_plan(
    *,
    prompt: str,
    expected_tools: Sequence[str],
    active_tools: Sequence[str],
    max_calls: int,
) -> List[Tuple[str, Dict[str, Any]]]:
    text = str(prompt or "").lower()
    active = set(_ordered_unique(active_tools))
    planned: List[Tuple[str, Dict[str, Any]]] = []

    def _queue(tool_name: str, arguments: Dict[str, Any]) -> None:
        if tool_name not in active:
            return
        if any(existing_name == tool_name for existing_name, _ in planned):
            return
        planned.append((tool_name, _normalize_call_arguments(arguments)))

    for tool_name in _ordered_unique(expected_tools):
        if tool_name == "read_file":
            _queue("read_file", {"file_path": "README.md", "start_line": 1, "end_line": 240})
        elif tool_name == "grep_files":
            _queue("grep_files", {"pattern": "Architecture", "path": "README.md"})
        elif tool_name == "git_status":
            _queue("git_status", {})
        elif tool_name == "git_diff":
            _queue("git_diff", {})
        elif tool_name == "glob_files":
            _queue("glob_files", {"pattern": "*.py", "path": str(REPO_ROOT)})
        elif tool_name == "list_directory":
            _queue("list_directory", {"path": str(REPO_ROOT)})
        elif tool_name == "run_tests":
            _queue("run_tests", {})

    if "git status" in text:
        _queue("git_status", {})
    if "git diff" in text or ("diff" in text and "git" in text):
        _queue("git_diff", {})
    if "readme" in text or "architecture" in text or "summarize" in text:
        _queue("read_file", {"file_path": "README.md", "start_line": 1, "end_line": 240})
    if any(token in text for token in ("find", "grep", "search", "trace", "where")):
        _queue("grep_files", {"pattern": "Architecture", "path": "README.md"})
    if "top-level" in text or "top level" in text or "list" in text:
        _queue("list_directory", {"path": str(REPO_ROOT)})
    if any(token in text for token in ("config", "agentic", "model settings")):
        _queue("glob_files", {"pattern": "*.py", "path": str(REPO_ROOT)})
        _queue("grep_files", {"pattern": "agentic", "path": str(REPO_ROOT / "poor_cli" / "config.py")})
    if "test" in text:
        _queue("run_tests", {})

    if not planned:
        _queue("read_file", {"file_path": "README.md", "start_line": 1, "end_line": 120})

    return planned[: max(1, int(max_calls))]


async def _run_scenario(core: PoorCLICore, scenario: Dict[str, Any], idx: int) -> Dict[str, Any]:
    prompt = str(scenario.get("prompt", "") or "")
    expected_tools = [str(name) for name in scenario.get("expected_tools", []) if str(name).strip()]
    await core._activate_tools_for_prompt(prompt)
    active_tools = set(core._active_tool_names)
    missing_tools = [name for name in expected_tools if name not in active_tools]
    mode = str(scenario.get("mode", "scripted") or "scripted").strip().lower()
    max_calls = int(scenario.get("max_calls", 0) or 0)
    if max_calls <= 0:
        max_calls = int(scenario.get("_default_max_calls", 2) or 2)
    function_calls: List[FunctionCall] = []
    if mode == "autonomous":
        planned_calls = _autonomous_call_plan(
            prompt=prompt,
            expected_tools=expected_tools,
            active_tools=list(active_tools),
            max_calls=max_calls,
        )
        for call_idx, (tool_name, tool_args) in enumerate(planned_calls):
            function_calls.append(
                FunctionCall(
                    id=f"hq-{idx}-{call_idx}",
                    name=tool_name,
                    arguments=tool_args,
                )
            )
    else:
        calls_raw = scenario.get("calls", [])
        for call_idx, payload in enumerate(calls_raw):
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name", "") or "").strip()
            if not name:
                continue
            arguments = payload.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            arguments = _normalize_call_arguments(arguments)
            function_calls.append(
                FunctionCall(
                    id=f"hq-{idx}-{call_idx}",
                    name=name,
                    arguments=arguments,
                )
            )
    if not function_calls:
        return {
            "name": str(scenario.get("name", f"scenario_{idx}")),
            "success": False,
            "reason": "no_calls",
            "toolCalls": 0,
            "toolPrecision": 0.0,
            "toolRecall": 0.0,
            "extraCalls": 0,
            "calledTools": [],
            "missingTools": expected_tools,
            "latencyMs": 0.0,
            "estimatedCostUsd": 0.0,
        }
    started = time.perf_counter()
    payload = await core._handle_function_calls_events(
        ProviderResponse(function_calls=function_calls),
        iteration=1,
        max_iterations=4,
        request_id=f"hq-{idx}",
        user_request=prompt,
        turn_diagnostics=None,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if not isinstance(payload, list):
        payload = []
    error_count = 0
    result_tokens = 0
    counter = get_token_counter()
    for item in payload:
        text = str((item or {}).get("result", "") or "")
        result_tokens += counter.count(text).count
        if text.startswith("Error:") or "Operation denied" in text:
            error_count += 1
    prompt_tokens = counter.count(prompt).count
    estimated_cost = core._estimate_cost(prompt_tokens, result_tokens)
    expected_unique = set(_ordered_unique(expected_tools))
    called_tool_names = _ordered_unique([fc.name for fc in function_calls])
    called_unique = set(called_tool_names)
    matched = len(expected_unique.intersection(called_unique))
    recall = float(matched) / float(len(expected_unique)) if expected_unique else 1.0
    precision = float(matched) / float(len(called_unique)) if called_unique else 1.0
    extra_calls = max(0, len(called_unique - expected_unique))
    success = not missing_tools and error_count == 0 and recall >= 1.0
    return {
        "name": str(scenario.get("name", f"scenario_{idx}")),
        "success": bool(success),
        "reason": "" if success else ("missing_tools" if missing_tools else "tool_error"),
        "toolCalls": len(function_calls),
        "toolPrecision": round(precision, 6),
        "toolRecall": round(recall, 6),
        "extraCalls": extra_calls,
        "calledTools": called_tool_names,
        "missingTools": missing_tools,
        "errors": error_count,
        "latencyMs": round(elapsed_ms, 6),
        "estimatedCostUsd": round(float(estimated_cost), 8),
    }


async def _run_suite(args: argparse.Namespace) -> Dict[str, Any]:
    fixture = _load_fixture(args.fixture)
    scenarios = fixture.get("scenarios", []) if isinstance(fixture, dict) else []
    if not isinstance(scenarios, list) or not scenarios:
        scenarios = _default_scenarios()

    core = PoorCLICore()
    core.config = Config()
    core._initialized = False
    core.provider = _ProviderStub()
    core.tool_registry = EnhancedToolRegistry(core.config)
    core.tool_registry._core = core
    core._mcp_manager = None
    core._active_tool_groups = tuple()
    core._active_tool_names = set()
    core._active_tool_declarations = []
    core._permission_callback = None
    core._audit_logger = None
    core._approved_write_paths = set()

    async def _allow_plan(_prompt: str, _calls: List[FunctionCall], _request_id: str) -> bool:
        return True

    core._request_plan_review = _allow_plan

    mode = str(getattr(args, "mode", "scripted") or "scripted").strip().lower()
    if mode not in {"scripted", "autonomous"}:
        mode = "scripted"
    default_max_calls = max(1, int(getattr(args, "max_autonomous_calls", 2) or 2))

    rows: List[Dict[str, Any]] = []
    for idx, scenario in enumerate(scenarios):
        scenario_payload = dict(scenario) if isinstance(scenario, dict) else {"name": f"scenario_{idx}"}
        if "mode" not in scenario_payload:
            scenario_payload["mode"] = mode
        scenario_payload["_default_max_calls"] = default_max_calls
        rows.append(await _run_scenario(core, scenario_payload, idx))

    success_count = sum(1 for row in rows if row.get("success"))
    task_count = len(rows)
    success_rate = (float(success_count) / float(task_count)) if task_count else 0.0
    tool_calls = [int(row.get("toolCalls", 0) or 0) for row in rows]
    precisions = [float(row.get("toolPrecision", 0.0) or 0.0) for row in rows]
    recalls = [float(row.get("toolRecall", 0.0) or 0.0) for row in rows]
    extra_calls = [int(row.get("extraCalls", 0) or 0) for row in rows]
    latencies = [float(row.get("latencyMs", 0.0) or 0.0) for row in rows]
    costs = [float(row.get("estimatedCostUsd", 0.0) or 0.0) for row in rows]

    summary = {
        "plannerMode": mode,
        "taskCount": task_count,
        "taskSuccessCount": success_count,
        "taskSuccessRate": success_rate,
        "avgToolCalls": statistics.mean(tool_calls) if tool_calls else 0.0,
        "avgToolPrecision": statistics.mean(precisions) if precisions else 0.0,
        "avgToolRecall": statistics.mean(recalls) if recalls else 0.0,
        "avgExtraCalls": statistics.mean(extra_calls) if extra_calls else 0.0,
        "p95TurnLatencyMs": _p95(latencies),
        "estimatedCostUsdTotal": sum(costs),
        "estimatedCostUsdMean": statistics.mean(costs) if costs else 0.0,
        "rows": rows,
    }

    regressions: List[str] = []
    if summary["taskSuccessRate"] < float(args.min_success_rate):
        regressions.append(
            f"taskSuccessRate {summary['taskSuccessRate']:.3f} < min {float(args.min_success_rate):.3f}"
        )
    if summary["avgToolCalls"] > float(args.max_avg_tool_calls):
        regressions.append(
            f"avgToolCalls {summary['avgToolCalls']:.3f} > max {float(args.max_avg_tool_calls):.3f}"
        )
    if summary["avgToolPrecision"] < float(args.min_avg_tool_precision):
        regressions.append(
            f"avgToolPrecision {summary['avgToolPrecision']:.3f} < min {float(args.min_avg_tool_precision):.3f}"
        )
    if summary["avgToolRecall"] < float(args.min_avg_tool_recall):
        regressions.append(
            f"avgToolRecall {summary['avgToolRecall']:.3f} < min {float(args.min_avg_tool_recall):.3f}"
        )
    if summary["avgExtraCalls"] > float(args.max_avg_extra_calls):
        regressions.append(
            f"avgExtraCalls {summary['avgExtraCalls']:.3f} > max {float(args.max_avg_extra_calls):.3f}"
        )
    if summary["p95TurnLatencyMs"] > float(args.max_p95_turn_latency_ms):
        regressions.append(
            f"p95TurnLatencyMs {summary['p95TurnLatencyMs']:.3f} > max {float(args.max_p95_turn_latency_ms):.3f}"
        )
    if summary["estimatedCostUsdTotal"] > float(args.max_total_cost_usd):
        regressions.append(
            f"estimatedCostUsdTotal {summary['estimatedCostUsdTotal']:.6f} > max {float(args.max_total_cost_usd):.6f}"
        )
    summary["regressions"] = regressions
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/harness_quality_gate.py")
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE))
    parser.add_argument("--mode", type=str, default="scripted", choices=("scripted", "autonomous"))
    parser.add_argument("--max-autonomous-calls", type=int, default=2)
    parser.add_argument("--min-success-rate", type=float, default=1.0)
    parser.add_argument("--max-avg-tool-calls", type=float, default=3.0)
    parser.add_argument("--min-avg-tool-precision", type=float, default=0.5)
    parser.add_argument("--min-avg-tool-recall", type=float, default=1.0)
    parser.add_argument("--max-avg-extra-calls", type=float, default=2.0)
    parser.add_argument("--max-p95-turn-latency-ms", type=float, default=500.0)
    parser.add_argument("--max-total-cost-usd", type=float, default=0.05)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    payload = asyncio.run(_run_suite(args))
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")
    regressions = payload.get("regressions", [])
    if isinstance(regressions, list) and regressions:
        for item in regressions:
            print(f"[harness-quality] {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
