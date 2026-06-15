from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from poor_cli.planner import SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOC_CAP = 7600
ANTHROPIC_FIXTURE_RESULT = ROOT / "bench" / "results" / "local-fixture-bugs-claude.json"
SWE_10_SUMMARY = ROOT / "bench" / "swe_bench_lite" / "results" / "swe10-claude-20260614T105615Z" / "summary.json"
CLI_TESTS = ROOT / "tests" / "test_cli.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Phase 1 acceptance evidence from checked-in results.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = acceptance_payload()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["accepted"] else 1


def acceptance_payload() -> dict[str, Any]:
    checks = {
        "anthropic_fixture_bugs": _anthropic_fixture_bugs(),
        "offline_replay_determinism": _offline_replay_determinism(),
        "source_loc": _source_loc(),
        "system_prompt_budget": _system_prompt_budget(),
        "swe_lite_10": _swe_lite_10(),
    }
    return {
        "schema_version": "poor-cli-phase1-acceptance-v1",
        "accepted": all(check["accepted"] for check in checks.values()),
        "checks": checks,
        "remaining": [name for name, check in checks.items() if not check["accepted"]],
    }


def _anthropic_fixture_bugs() -> dict[str, Any]:
    payload = _json_file(ANTHROPIC_FIXTURE_RESULT)
    accepted = (
        payload.get("agent") == "claude"
        and payload.get("fixture_count") == 3
        and payload.get("completed_count") == 3
        and payload.get("tests_passed_count") == 3
        and payload.get("replay_verified_count") == 3
    )
    return {
        "accepted": accepted,
        "evidence": str(ANTHROPIC_FIXTURE_RESULT.relative_to(ROOT)),
        "fixture_count": payload.get("fixture_count"),
        "completed_count": payload.get("completed_count"),
        "tests_passed_count": payload.get("tests_passed_count"),
        "replay_verified_count": payload.get("replay_verified_count"),
    }


def _offline_replay_determinism() -> dict[str, Any]:
    text = CLI_TESTS.read_text(encoding="utf-8") if CLI_TESTS.is_file() else ""
    required_fragments = [
        "before_verify == after_verify",
        "first_verify == second_verify",
        '"--offline"',
        '"--verify"',
        '["verification"]["verified"] is True',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    return {
        "accepted": not missing,
        "evidence": "tests/test_cli.py::test_cli_main_in_process_run_inspect_replay",
        "missing_fragments": missing,
    }


def _source_loc() -> dict[str, Any]:
    files = sorted(path for path in (ROOT / "src" / "poor_cli").rglob("*.py") if "__pycache__" not in path.parts)
    counts = {str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines()) for path in files}
    total = sum(counts.values())
    over_file_limit = {path: count for path, count in counts.items() if count > 600}
    return {
        "accepted": total <= SOURCE_LOC_CAP and not over_file_limit,
        "total": total,
        "max_total": SOURCE_LOC_CAP,
        "file_count": len(files),
        "over_file_limit": over_file_limit,
        "evidence": "bench/loc_gate.py",
    }


def _system_prompt_budget() -> dict[str, Any]:
    byte_count = len(SYSTEM_PROMPT.encode("utf-8"))
    return {
        "accepted": byte_count <= 1000,
        "bytes": byte_count,
        "max_bytes": 1000,
        "evidence": "tests/test_gates.py::test_system_prompt_under_1000_token_ceiling",
    }


def _swe_lite_10() -> dict[str, Any]:
    payload = _json_file(SWE_10_SUMMARY)
    official = payload.get("official_evaluation") if isinstance(payload.get("official_evaluation"), dict) else {}
    results = official.get("results") if isinstance(official.get("results"), dict) else {}
    resolved = int(results.get("resolved_instances") or 0)
    total = int(results.get("total_instances") or payload.get("task_count") or 0)
    pass_rate = (resolved / total) if total else 0.0
    return {
        "accepted": total == 10 and pass_rate >= 0.30 and int(results.get("error_instances") or 0) == 0,
        "evidence": str(SWE_10_SUMMARY.relative_to(ROOT)),
        "model": payload.get("model"),
        "total_instances": total,
        "resolved_instances": resolved,
        "pass_rate": pass_rate,
        "minimum_pass_rate": 0.30,
        "unresolved_ids": results.get("unresolved_ids") or [],
    }


def _json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
