from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_linux_cuda_setup_script_is_executable_and_valid_shell() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "setup-linux-cuda.sh"

    result = subprocess.run(["bash", "-n", str(script)], cwd=root, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert os.access(script, os.X_OK)


def test_phase3_closeout_script_is_executable_and_valid_shell() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "phase3-closeout-linux-cuda.sh"

    result = subprocess.run(["bash", "-n", str(script)], cwd=root, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert os.access(script, os.X_OK)


def test_linux_cuda_setup_script_covers_local_engines() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "setup-linux-cuda.sh"
    text = script.read_text(encoding="utf-8")

    assert "vllm" in text
    assert "sglang[all]" in text
    assert "ollama" in text
    assert "Qwen/Qwen2.5-Coder-32B-Instruct" in text
    assert ".poor-cli/local-cuda.env" in text
    assert ".poor-cli/local-cuda-run.sh" in text
    assert "export POOR_CLI_PROVIDER" in text
    assert "export POOR_CLI_MODEL" in text
    assert "export POOR_CLI_LOCAL_VENV" in text
    assert "export POOR_CLI_LOCAL_BASE_URL" in text
    assert "nvidia-smi" in text
    assert "--enable-prefix-caching" in text
    assert "--prefix-caching-hash-algo" in text
    assert "--no-enable-prefix-caching" in text
    assert "--disable-radix-cache" in text
    assert "--kv-cache-dtype" in text
    assert "POOR_CLI_LOCAL_PREFIX_CACHE" in text


def test_phase3_closeout_script_runs_required_audits() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "phase3-closeout-linux-cuda.sh"
    text = script.read_text(encoding="utf-8")

    assert "scripts/setup-linux-cuda.sh --yes" in text
    assert "bench/phase3_readiness.py" in text
    assert "bench/swe_bench_lite/run.py" in text
    assert "--agent local" in text
    assert "bench/phase3_local_benchmark.py" in text
    assert "bench/phase3_demo.py" in text
    assert "bench/phase3_acceptance.py" in text
    assert "bench/pivot_remaining.py" in text
    assert "bench/phase3_closeout.py" in text
    assert "curl --fail" in text
    assert "--start-server" in text
    assert "nohup .poor-cli/local-cuda-run.sh" in text
    assert "phase3-closeout-server.pid" in text
    assert "wait_for_server" in text
    assert "openai_compatible_health_url" in text
    assert "--write-demo-evidence" in text
    assert "--demo-video-path" in text
    assert "--demo-internet-disabled" in text
    assert "--demo-local-gpu" in text
    assert "--demo-graph-tools-visible" in text
    assert "--demo-offline-replay-verified" in text
