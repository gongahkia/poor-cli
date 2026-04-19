#!/usr/bin/env python3
"""Context snapshot memoization hit-rate profile."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from poor_cli.context_assembly import ContextAssemblyOrchestrator

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "workloads.json"


@dataclass
class _ProviderCaps:
    max_context_tokens: int = 0


class _ProviderStub:
    def get_history(self):
        return []

    def get_capabilities(self):
        return _ProviderCaps()


class _CoreStub:
    def __init__(self) -> None:
        self.provider = _ProviderStub()
        self.config = type(
            "Cfg",
            (),
            {
                "model": type("ModelCfg", (), {"provider": "openai", "model_name": "gpt-5"})(),
                "history": type("HistCfg", (), {"max_token_limit": 200_000})(),
            },
        )()
        self._context_compressor = None
        self._tiered_compactor = None
        self._block_cache = None
        self._system_instruction = "system"
        self._system_context_hash = "hash"
        self._active_tool_groups = tuple()
        self._active_tool_names = set()
        self._active_tool_declarations = []
        self._context_dropped_files = set()

    def _instruction_snapshot_hash(self) -> str:
        return ""


def _load_fixture(path: str) -> Dict[str, Any]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.exists():
        return {}
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    scoped = payload.get("context_snapshot_memo_profile", {})
    return scoped if isinstance(scoped, dict) else {}


def _prompt_for_turn(
    idx: int,
    mode: str,
    run_len: int,
    *,
    fixture: Dict[str, Any],
    bursty_offset: int,
) -> str:
    stable_prompt = str(fixture.get("stable_prompt", "profile context memo behavior") or "profile context memo behavior")
    alternating_prompts = fixture.get("alternating_prompts", ["alpha prompt", "beta prompt"])
    if not isinstance(alternating_prompts, list) or not alternating_prompts:
        alternating_prompts = ["alpha prompt", "beta prompt"]
    alternating_prompts = [str(item) for item in alternating_prompts if str(item).strip()]
    if not alternating_prompts:
        alternating_prompts = ["alpha prompt", "beta prompt"]
    bursty_prompts = fixture.get("bursty_prompts", [])
    if not isinstance(bursty_prompts, list) or not bursty_prompts:
        bursty_prompts = ["run-bucket-a", "run-bucket-b", "run-bucket-c"]
    bursty_prompts = [str(item) for item in bursty_prompts if str(item).strip()]
    if not bursty_prompts:
        bursty_prompts = ["run-bucket-a", "run-bucket-b", "run-bucket-c"]
    if mode == "stable":
        return stable_prompt
    if mode == "alternating":
        return alternating_prompts[idx % len(alternating_prompts)]
    bucket = idx // max(1, run_len)
    return bursty_prompts[(bucket + bursty_offset) % len(bursty_prompts)]


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    fixture = _load_fixture(args.fixture)
    rng = random.Random(int(args.seed))
    bursty_prompts = fixture.get("bursty_prompts", []) if isinstance(fixture, dict) else []
    bursty_len = len(bursty_prompts) if isinstance(bursty_prompts, list) and bursty_prompts else 4
    bursty_offset = rng.randrange(max(1, bursty_len))
    core = _CoreStub()
    orchestrator = ContextAssemblyOrchestrator(core)
    assemble_calls = 0

    async def _fake_assemble_user_message(request):
        nonlocal assemble_calls
        assemble_calls += 1
        return f"User request: {request.prompt}", None, [], "rules"

    orchestrator._assemble_user_message = _fake_assemble_user_message  # type: ignore[assignment]
    orchestrator._tool_schemas = lambda: []  # type: ignore[assignment]
    orchestrator._history = lambda: []  # type: ignore[assignment]
    orchestrator._context_files = lambda _context_result: tuple()  # type: ignore[assignment]
    orchestrator._snapshot_key = lambda **_kwargs: "snapshot-key"  # type: ignore[assignment]
    orchestrator._token_breakdown = lambda **_kwargs: {  # type: ignore[assignment]
        "system": 1,
        "rules": 1,
        "files": 0,
        "history": 0,
        "tools": 0,
        "messages": 1,
        "total": 3,
    }

    latencies: List[float] = []
    turns = max(1, int(args.turns))
    for idx in range(turns):
        prompt = _prompt_for_turn(
            idx,
            args.mode,
            args.run_len,
            fixture=fixture,
            bursty_offset=bursty_offset,
        )
        started = time.perf_counter()
        await orchestrator.assemble(prompt=prompt, activate_tools=False)
        latencies.append((time.perf_counter() - started) * 1000.0)

    misses = assemble_calls
    hits = max(0, turns - misses)
    return {
        "seed": int(args.seed),
        "mode": str(args.mode),
        "turns": int(turns),
        "run_len": int(args.run_len),
        "memo_hits": int(hits),
        "memo_misses": int(misses),
        "memo_hit_rate": (float(hits) / float(turns)) if turns else 0.0,
        "latency_mean_ms": statistics.mean(latencies) if latencies else 0.0,
        "latency_p50_ms": statistics.median(latencies) if latencies else 0.0,
        "latency_p95_ms": sorted(latencies)[max(0, int(0.95 * (len(latencies) - 1)))] if latencies else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/context_snapshot_memo_profile.py")
    parser.add_argument("--turns", type=int, default=300)
    parser.add_argument("--mode", choices=("stable", "alternating", "bursty"), default="bursty")
    parser.add_argument("--run-len", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    payload = asyncio.run(_run(args))
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
