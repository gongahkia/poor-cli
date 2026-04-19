#!/usr/bin/env python3
"""Context snapshot memoization hit-rate profile."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from poor_cli.context_assembly import ContextAssemblyOrchestrator


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


def _prompt_for_turn(idx: int, mode: str, run_len: int) -> str:
    if mode == "stable":
        return "profile context memo behavior"
    if mode == "alternating":
        return "alpha prompt" if idx % 2 == 0 else "beta prompt"
    bucket = idx // max(1, run_len)
    return f"run-bucket-{bucket}"


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
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
        prompt = _prompt_for_turn(idx, args.mode, args.run_len)
        started = time.perf_counter()
        await orchestrator.assemble(prompt=prompt, activate_tools=False)
        latencies.append((time.perf_counter() - started) * 1000.0)

    misses = assemble_calls
    hits = max(0, turns - misses)
    return {
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
