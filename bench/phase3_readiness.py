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
    selected_engine = _selected_engine()
    checks = {
        "setup_script": _setup_script(),
        "provider_adapters": _provider_adapters(),
        "selected_engine": _selected_engine_supported(selected_engine),
        "linux_cuda_host": _linux_cuda_host(),
        "engine_python_deps": _python_deps("vllm", "sglang", selected_engine=selected_engine),
        "ollama_binary": _ollama_binary(selected_engine),
        "local_agent_path": _local_agent_path(),
    }
    return {
        "schema_version": "poor-cli-phase3-readiness-v1",
        "selected_engine": selected_engine,
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


def _selected_engine() -> str:
    return (os.environ.get("POOR_CLI_LOCAL_ENGINE") or os.environ.get("POOR_CLI_PROVIDER") or "vllm").strip().lower()


def _selected_engine_supported(selected_engine: str) -> dict[str, Any]:
    supported = {"ollama", "sglang", "vllm"}
    return {
        "ready": selected_engine in supported,
        "engine": selected_engine,
        "supported": sorted(supported),
    }


def _python_deps(*names: str, selected_engine: str | None = None) -> dict[str, Any]:
    current_modules = {name: importlib.util.find_spec(name) is not None for name in names}
    venv_path = _local_cuda_venv()
    venv_python = venv_path / "bin" / "python"
    venv_modules = {name: _venv_module_available(venv_python, name) for name in names}
    modules = {name: current_modules[name] or venv_modules[name] for name in names}
    engine = selected_engine or _selected_engine()
    required = engine in names
    install_engine = engine if engine in {"sglang", "vllm"} else "vllm"
    return {
        "ready": not required or modules[engine],
        "required": required,
        "selected_engine": engine,
        "modules": modules,
        "current_modules": current_modules,
        "venv_modules": venv_modules,
        "venv_python": _display_path(venv_python),
        "venv_python_exists": venv_python.is_file(),
        "requirement": f"selected engine module: {engine}" if required else "not required for selected engine",
        "install": f"scripts/setup-linux-cuda.sh --yes --engine {install_engine}",
    }


def _local_cuda_venv() -> Path:
    raw = Path(os.environ.get("POOR_CLI_LOCAL_VENV", ".poor-cli/local-cuda-venv")).expanduser()
    return raw if raw.is_absolute() else ROOT / raw


def _venv_module_available(python: Path, name: str) -> bool:
    if not python.is_file():
        return False
    try:
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)",
                name,
            ],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _binary(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"ready": bool(path), "available": bool(path), "path": path or ""}


def _ollama_binary(selected_engine: str) -> dict[str, Any]:
    payload = _binary("ollama")
    required = selected_engine == "ollama"
    return {
        **payload,
        "ready": payload["ready"] if required else True,
        "required": required,
        "selected_engine": selected_engine,
    }


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
