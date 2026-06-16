from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import ConfigError, explain_route, load_config
from .store import RunStore

MANAGED = "# poor-cli-shim-v1"
SHIM_NAMES = ("claude", "codex")
SECRET_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "MOONSHOT_API_KEY", "AUTHORIZATION", "X_API_KEY")
VALUE_FLAGS = {"--output-format", "--input-format", "--permission-mode", "--model", "--max-turns", "--max-budget-usd", "--cwd", "--cd"}


def add_shims_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    shims = sub.add_parser("shims")
    shims_sub = shims.add_subparsers(dest="shims_command")
    for name in ("install", "doctor", "uninstall"):
        parser = shims_sub.add_parser(name)
        parser.add_argument("--dir", default=os.environ.get("POOR_CLI_SHIMS_DIR"))
    run = shims_sub.add_parser("exec")
    run.add_argument("--dir", default=os.environ.get("POOR_CLI_SHIMS_DIR"))
    run.add_argument("agent", choices=SHIM_NAMES)
    run.add_argument("agent_args", nargs=argparse.REMAINDER)


def handle_shims_command(args: Any, store: RunStore) -> int:
    if args.shims_command == "install":
        return _install(_shim_dir(args))
    if args.shims_command == "doctor":
        return _doctor(_shim_dir(args))
    if args.shims_command == "uninstall":
        return _uninstall(_shim_dir(args))
    if args.shims_command == "exec":
        agent_args = list(args.agent_args)
        if agent_args[:1] == ["--"]:
            agent_args = agent_args[1:]
        return _exec(str(args.agent), agent_args, _shim_dir(args), store)
    raise RuntimeError("missing shims command")


def _shim_dir(args: Any) -> Path:
    return Path(args.dir).expanduser() if args.dir else Path.home() / ".poor-cli" / "shims"


def _install(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    for name in SHIM_NAMES:
        path = root / name
        if path.exists() and not _managed(path):
            raise RuntimeError(f"refusing to overwrite unmanaged shim: {path}")
        path.write_text(f"#!/bin/sh\n{MANAGED}\nexec poor-cli shims exec {name} -- \"$@\"\n", encoding="utf-8")
        path.chmod(0o755)
        print(f"installed {path}")
    print(f'add to PATH: export PATH="{root}:$PATH"')
    return 0


def _doctor(root: Path) -> int:
    ok = True
    print(f"shims_dir: {root}")
    for name in SHIM_NAMES:
        path = root / name
        real = resolve_real_binary(name, root)
        managed = _managed(path) if path.exists() else False
        ok = ok and managed and real is not None
        print(f"{name}: shim={'ok' if managed else 'missing'} real={real or 'missing'}")
    return 0 if ok else 1


def _uninstall(root: Path) -> int:
    for name in SHIM_NAMES:
        path = root / name
        if path.exists() and not _managed(path):
            raise RuntimeError(f"refusing to remove unmanaged shim: {path}")
        if path.exists():
            path.unlink()
            print(f"removed {path}")
    return 0


def _exec(agent: str, argv: list[str], root: Path, store: RunStore) -> int:
    real = resolve_real_binary(agent, root)
    if real is None:
        raise RuntimeError(f"real {agent} binary not found outside {root}")
    prompt = _captured_prompt(agent, argv)
    if prompt is None:
        return subprocess.run([str(real), *argv], check=False).returncode
    stdin = sys.stdin.buffer.read() if not sys.stdin.isatty() else b""
    run_id = _record_start(store, agent, argv, prompt or _text(stdin).strip(), real, stdin)
    result = subprocess.run([str(real), *argv], input=stdin or None, capture_output=True, check=False)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    store.put_artifact(
        run_id=run_id,
        kind="shim.result",
        data={"returncode": result.returncode, "stdout": _text(result.stdout), "stderr": _text(result.stderr)},
    )
    store.append_event(run_id, "shim.completed", {"returncode": result.returncode})
    status = "completed" if result.returncode == 0 else "failed"
    store.set_run_status(run_id, status, f"{agent} exited {result.returncode}")
    return result.returncode


def resolve_real_binary(name: str, root: Path, path_env: str | None = None) -> Path | None:
    for item in (path_env if path_env is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if not item:
            continue
        candidate = Path(item).expanduser() / name
        if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
            if candidate.resolve().parent == root.resolve() or _managed(candidate):
                continue
            return candidate
    return None


def _record_start(store: RunStore, agent: str, argv: list[str], prompt: str, real: Path, stdin: bytes) -> str:
    run_id = store.create_run(user_goal=prompt, repo_path=Path.cwd(), git_commit_start=_git_head(), mode="shim", budget={})
    route = _route(prompt)
    if route:
        store.append_event(run_id, "route.selected", route)
    payload = {
        "agent": agent,
        "argv": argv,
        "prompt": prompt,
        "stdin": _text(stdin) if stdin else "",
        "cwd": str(Path.cwd()),
        "real_binary": str(real),
        "redacted_env": {key: "[redacted]" for key in SECRET_ENV if key in os.environ},
    }
    artifact = store.put_artifact(run_id=run_id, kind="shim.capture", data=payload)
    store.append_event(run_id, "shim.invoked", {**payload, "artifact_id": artifact.artifact_id})
    return run_id


def _captured_prompt(agent: str, argv: list[str]) -> str | None:
    if agent == "codex":
        return _positionals(argv[1:])[-1] if argv[:1] == ["exec"] and _positionals(argv[1:]) else None
    if "-p" in argv or "--print" in argv:
        pos = _positionals(argv)
        return pos[-1] if pos else ""
    return " ".join(argv) if len(argv) == 1 and not argv[0].startswith("-") else None


def _positionals(argv: list[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for item in argv:
        if skip:
            skip = False
        elif item in VALUE_FLAGS:
            skip = True
        elif item.startswith("-"):
            continue
        else:
            out.append(item)
    return out


def _managed(path: Path) -> bool:
    try:
        return MANAGED in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:3]
    except OSError:
        return False


def _git_head() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _route(prompt: str) -> dict[str, Any] | None:
    try:
        return explain_route(load_config(), prompt, role="executor")
    except ConfigError:
        return None


def _text(data: bytes) -> str:
    return data.decode(errors="replace")
