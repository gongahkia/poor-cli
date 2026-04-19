#!/usr/bin/env python3
# ruff: noqa: E402
"""Profile capability-graph guided tool activation vs baseline keyword routing."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.config import Config
from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.history import TokenCounter
from poor_cli.tool_capability_graph import ToolCapabilityGraph

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "workloads.json"


def _load_fixture(path: str) -> Dict[str, Any]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.exists():
        return {}
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    scoped = payload.get("tool_capability_graph_profile", {})
    return scoped if isinstance(scoped, dict) else {}


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _default_train_sequences() -> List[Dict[str, Any]]:
    return [
        {"calls": ["read_file", "git_diff"]},
        {"calls": ["read_file", "web_search"]},
        {"calls": ["read_file", "git_diff"]},
        {"calls": ["read_file", "web_search"]},
        {"calls": ["read_file", "run_tests"]},
        {"calls": ["read_file", "git_diff"]},
        {"calls": ["read_file", "web_search"]},
    ]


def _default_eval_scenarios() -> List[Dict[str, Any]]:
    return [
        {"prompt": "check this change", "expected_tools": ["git_diff"]},
        {"prompt": "look this up quickly", "expected_tools": ["web_search"]},
        {"prompt": "validate this patch", "expected_tools": ["run_tests"]},
        {"prompt": "investigate what happened", "expected_tools": ["git_diff", "web_search"]},
    ]


def _build_graph(train_sequences: List[Dict[str, Any]]) -> ToolCapabilityGraph:
    registry = EnhancedToolRegistry(Config())
    with tempfile.TemporaryDirectory() as td:
        graph = ToolCapabilityGraph(base_dir=Path(td))
        for idx, sequence in enumerate(train_sequences):
            calls = _ordered_unique(sequence.get("calls", []))
            request_id = f"train-{idx}"
            for call_idx, tool_name in enumerate(calls):
                call_id = f"{request_id}-{call_idx}"
                group = registry.tool_group_for_name(tool_name) or ""
                graph.observe_tool_call_start(
                    request_id=request_id,
                    call_id=call_id,
                    tool_name=tool_name,
                    group=group,
                    capabilities=registry.get_tool_capabilities(tool_name),
                )
                graph.observe_tool_call_result(
                    request_id=request_id,
                    call_id=call_id,
                    tool_name=tool_name,
                    success=True,
                    latency_ms=45.0 + float(call_idx * 5),
                )
        return graph


def _evaluate_registry(
    registry: EnhancedToolRegistry,
    eval_scenarios: List[Dict[str, Any]],
    *,
    schema_token_budget: int = 0,
) -> Dict[str, Any]:
    misses = 0
    total_expected = 0
    groups_per_prompt: List[int] = []
    declarations_per_prompt: List[int] = []
    schema_tokens_per_prompt: List[int] = []
    latency_ms: List[float] = []
    rows: List[Dict[str, Any]] = []

    for row in eval_scenarios:
        prompt = str(row.get("prompt", "") or "")
        expected_tools = _ordered_unique(row.get("expected_tools", []))
        started = time.perf_counter()
        groups = registry.required_tool_groups(prompt, schema_token_budget=schema_token_budget)
        declarations = registry.get_tool_declarations_for_groups(groups)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        active_names = {
            str(declaration.get("name", "")).strip()
            for declaration in declarations
            if str(declaration.get("name", "")).strip()
        }
        missing = [tool_name for tool_name in expected_tools if tool_name not in active_names]
        misses += len(missing)
        total_expected += len(expected_tools)
        groups_per_prompt.append(len(groups))
        declarations_per_prompt.append(len(active_names))
        schema_tokens_per_prompt.append(
            TokenCounter.estimate_tokens(json.dumps(declarations, sort_keys=True, separators=(",", ":")))
        )
        latency_ms.append(elapsed_ms)
        rows.append(
            {
                "prompt": prompt,
                "groups": groups,
                "activeToolsCount": len(active_names),
                "expectedTools": expected_tools,
                "missingTools": missing,
                "selectionLatencyMs": round(elapsed_ms, 6),
            }
        )

    miss_rate = (float(misses) / float(total_expected)) if total_expected else 0.0
    return {
        "scenarioRows": rows,
        "promptCount": len(eval_scenarios),
        "expectedToolCalls": total_expected,
        "missingToolCalls": misses,
        "missRate": miss_rate,
        "avgGroupsPerPrompt": statistics.mean(groups_per_prompt) if groups_per_prompt else 0.0,
        "avgDeclarationsPerPrompt": statistics.mean(declarations_per_prompt) if declarations_per_prompt else 0.0,
        "avgSchemaTokensPerPrompt": statistics.mean(schema_tokens_per_prompt) if schema_tokens_per_prompt else 0.0,
        "selectionLatencyMeanMs": statistics.mean(latency_ms) if latency_ms else 0.0,
        "selectionLatencyP95Ms": sorted(latency_ms)[max(0, int(0.95 * (len(latency_ms) - 1)))] if latency_ms else 0.0,
    }


def _run(args: argparse.Namespace) -> Dict[str, Any]:
    fixture = _load_fixture(args.fixture)
    train_sequences = fixture.get("train_sequences", []) if isinstance(fixture, dict) else []
    if not isinstance(train_sequences, list) or not train_sequences:
        train_sequences = _default_train_sequences()
    eval_scenarios = fixture.get("eval_scenarios", []) if isinstance(fixture, dict) else []
    if not isinstance(eval_scenarios, list) or not eval_scenarios:
        eval_scenarios = _default_eval_scenarios()

    schema_token_budget = max(0, int(getattr(args, "schema_budget", 0) or 0))
    runs = max(1, int(args.runs))
    baseline_runs: List[Dict[str, Any]] = []
    graph_runs: List[Dict[str, Any]] = []
    for _ in range(runs):
        baseline_registry = EnhancedToolRegistry(Config())
        baseline_runs.append(
            _evaluate_registry(
                baseline_registry,
                eval_scenarios,
                schema_token_budget=schema_token_budget,
            )
        )

        graph = _build_graph(train_sequences)
        graph_registry = EnhancedToolRegistry(Config(), capability_graph=graph)
        graph_runs.append(
            _evaluate_registry(
                graph_registry,
                eval_scenarios,
                schema_token_budget=schema_token_budget,
            )
        )

    def _mean_metric(payloads: List[Dict[str, Any]], key: str) -> float:
        values = [float(item.get(key, 0.0) or 0.0) for item in payloads]
        return statistics.mean(values) if values else 0.0

    baseline_summary = baseline_runs[-1] if baseline_runs else {}
    graph_summary = graph_runs[-1] if graph_runs else {}
    baseline_miss_rate = _mean_metric(baseline_runs, "missRate")
    graph_miss_rate = _mean_metric(graph_runs, "missRate")
    baseline_latency = _mean_metric(baseline_runs, "selectionLatencyMeanMs")
    graph_latency = _mean_metric(graph_runs, "selectionLatencyMeanMs")
    baseline_schema = _mean_metric(baseline_runs, "avgSchemaTokensPerPrompt")
    graph_schema = _mean_metric(graph_runs, "avgSchemaTokensPerPrompt")

    return {
        "runs": runs,
        "schemaTokenBudget": schema_token_budget,
        "baseline": baseline_summary,
        "graphGuided": graph_summary,
        "comparison": {
            "missRateBaseline": baseline_miss_rate,
            "missRateGraphGuided": graph_miss_rate,
            "missRateDelta": graph_miss_rate - baseline_miss_rate,
            "selectionLatencyMeanMsBaseline": baseline_latency,
            "selectionLatencyMeanMsGraphGuided": graph_latency,
            "selectionLatencyMeanMsDelta": graph_latency - baseline_latency,
            "avgSchemaTokensPerPromptBaseline": baseline_schema,
            "avgSchemaTokensPerPromptGraphGuided": graph_schema,
            "avgSchemaTokensPerPromptDelta": graph_schema - baseline_schema,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/tool_capability_graph_profile.py")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--schema-budget", type=int, default=0)
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    payload = _run(args)
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
