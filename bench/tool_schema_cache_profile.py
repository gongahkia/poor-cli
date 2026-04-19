#!/usr/bin/env python3
"""Tool-schema materialization cache hit-rate profile."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from poor_cli.config import Config
from poor_cli.core import PoorCLICore

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "workloads.json"


class _CountingRegistry:
    def __init__(self, base_tools: int = 12) -> None:
        self.calls = 0
        self.tools = {f"tool_{idx}": object() for idx in range(base_tools)}

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        self.calls += 1
        return [
            {
                "name": name,
                "description": "bench",
                "parameters": {"type": "OBJECT", "properties": {}, "required": []},
            }
            for name in sorted(self.tools)
        ]


def _load_fixture(path: str) -> Dict[str, Any]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.exists():
        return {}
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    scoped = payload.get("tool_schema_cache_profile", {})
    return scoped if isinstance(scoped, dict) else {}


def _run(args: argparse.Namespace) -> Dict[str, Any]:
    fixture = _load_fixture(args.fixture)
    rng = random.Random(int(args.seed))
    model_names = fixture.get("model_names", []) if isinstance(fixture, dict) else []
    if not isinstance(model_names, list) or not model_names:
        model_names = ["bench-model-a", "bench-model-b", "bench-model-c", "bench-model-d"]
    model_names = [str(item) for item in model_names if str(item).strip()]
    if not model_names:
        model_names = ["bench-model-a", "bench-model-b", "bench-model-c", "bench-model-d"]
    tool_prefix = str(fixture.get("dynamic_tool_prefix", "dynamic_tool_")) if isinstance(fixture, dict) else "dynamic_tool_"
    model_cursor = rng.randrange(len(model_names))
    core = object.__new__(PoorCLICore)
    core.config = Config()
    core.tool_registry = _CountingRegistry(base_tools=max(2, int(args.base_tools)))
    core._mcp_manager = None
    core._tool_schema_materialization_cache = {}

    turns = max(1, int(args.turns))
    model_switch_every = max(0, int(args.model_switch_every))
    tool_mutate_every = max(0, int(args.tool_mutate_every))
    latencies: List[float] = []
    declarations_count = 0
    for idx in range(turns):
        if model_switch_every and idx > 0 and idx % model_switch_every == 0:
            model_cursor = (model_cursor + 1) % len(model_names)
            core.config.model.model_name = model_names[model_cursor]
        if tool_mutate_every and idx > 0 and idx % tool_mutate_every == 0:
            key = f"{tool_prefix}{idx}"
            if key in core.tool_registry.tools:
                core.tool_registry.tools.pop(key, None)
            else:
                core.tool_registry.tools[key] = object()
        started = time.perf_counter()
        declarations = core._tool_declarations_for_shipping()
        latencies.append((time.perf_counter() - started) * 1000.0)
        declarations_count = len(declarations)

    misses = int(core.tool_registry.calls)
    hits = max(0, turns - misses)
    return {
        "seed": int(args.seed),
        "turns": int(turns),
        "base_tools": int(args.base_tools),
        "model_switch_every": int(model_switch_every),
        "tool_mutate_every": int(tool_mutate_every),
        "declarations_per_turn": int(declarations_count),
        "materialization_calls": int(misses),
        "cache_hits": int(hits),
        "cache_hit_rate": (float(hits) / float(turns)) if turns else 0.0,
        "latency_mean_ms": statistics.mean(latencies) if latencies else 0.0,
        "latency_p50_ms": statistics.median(latencies) if latencies else 0.0,
        "latency_p95_ms": sorted(latencies)[max(0, int(0.95 * (len(latencies) - 1)))] if latencies else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/tool_schema_cache_profile.py")
    parser.add_argument("--turns", type=int, default=1000)
    parser.add_argument("--base-tools", type=int, default=12)
    parser.add_argument("--model-switch-every", type=int, default=0)
    parser.add_argument("--tool-mutate-every", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
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
