#!/usr/bin/env python3
"""Offline gate for context substrate, LOD memory, and egress controls."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poor_cli.context_substrate import append_jsonl_record, init_context, render_routed_context  # noqa: E402
from poor_cli.memory import MemoryEntry, MemoryManager  # noqa: E402
from poor_cli.memory_lod import search_lod  # noqa: E402
from poor_cli.tools_async import ToolRegistryAsync  # noqa: E402


def _check_context(root: Path) -> Dict[str, Any]:
    init_context(root)
    append_jsonl_record("decisions.jsonl", {"decision": "use append-only context"}, repo_root=root)
    rendered = render_routed_context("why did we choose the architecture?", repo_root=root)
    ok = "use append-only context" in rendered and "Context Map" in rendered
    return {"name": "context_routing", "ok": ok, "bytes": len(rendered.encode("utf-8"))}


async def _check_memory(root: Path) -> Dict[str, Any]:
    mgr = MemoryManager(root / ".poor-cli")
    mgr.save(MemoryEntry(name="decision", description="append-only JSONL", type="project", content="append-only JSONL stores decisions safely"))
    results = await search_lod(mgr, "JSONL decisions", max_results=5, alpha_profile="semantic")
    ok = bool(results and results[0].entry.name == "decision" and results[0].tier in {"full", "summary", "headline"})
    return {"name": "lod_memory", "ok": ok, "resultCount": len(results)}


async def _check_egress(root: Path) -> Dict[str, Any]:
    (root / "a.txt").write_text("needle\n")
    (root / "b.txt").write_text("needle\n")
    registry = ToolRegistryAsync()
    result = await registry.grep_files("needle", path=str(root), result_mode="paths_only", max_results=10)
    ok = "tool_egress" in result and "matching files" in result
    return {"name": "egress_grep", "ok": ok, "bytes": len(result.encode("utf-8"))}


async def run_gate() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        checks.append(_check_context(root))
        checks.append(await _check_memory(root))
        checks.append(await _check_egress(root))
    return {
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = asyncio.run(run_gate())
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
