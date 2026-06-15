from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup-linux-cuda.sh"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
        "local_agent_path": _local_agent_path(),
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
    return {
        "ready": any(modules.values()),
        "modules": modules,
        "requirement": "one of vllm or sglang",
        "install": "scripts/setup-linux-cuda.sh --yes --engine vllm",
    }


def _binary(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"ready": bool(path), "available": bool(path), "path": path or ""}


def _local_agent_path() -> dict[str, Any]:
    old_values = {key: os.environ.get(key) for key in ("POOR_CLI_PROVIDER", "POOR_CLI_MODEL", "POOR_CLI_LOCAL_BASE_URL")}
    try:
        os.environ["POOR_CLI_PROVIDER"] = "vllm"
        os.environ["POOR_CLI_MODEL"] = "qwen"
        os.environ["POOR_CLI_LOCAL_BASE_URL"] = "http://localhost:8000"
        from poor_cli.agents import detect_agents

        local_agents = [agent for agent in detect_agents() if agent.name == "local"]
        agent_ready = bool(local_agents) and local_agents[0].provider == "vllm" and local_agents[0].default_model == "qwen"
    except Exception as exc:
        return {"ready": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    try:
        from bench.swe_bench_lite import run as swe_run

        args = swe_run.parse_args(["--confirm-cost", "--no-evaluate", "--limit", "1", "--agent", "local"])
        runner_ready = args.agent == "local"
    except Exception as exc:
        return {"ready": False, "agent_detected": agent_ready, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ready": agent_ready and runner_ready,
        "agent_detected": agent_ready,
        "swe_runner_agent": "local" if runner_ready else "",
    }


if __name__ == "__main__":
    raise SystemExit(main())
