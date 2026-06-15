from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from bench.phase3_acceptance import acceptance_payload
    from bench.pivot_remaining import remaining_payload
except ModuleNotFoundError:
    from phase3_acceptance import acceptance_payload
    from pivot_remaining import remaining_payload


def closeout_payload() -> dict[str, Any]:
    acceptance = acceptance_payload()
    pivot = remaining_payload()
    return {
        "schema_version": "poor-cli-phase3-closeout-v1",
        "accepted": bool(acceptance["accepted"]) and bool(pivot["complete"]),
        "checks": {
            "phase3_acceptance": {
                "accepted": bool(acceptance["accepted"]),
                "remaining": acceptance["remaining"],
                "evidence": "bench/results/phase3-acceptance.json",
            },
            "pivot_remaining": {
                "accepted": bool(pivot["complete"]),
                "remaining": pivot["remaining"],
                "evidence": "bench/results/pivot-remaining.json",
            },
        },
        "remaining": sorted(set(acceptance["remaining"]) | set(pivot["remaining"])),
        "target_host_commands": target_host_commands(),
    }


def target_host_commands() -> dict[str, str]:
    run_id = "swe10-local-YYYYMMDDTHHMMSSZ"
    return {
        "run_all": (
            "scripts/phase3-closeout-linux-cuda.sh --yes --start-server --run-id swe10-local-YYYYMMDDTHHMMSSZ "
            "--stop-server-on-exit "
            "--write-demo-evidence --demo-video-path bench/results/phase3-demo.mp4 --demo-duration-seconds 60 "
            "--demo-internet-disabled --demo-local-gpu --demo-graph-tools-visible --demo-offline-replay-verified"
        ),
        "setup": "scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct",
        "setup_quantized": (
            "scripts/setup-linux-cuda.sh --yes --engine vllm "
            "--model Qwen/Qwen2.5-Coder-32B-Instruct-AWQ "
            "--served-model Qwen/Qwen2.5-Coder-32B-Instruct "
            "--quantization awq --max-model-len 8192 --gpu-memory-utilization 0.90"
        ),
        "launch_server": ".poor-cli/local-cuda-run.sh",
        "readiness": "uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json",
        "generate_local_swe": (
            "set -a; source .poor-cli/local-cuda.env; set +a; "
            "uv run --locked --extra bench python bench/swe_bench_lite/run.py "
            '--graph --agent local --provider "$POOR_CLI_PROVIDER" --model "$POOR_CLI_MODEL" '
            f'--local-base-url "$POOR_CLI_LOCAL_BASE_URL" --no-evaluate --confirm-cost --timeout-seconds 1200 --run-id {run_id}'
        ),
        "evaluate_local_swe": (
            "uv run --locked --extra bench python bench/swe_bench_lite/run.py "
            f"--evaluate-existing-run {run_id} --confirm-cost --eval-max-workers 1 --eval-namespace none"
        ),
        "verify_local_swe": (
            f"uv run --locked python bench/phase3_local_benchmark.py --summary bench/swe_bench_lite/results/{run_id}/summary.json"
        ),
        "write_demo_evidence": (
            "uv run --locked python bench/phase3_demo.py --write-template bench/results/phase3-demo.json "
            "--run-id <poor_cli_run_id> --store-dir <poor_cli_store_dir> "
            "--video-path bench/results/phase3-demo.mp4 --duration-seconds 60 "
            "--source-model <loaded-model-id> --served-model Qwen/Qwen2.5-Coder-32B-Instruct "
            "--quantization <none|awq|gptq> "
            "--internet-disabled --network-probe-exit-code <nonzero> --local-gpu "
            "--gpu-probe-exit-code 0 --gpu-probe-output <nvidia-smi-gpu-name> "
            "--graph-tools-visible --offline-replay-verified"
        ),
        "verify_demo": "uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json",
        "refresh_acceptance": "uv run --locked python bench/phase3_acceptance.py --output bench/results/phase3-acceptance.json",
        "refresh_pivot": "uv run --locked python bench/pivot_remaining.py --output bench/results/pivot-remaining.json",
        "closeout": "uv run --locked python bench/phase3_closeout.py --output bench/results/phase3-closeout.json",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/phase3_closeout.py")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = closeout_payload()
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
