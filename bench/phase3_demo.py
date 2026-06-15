from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_EVIDENCE = ROOT / "bench" / "results" / "phase3-demo.json"
TARGET_MODEL_MARKERS = ("qwen2.5-coder", "32b")
DEFAULT_NETWORK_PROBE_COMMAND = "curl --fail --silent --show-error --max-time 5 https://example.com"
DEFAULT_GPU_PROBE_COMMAND = "nvidia-smi --query-gpu=name --format=csv,noheader"
REQUIRED_COMMAND_FRAGMENTS = (
    "poor-cli run",
    "--agents local",
    "--graph",
    "poor-cli --offline",
    "replay",
    "--verify",
)


def demo_evidence_template(
    *,
    run_id: str,
    video_path: str,
    model: str,
    duration_seconds: int,
    internet_disabled: bool,
    local_gpu: bool,
    graph_tools_visible: bool,
    offline_replay_verified: bool,
    store_dir: str = "",
    network_probe_command: str = "",
    network_probe_exit_code: int | None = None,
    gpu_probe_command: str = "",
    gpu_probe_exit_code: int | None = None,
    gpu_probe_output: str = "",
) -> dict[str, Any]:
    replay_command = f"poor-cli --offline replay {run_id or '<run_id>'} --verify"
    if store_dir:
        replay_command = f"poor-cli --offline --store-dir {shlex.quote(store_dir)} replay {run_id or '<run_id>'} --verify"
    return {
        "duration_seconds": duration_seconds,
        "model": model,
        "internet_disabled": internet_disabled,
        "local_gpu": local_gpu,
        "graph_tools_visible": graph_tools_visible,
        "offline_replay_verified": offline_replay_verified,
        "run_id": run_id,
        "store_dir": store_dir,
        "video_path": video_path,
        "network_probe": {
            "command": network_probe_command,
            "exit_code": network_probe_exit_code,
        },
        "gpu_probe": {
            "command": gpu_probe_command,
            "exit_code": gpu_probe_exit_code,
            "output": gpu_probe_output,
        },
        "commands": [
            'poor-cli run "fix a real bug using graph tools" --graph --agents local --yes',
            replay_command,
        ],
    }


def demo_plan_payload() -> dict[str, Any]:
    return {
        "schema_version": "poor-cli-phase3-demo-plan-v1",
        "target": {
            "duration_seconds_min": 45,
            "duration_seconds_max": 75,
            "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "model_markers": list(TARGET_MODEL_MARKERS),
            "requires_linux_cuda": True,
            "requires_internet_disabled": True,
            "requires_graph_tools_visible": True,
            "requires_offline_replay_verified": True,
            "requires_network_disabled_probe": True,
            "requires_gpu_probe": True,
        },
        "commands": {
            "setup": "scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct",
            "launch_server": ".poor-cli/local-cuda-run.sh",
            "readiness": "uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json",
            "run_demo": (
                "set -a; source .poor-cli/local-cuda.env; set +a; "
                'poor-cli run "fix a real bug using graph tools" --graph --agents local --yes'
            ),
            "replay": "poor-cli --offline --store-dir <poor_cli_store_dir> replay <poor_cli_run_id> --verify",
            "write_evidence": (
                "uv run --locked python bench/phase3_demo.py --write-template bench/results/phase3-demo.json "
                "--run-id <poor_cli_run_id> --store-dir <poor_cli_store_dir> "
                "--video-path bench/results/phase3-demo.mp4 --duration-seconds 60 "
                "--internet-disabled --network-probe-exit-code <nonzero> --local-gpu "
                "--gpu-probe-exit-code 0 --gpu-probe-output <nvidia-smi-gpu-name> "
                "--graph-tools-visible --offline-replay-verified"
            ),
            "verify": "uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json",
        },
    }


def validate_demo_evidence(path: Path = DEMO_EVIDENCE) -> dict[str, Any]:
    payload = _json_file(path)
    video_path = _resolve_video_path(path, str(payload.get("video_path") or ""))
    commands = payload.get("commands", []) if isinstance(payload.get("commands"), list) else []
    command_transcript = "\n".join(str(item) for item in commands)
    missing_fragments = [fragment for fragment in REQUIRED_COMMAND_FRAGMENTS if fragment not in command_transcript]
    duration = int(payload.get("duration_seconds") or 0)
    model = str(payload.get("model") or "")
    run_id = str(payload.get("run_id") or "")
    store_dir = str(payload.get("store_dir") or "")
    network_probe = _dict_payload(payload.get("network_probe"))
    gpu_probe = _dict_payload(payload.get("gpu_probe"))
    errors = []
    if not 45 <= duration <= 75:
        errors.append("duration_seconds must be between 45 and 75")
    if not all(marker in model.lower() for marker in TARGET_MODEL_MARKERS):
        errors.append("model must be qwen2.5-coder-32b")
    for field in ("internet_disabled", "local_gpu", "graph_tools_visible", "offline_replay_verified"):
        if not bool(payload.get(field)):
            errors.append(f"{field} must be true")
    if bool(payload.get("internet_disabled")) and not _network_probe_proves_disabled(network_probe):
        errors.append("network_probe must show internet request failed")
    if bool(payload.get("local_gpu")) and not _gpu_probe_proves_local_gpu(gpu_probe):
        errors.append("gpu_probe must show nvidia-smi detected a GPU")
    if not run_id:
        errors.append("run_id is required")
    elif not _commands_replay_run_id(commands, run_id):
        errors.append("commands must replay the recorded run_id offline")
    if store_dir and not _commands_replay_store_dir(commands, run_id, store_dir):
        errors.append("commands must replay from the recorded store_dir")
    if missing_fragments:
        errors.append("commands must show local graph run and offline replay verification")
    if not video_path.is_file():
        errors.append("video_path must exist")
    elif video_path.stat().st_size <= 0:
        errors.append("video_path must be non-empty")
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
        "run_id": run_id,
        "store_dir": store_dir,
        "video_path": payload.get("video_path", ""),
        "network_probe": network_probe,
        "gpu_probe": gpu_probe,
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


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _network_probe_proves_disabled(probe: dict[str, Any]) -> bool:
    command = str(probe.get("command") or "")
    exit_code = _int_value(probe.get("exit_code"))
    return exit_code is not None and exit_code != 0 and "curl" in command and "http" in command


def _gpu_probe_proves_local_gpu(probe: dict[str, Any]) -> bool:
    command = str(probe.get("command") or "")
    output = str(probe.get("output") or "")
    exit_code = _int_value(probe.get("exit_code"))
    return exit_code == 0 and "nvidia-smi" in command and bool([line for line in output.splitlines() if line.strip()])


def _resolve_video_path(evidence_path: Path, raw_path: str) -> Path:
    if not raw_path:
        return ROOT / ""
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    root_candidate = ROOT / path
    return root_candidate if root_candidate.is_file() else evidence_path.parent / path


def _commands_replay_run_id(commands: list[Any], run_id: str) -> bool:
    for command in commands:
        text = str(command)
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        for index, part in enumerate(parts[:-1]):
            if part == "replay" and parts[index + 1] == run_id and "--offline" in parts and "--verify" in parts:
                return True
    return False


def _commands_replay_store_dir(commands: list[Any], run_id: str, store_dir: str) -> bool:
    for command in commands:
        text = str(command)
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        store_indexes = [idx for idx, part in enumerate(parts[:-1]) if part == "--store-dir"]
        for index, part in enumerate(parts[:-1]):
            if (
                part == "replay"
                and parts[index + 1] == run_id
                and "--offline" in parts
                and "--verify" in parts
                and any(parts[store_index + 1] == store_dir for store_index in store_indexes)
            ):
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/phase3_demo.py")
    parser.add_argument("--evidence", type=Path, default=DEMO_EVIDENCE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-template", type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--store-dir", default="")
    parser.add_argument("--video-path", default="")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-32B-Instruct")
    parser.add_argument("--internet-disabled", action="store_true")
    parser.add_argument("--network-probe-command", default=DEFAULT_NETWORK_PROBE_COMMAND)
    parser.add_argument("--network-probe-exit-code", type=int)
    parser.add_argument("--local-gpu", action="store_true")
    parser.add_argument("--gpu-probe-command", default=DEFAULT_GPU_PROBE_COMMAND)
    parser.add_argument("--gpu-probe-exit-code", type=int)
    parser.add_argument("--gpu-probe-output", default="")
    parser.add_argument("--graph-tools-visible", action="store_true")
    parser.add_argument("--offline-replay-verified", action="store_true")
    args = parser.parse_args(argv)
    if args.write_template:
        payload = demo_evidence_template(
            run_id=str(args.run_id),
            video_path=str(args.video_path),
            model=str(args.model),
            duration_seconds=int(args.duration_seconds),
            internet_disabled=bool(args.internet_disabled),
            local_gpu=bool(args.local_gpu),
            graph_tools_visible=bool(args.graph_tools_visible),
            offline_replay_verified=bool(args.offline_replay_verified),
            store_dir=str(args.store_dir),
            network_probe_command=str(args.network_probe_command),
            network_probe_exit_code=args.network_probe_exit_code,
            gpu_probe_command=str(args.gpu_probe_command),
            gpu_probe_exit_code=args.gpu_probe_exit_code,
            gpu_probe_output=str(args.gpu_probe_output),
        )
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        args.write_template.parent.mkdir(parents=True, exist_ok=True)
        args.write_template.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0
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
