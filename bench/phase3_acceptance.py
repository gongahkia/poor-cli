from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from bench.phase3_local_benchmark import target_payload, validate_local_summary
except ModuleNotFoundError:
    from phase3_local_benchmark import target_payload, validate_local_summary

ROOT = Path(__file__).resolve().parents[1]
PHASE3_READINESS = ROOT / "bench" / "results" / "phase3-readiness.json"
PHASE3_DEMO = ROOT / "bench" / "results" / "phase3-demo.json"
CLI_TESTS = ROOT / "tests" / "test_cli.py"
AGENT_TESTS = ROOT / "tests" / "test_agents.py"
PROVIDER_TESTS = ROOT / "tests" / "test_provider_adapters.py"
PROVIDER_CACHE_TESTS = ROOT / "tests" / "test_providers.py"
PLANNER_TESTS = ROOT / "tests" / "test_planner.py"


def acceptance_payload() -> dict[str, Any]:
    checks = {
        "linux_cuda_readiness": _linux_cuda_readiness(),
        "local_swe_lite_10": _local_swe_lite_10(),
        "offline_graph_replay": _offline_graph_replay(),
        "offline_network_guards": _offline_network_guards(),
        "local_gpu_screencast": _local_gpu_screencast(),
    }
    return {
        "schema_version": "poor-cli-phase3-acceptance-v1",
        "accepted": all(check["accepted"] for check in checks.values()),
        "checks": checks,
        "remaining": [name for name, check in checks.items() if not check["accepted"]],
    }


def _linux_cuda_readiness() -> dict[str, Any]:
    payload = _json_file(PHASE3_READINESS)
    return {
        "accepted": bool(payload.get("ready")),
        "evidence": str(PHASE3_READINESS.relative_to(ROOT)),
        "remaining": payload.get("remaining", []),
    }


def _local_swe_lite_10() -> dict[str, Any]:
    target = target_payload()
    best = {
        "accepted": False,
        "evidence": "",
        "pass_rate": 0.0,
        "target_rate": target["target_rate"],
        "resolved_instances": 0,
        "total_instances": 0,
        "replay_verified_count": 0,
    }
    for summary_path in sorted((ROOT / "bench" / "swe_bench_lite" / "results").glob("*/summary.json")):
        validation = validate_local_summary(summary_path.resolve())
        if validation["provider"] not in {"ollama", "sglang", "vllm"} and validation["agent"] != "local":
            continue
        if validation["accepted"]:
            return validation
        if float(validation["pass_rate"]) > float(best["pass_rate"]):
            best = validation
    return best


def _offline_graph_replay() -> dict[str, Any]:
    text = CLI_TESTS.read_text(encoding="utf-8") if CLI_TESTS.is_file() else ""
    required_fragments = [
        "test_cli_run_graph_replays_offline",
        '"--graph"',
        '"--offline"',
        '"replay"',
        '"--verify"',
        '["verification"]["verified"] is True',
        '"graph_mode"] is True',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    return {
        "accepted": not missing,
        "evidence": "tests/test_cli.py::test_cli_run_graph_replays_offline",
        "missing_fragments": missing,
    }


def _offline_network_guards() -> dict[str, Any]:
    expected = {
        "tests/test_agents.py::test_offline_mode_blocks_network_backed_agents": AGENT_TESTS,
        "tests/test_provider_adapters.py::test_provider_adapters_block_offline_calls": PROVIDER_TESTS,
        "tests/test_providers.py::test_cached_replay_provider_blocks_live_call_when_offline": PROVIDER_CACHE_TESTS,
        "tests/test_planner.py::test_offline_planner_requires_custom_command": PLANNER_TESTS,
    }
    missing = [name for name, path in expected.items() if name.rsplit("::", 1)[1] not in _text(path)]
    return {
        "accepted": not missing,
        "evidence": sorted(expected),
        "missing": missing,
    }


def _local_gpu_screencast() -> dict[str, Any]:
    payload = _json_file(PHASE3_DEMO)
    video_path = ROOT / str(payload.get("video_path") or "")
    accepted = (
        45 <= int(payload.get("duration_seconds") or 0) <= 75
        and bool(payload.get("internet_disabled"))
        and bool(payload.get("local_gpu"))
        and str(payload.get("model") or "").lower().startswith(("qwen2.5-coder", "qwen/qwen2.5-coder"))
        and bool(payload.get("graph_tools_visible"))
        and bool(payload.get("offline_replay_verified"))
        and video_path.is_file()
    )
    return {
        "accepted": accepted,
        "evidence": str(PHASE3_DEMO.relative_to(ROOT)),
        "duration_seconds": payload.get("duration_seconds", 0),
        "model": payload.get("model", ""),
        "internet_disabled": bool(payload.get("internet_disabled")),
        "local_gpu": bool(payload.get("local_gpu")),
        "graph_tools_visible": bool(payload.get("graph_tools_visible")),
        "offline_replay_verified": bool(payload.get("offline_replay_verified")),
        "video_path": payload.get("video_path", ""),
    }


def _json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Phase 3 acceptance evidence from checked-in results.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = acceptance_payload()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
