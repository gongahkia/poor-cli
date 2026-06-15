from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from poor_cli.repo_graph import RepoGraph

SCHEMA_VERSION = "poor-cli-graph-vs-grep-v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare grep-mode and graph-mode context for a synthetic Python repo.")
    parser.add_argument("--modules", type=int, default=500)
    parser.add_argument("--filler-lines", type=int, default=96)
    parser.add_argument("--target-index", type=int)
    parser.add_argument("--min-loc", type=int, default=50_000)
    parser.add_argument("--min-reduction", type=float, default=0.30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = graph_vs_grep_payload(
        modules=args.modules,
        filler_lines=args.filler_lines,
        target_index=args.target_index,
        min_loc=args.min_loc,
        min_reduction=args.min_reduction,
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["accepted"] else 1


def graph_vs_grep_payload(
    *,
    modules: int = 500,
    filler_lines: int = 96,
    target_index: int | None = None,
    min_loc: int = 50_000,
    min_reduction: float = 0.30,
) -> dict[str, Any]:
    if modules < 3:
        raise ValueError("modules must be at least 3")
    target = target_index if target_index is not None else modules - 2
    if target < 1 or target >= modules:
        raise ValueError("target_index must be between 1 and modules - 1")
    target_symbol = f"function_{target:04d}"
    expected = {"definition_path": f"module_{target:04d}.py", "caller_paths": [f"module_{target - 1:04d}.py"]}
    with tempfile.TemporaryDirectory(prefix="poor-cli-graph-bench-") as temp:
        root = Path(temp) / "repo"
        root.mkdir()
        line_count = _write_fixture(root, modules, filler_lines)
        grep = _grep_mode(root, target_symbol, expected)
        graph = _graph_mode(root, target_symbol, expected)
    reduction = 1.0 - (graph["input_tokens"] / grep["input_tokens"])
    return {
        "schema_version": SCHEMA_VERSION,
        "accepted": (line_count >= min_loc and grep["correct"] and graph["correct"] and reduction >= min_reduction),
        "fixture": {"modules": modules, "filler_lines_per_module": filler_lines, "line_count": line_count},
        "task": {
            "objective": "find the target function definition and its direct callers",
            "target_symbol": target_symbol,
            "expected": expected,
        },
        "modes": {"grep": grep, "graph": graph},
        "token_reduction": reduction,
        "min_reduction": min_reduction,
        "min_loc": min_loc,
    }


def _write_fixture(root: Path, modules: int, filler_lines: int) -> int:
    line_count = 0
    for index in range(modules):
        lines = []
        if index + 1 < modules:
            lines.append(f"from module_{index + 1:04d} import function_{index + 1:04d}")
        else:
            lines.append("TERMINAL_VALUE = 'end'")
        lines.extend(["", f"def function_{index:04d}() -> str:"])
        if index + 1 < modules:
            lines.append(f"    return function_{index + 1:04d}()")
        else:
            lines.append("    return 'end'")
        for filler in range(filler_lines):
            lines.append(f"FILLER_{filler:03d}_{index:04d} = {filler}")
        text = "\n".join(lines) + "\n"
        line_count += len(text.splitlines())
        (root / f"module_{index:04d}.py").write_text(text, encoding="utf-8")
    return line_count


def _grep_mode(root: Path, target_symbol: str, expected: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    context = []
    definition_path = None
    caller_paths = set()
    for path in sorted(root.rglob("*.py")):
        rel = str(path.relative_to(root))
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("def ") or target_symbol in stripped:
                context.append({"path": rel, "line": line_number, "text": stripped})
            if stripped.startswith(f"def {target_symbol}("):
                definition_path = rel
            if f"{target_symbol}(" in stripped and not stripped.startswith("def "):
                caller_paths.add(rel)
    output = {"definition_path": definition_path, "caller_paths": sorted(caller_paths)}
    tokens = _token_estimate(context)
    return {
        "strategy": "grep import/function/call lines",
        "correct": output == expected,
        "recall_proxy": 1.0 if output == expected else 0.0,
        "output": output,
        "input_tokens": tokens,
        "token_count_proxy": tokens,
        "context_lines": len(context),
        "latency_seconds": time.perf_counter() - started,
    }


def _graph_mode(root: Path, target_symbol: str, expected: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    graph = RepoGraph(root).build_index()
    definition = graph.definition_of(target_symbol)
    callers = graph.callers_of(target_symbol)
    output = {
        "definition_path": definition["path"] if definition else None,
        "caller_paths": sorted(str(item["path"]) for item in callers),
    }
    context = {"definition": definition, "callers": callers}
    tokens = _token_estimate(context)
    return {
        "strategy": "definition_of plus callers_of",
        "correct": output == expected,
        "recall_proxy": 1.0 if output == expected else 0.0,
        "output": output,
        "input_tokens": tokens,
        "token_count_proxy": tokens,
        "context_lines": len(callers) + (1 if definition else 0),
        "latency_seconds": time.perf_counter() - started,
    }


def _token_estimate(value: Any) -> int:
    return max(1, len(json.dumps(value, sort_keys=True, separators=(",", ":"))) // 4)


if __name__ == "__main__":
    raise SystemExit(main())
