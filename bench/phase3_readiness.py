from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup-linux-cuda.sh"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Phase 3 local-first readiness without starting local model servers.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = readiness_payload()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["ready"] else 1


def readiness_payload() -> dict[str, Any]:
    checks = {
        "setup_script": _setup_script(),
        "provider_adapters": _provider_adapters(),
        "linux_cuda_host": _linux_cuda_host(),
        "engine_python_deps": _python_deps("vllm", "sglang"),
        "ollama_binary": _binary("ollama"),
    }
    return {
        "schema_version": "poor-cli-phase3-readiness-v1",
        "ready": all(check["ready"] for check in checks.values()),
        "checks": checks,
        "remaining": [name for name, check in checks.items() if not check["ready"]],
    }


def _setup_script() -> dict[str, Any]:
    if not SETUP_SCRIPT.is_file():
        return {"ready": False, "path": str(SETUP_SCRIPT.relative_to(ROOT)), "reason": "missing setup script"}
    syntax = subprocess.run(["bash", "-n", str(SETUP_SCRIPT)], text=True, capture_output=True, timeout=10, check=False)
    executable = bool(SETUP_SCRIPT.stat().st_mode & 0o111)
    return {
        "ready": syntax.returncode == 0 and executable,
        "path": str(SETUP_SCRIPT.relative_to(ROOT)),
        "executable": executable,
        "bash_syntax": syntax.returncode == 0,
    }


def _provider_adapters() -> dict[str, Any]:
    try:
        from poor_cli.provider_adapters import OllamaProvider, SGLangProvider, VLLMProvider
    except Exception as exc:
        return {"ready": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ready": True,
        "providers": sorted([OllamaProvider.name, SGLangProvider.name, VLLMProvider.name]),
    }


def _linux_cuda_host() -> dict[str, Any]:
    system = platform.system()
    nvidia_smi = shutil.which("nvidia-smi")
    gpu_query = ""
    if nvidia_smi:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        gpu_query = result.stdout.strip()
    return {
        "ready": system == "Linux" and bool(nvidia_smi),
        "system": system,
        "nvidia_smi": bool(nvidia_smi),
        "gpu_names": [line for line in gpu_query.splitlines() if line.strip()],
    }


def _python_deps(*names: str) -> dict[str, Any]:
    modules = {name: importlib.util.find_spec(name) is not None for name in names}
    return {"ready": all(modules.values()), "modules": modules, "install": "scripts/setup-linux-cuda.sh --yes --engine vllm"}


def _binary(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"ready": bool(path), "available": bool(path), "path": path or ""}


if __name__ == "__main__":
    raise SystemExit(main())
