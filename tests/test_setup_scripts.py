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


def test_linux_cuda_setup_script_covers_local_engines() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "setup-linux-cuda.sh"
    text = script.read_text(encoding="utf-8")

    assert "vllm" in text
    assert "sglang[all]" in text
    assert "ollama" in text
    assert "Qwen/Qwen2.5-Coder-32B-Instruct" in text
    assert ".poor-cli/local-cuda.env" in text
    assert ".poor-cli/local-cuda-run.sh" in text
    assert "nvidia-smi" in text
