from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_EVIDENCE = ROOT / "bench" / "results" / "phase3-demo.json"
REQUIRED_COMMAND_FRAGMENTS = (
    "poor-cli run",
    "--agents local",
    "--graph",
    "poor-cli --offline",
    "replay",
    "--verify",
)


def demo_plan_payload() -> dict[str, Any]:
    return {
        "schema_version": "poor-cli-phase3-demo-plan-v1",
        "target": {
            "duration_seconds_min": 45,
            "duration_seconds_max": 75,
            "model_prefixes": ["qwen2.5-coder", "qwen/qwen2.5-coder"],
            "requires_linux_cuda": True,
            "requires_internet_disabled": True,
            "requires_graph_tools_visible": True,
            "requires_offline_replay_verified": True,
        },
        "commands": {
            "setup": "scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct",
            "launch_server": ".poor-cli/local-cuda-run.sh",
            "readiness": "uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json",
            "run_demo": (
                "set -a; source .poor-cli/local-cuda.env; set +a; "
                'poor-cli run "fix a real bug using graph tools" --graph --agents local --yes'
            ),
            "replay": "poor-cli --offline replay <run_id> --verify",
            "write_evidence": "write bench/results/phase3-demo.json with the schema documented by bench/phase3_demo.py",
            "verify": "uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json",
        },
    }


def validate_demo_evidence(path: Path = DEMO_EVIDENCE) -> dict[str, Any]:
    payload = _json_file(path)
    video_path = ROOT / str(payload.get("video_path") or "")
    command_transcript = "\n".join(str(item) for item in payload.get("commands", [])) if isinstance(payload.get("commands"), list) else ""
    missing_fragments = [fragment for fragment in REQUIRED_COMMAND_FRAGMENTS if fragment not in command_transcript]
    duration = int(payload.get("duration_seconds") or 0)
    model = str(payload.get("model") or "")
    errors = []
    if not 45 <= duration <= 75:
        errors.append("duration_seconds must be between 45 and 75")
    if not model.lower().startswith(("qwen2.5-coder", "qwen/qwen2.5-coder")):
        errors.append("model must be qwen2.5-coder or comparable qwen/qwen2.5-coder path")
    for field in ("internet_disabled", "local_gpu", "graph_tools_visible", "offline_replay_verified"):
        if not bool(payload.get(field)):
            errors.append(f"{field} must be true")
    if not str(payload.get("run_id") or ""):
        errors.append("run_id is required")
    if missing_fragments:
        errors.append("commands must show local graph run and offline replay verification")
    if not video_path.is_file():
        errors.append("video_path must exist")
    return {
        "accepted": not errors,
        "evidence": _display_path(path),
        "errors": errors,
        "duration_seconds": duration,
        "model": model,
        "internet_disabled": bool(payload.get("internet_disabled")),
        "local_gpu": bool(payload.get("local_gpu")),
        "graph_tools_visible": bool(payload.get("graph_tools_visible")),
        "offline_replay_verified": bool(payload.get("offline_replay_verified")),
        "run_id": payload.get("run_id", ""),
        "video_path": payload.get("video_path", ""),
        "missing_command_fragments": missing_fragments,
    }


def _json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/phase3_demo.py")
    parser.add_argument("--evidence", type=Path, default=DEMO_EVIDENCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = {
        "plan": demo_plan_payload(),
        "validation": validate_demo_evidence(args.evidence.resolve()),
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if payload["validation"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
