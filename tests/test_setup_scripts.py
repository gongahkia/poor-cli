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
    assert "POOR_CLI_LOCAL_PYTHON" in text
    assert "--python" in text
    assert "--served-model" in text
    assert "--quantization" in text
    assert "--dtype" in text
    assert "--max-model-len" in text
    assert "--tensor-parallel-size" in text
    assert "--gpu-memory-utilization" in text
    assert ".poor-cli/local-cuda.env" in text
    assert ".poor-cli/local-cuda-run.sh" in text
    assert "export POOR_CLI_PROVIDER" in text
    assert "export POOR_CLI_MODEL" in text
    assert "export POOR_CLI_LOCAL_MODEL_SOURCE" in text
    assert "export POOR_CLI_LOCAL_SERVED_MODEL" in text
    assert "export POOR_CLI_LOCAL_QUANTIZATION" in text
    assert "export POOR_CLI_LOCAL_PYTHON" in text
    assert "export POOR_CLI_LOCAL_VENV" in text
    assert "export POOR_CLI_LOCAL_BASE_URL" in text
    assert "nvidia-smi" in text
    assert "nvidia-smi --query-gpu=name --format=csv,noheader" in text
    assert "nvidia-smi did not return a GPU name" in text
    assert "--enable-prefix-caching" in text
    assert "--prefix-caching-hash-algo" in text
    assert "--no-enable-prefix-caching" in text
    assert "--disable-radix-cache" in text
    assert "--kv-cache-dtype" in text
    assert "--served-model-name" in text
    assert "--context-length" in text
    assert "--mem-fraction-static" in text
    assert "POOR_CLI_LOCAL_PREFIX_CACHE" in text
    assert "exec vllm serve" in text
    assert "exec python -m sglang.launch_server" in text
    assert "exec ollama serve" in text


def test_phase3_closeout_script_runs_required_audits() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "phase3-closeout-linux-cuda.sh"
    text = script.read_text(encoding="utf-8")

    assert "scripts/setup-linux-cuda.sh" in text
    assert "SETUP_ARGS=(--yes" in text
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
    assert "--stop-server-on-exit" in text
    assert "stop_started_server" in text
    assert "nohup .poor-cli/local-cuda-run.sh" in text
    assert "phase3-closeout-server.pid" in text
    assert "wait_for_server" in text
    assert "openai_compatible_health_url" in text
    assert "--write-demo-evidence" in text
    assert "--demo-video-path" in text
    assert "--demo-run-id" in text
    assert "--demo-store-dir" in text
    assert "--served-model" in text
    assert "--quantization" in text
    assert "--max-model-len" in text
    assert "--demo-internet-disabled" in text
    assert "--demo-local-gpu" in text
    assert "--demo-graph-tools-visible" in text
    assert "--demo-offline-replay-verified" in text
    assert "derive_demo_replay_evidence" in text
    assert "capture_network_disabled_probe" in text
    assert "capture_gpu_probe" in text
    assert "--network-probe-exit-code" in text
    assert "--gpu-probe-output" in text
    assert "poor_cli_run_id" in text
    assert "poor_cli_store_dir" in text
    assert '--store-dir "$DEMO_STORE_DIR"' in text
