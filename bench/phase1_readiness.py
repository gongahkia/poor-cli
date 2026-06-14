from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_FIXTURE_RESULT = ROOT / "bench" / "results" / "local-fixture-bugs-generic.json"
SWE_MANIFEST = ROOT / "tests" / "fixtures" / "swe-lite-10" / "manifest.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Phase 1 release readiness without running live agents.")
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
        "local_fixture_generic_result": _local_fixture_result(),
        "live_anthropic_fixture_prereqs": _live_agent_prereqs("claude", "ANTHROPIC_API_KEY", _claude_auth_status),
        "live_codex_fixture_prereqs": _live_agent_prereqs("codex", "OPENAI_API_KEY", _codex_auth_status),
        "swe_lite_manifest": _swe_lite_manifest(),
        "swe_lite_python_deps": _python_deps("datasets", "swebench"),
        "docker": _docker(),
    }
    return {
        "schema_version": "poor-cli-phase1-readiness-v1",
        "ready": all(check["ready"] for check in checks.values()),
        "checks": checks,
        "remaining": [name for name, check in checks.items() if not check["ready"]],
    }


def _local_fixture_result() -> dict[str, Any]:
    if not LOCAL_FIXTURE_RESULT.is_file():
        return {"ready": False, "reason": "missing result file"}
    payload = json.loads(LOCAL_FIXTURE_RESULT.read_text(encoding="utf-8"))
    ready = (
        payload.get("schema_version") == "poor-cli-local-fixture-bugs-result-v1"
        and payload.get("fixture_count") == 3
        and payload.get("completed_count") == 3
        and payload.get("tests_passed_count") == 3
        and payload.get("replay_verified_count") == 3
    )
    return {
        "ready": ready,
        "fixture_count": payload.get("fixture_count"),
        "completed_count": payload.get("completed_count"),
        "tests_passed_count": payload.get("tests_passed_count"),
        "replay_verified_count": payload.get("replay_verified_count"),
    }


def _live_agent_prereqs(command: str, key_env: str, auth_probe: Any) -> dict[str, Any]:
    path = shutil.which(command)
    version = _version(path) if path else ""
    key_set = bool(os.environ.get(key_env))
    cli_auth = auth_probe(path) if path else {"ready": False, "checked": False}
    return {
        "ready": bool(path and (key_set or cli_auth["ready"])),
        "command": command,
        "available": bool(path),
        "version": version,
        "auth_env": key_env,
        "auth_env_set": key_set,
        "cli_auth": cli_auth,
    }


def _claude_auth_status(path: str) -> dict[str, Any]:
    result = _status_command([path, "auth", "status"])
    payload = _json_object(result.stdout)
    logged_in = bool(payload.get("loggedIn")) if payload else False
    return {
        "checked": True,
        "ready": result.returncode == 0 and logged_in,
        "method": str(payload.get("authMethod") or "") if payload else "",
        "provider": str(payload.get("apiProvider") or "") if payload else "",
        "returncode": result.returncode,
    }


def _codex_auth_status(path: str) -> dict[str, Any]:
    result = _status_command([path, "login", "status"])
    text = (result.stdout or result.stderr).strip()
    logged_in = result.returncode == 0 and text.lower().startswith("logged in")
    method = text.removeprefix("Logged in using ").strip() if logged_in else ""
    return {"checked": True, "ready": logged_in, "method": method, "returncode": result.returncode}


def _swe_lite_manifest() -> dict[str, Any]:
    if not SWE_MANIFEST.is_file():
        return {"ready": False, "reason": "missing manifest"}
    payload = json.loads(SWE_MANIFEST.read_text(encoding="utf-8"))
    instances = payload.get("instances") if isinstance(payload.get("instances"), list) else []
    ready = payload.get("schema_version") == "swe-lite-10-v1" and len(instances) == 10
    return {"ready": ready, "schema_version": payload.get("schema_version"), "instance_count": len(instances)}


def _python_deps(*names: str) -> dict[str, Any]:
    modules = {name: importlib.util.find_spec(name) is not None for name in names}
    return {"ready": all(modules.values()), "modules": modules, "install": "python -m pip install -e '.[bench]'"}


def _docker() -> dict[str, Any]:
    if shutil.which("docker") is None:
        return {"ready": False, "available": False, "daemon": False, "version": ""}
    result = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], text=True, capture_output=True, timeout=10, check=False)
    version = result.stdout.strip()
    return {"ready": result.returncode == 0, "available": True, "daemon": result.returncode == 0, "version": version}


def _version(path: str) -> str:
    result = subprocess.run([path, "--version"], text=True, capture_output=True, timeout=10, check=False)
    return (result.stdout or result.stderr).strip().splitlines()[0][:160] if (result.stdout or result.stderr).strip() else ""


def _status_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)


def _json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
