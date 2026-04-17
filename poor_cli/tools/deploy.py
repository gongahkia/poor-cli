"""Deploy tools (Phase B). Replaces the removed ``:PoorCLIDeploy`` verb.

Each tool reads the project's deploy config — either ``poor-cli.deploy.yaml``
or ``.poor-cli/deploy.json`` (the same convention the old rpc.deploy used).
The config maps target names to shell commands. Tools execute those commands
via subprocess; no magical behavior. The agent is the user's interface.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


_PREVIEW: Dict[str, Any] = {}
_LOCK = threading.Lock()


def _ctx_cwd(ctx: Any) -> str:
    return getattr(ctx, "cwd", None) or os.getcwd()


def _load_config(cwd: str) -> Dict[str, Any]:
    """Read poor-cli deploy config. Tries, in order:
      ``.poor-cli/deploy.json``  (canonical in Phase B)
      ``poor-cli.deploy.json``
    Returns ``{}`` when missing. No YAML parser dep is introduced here —
    if the user wants YAML they can convert to JSON or we can add PyYAML
    in a follow-up."""
    for rel in (".poor-cli/deploy.json", "poor-cli.deploy.json"):
        p = Path(cwd) / rel
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return {}
    return {}


def _targets_table(config: Dict[str, Any]) -> List[List[str]]:
    targets = config.get("targets") or {}
    rows: List[List[str]] = []
    for name, entry in targets.items():
        cmd = entry.get("cmd") if isinstance(entry, dict) else str(entry)
        desc = entry.get("description", "") if isinstance(entry, dict) else ""
        rows.append([str(name), str(cmd or ""), str(desc)])
    return rows


async def _run(argv: List[str], *, cwd: str, timeout: float = 300.0) -> Any:
    def _sync():
        try:
            return subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            class _R:
                returncode = 124
                stdout = e.stdout or ""
                stderr = (e.stderr or "") + "\n[timed out]"
            return _R()

    return await asyncio.get_running_loop().run_in_executor(None, _sync)


async def handle_run_target(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    target = str(args.get("target") or "").strip()
    if not target:
        return ToolResult.error("target is required")
    config = _load_config(cwd)
    entry = (config.get("targets") or {}).get(target)
    if entry is None:
        available = list((config.get("targets") or {}).keys())
        return ToolResult.error(
            f"no deploy target {target!r}; available: {', '.join(available) or '(none)'}"
        )
    cmd = entry.get("cmd") if isinstance(entry, dict) else str(entry)
    if not cmd:
        return ToolResult.error(f"target {target!r} has no cmd field")
    argv = cmd if isinstance(cmd, list) else shlex.split(str(cmd))
    dry_run = bool(args.get("dry_run"))
    if dry_run:
        return ToolResult.text(f"[dry-run] would execute: {' '.join(argv)}")
    result = await _run(argv, cwd=cwd)
    blocks: List[Any] = [
        TextBlock(
            text=f"deploy {target!r} → exit {result.returncode}"
        )
    ]
    out = (result.stdout or "") + (result.stderr or "")
    if out.strip():
        blocks.append(CodeBlock(language="text", code=out[-6000:]))
    return ToolResult(
        content=blocks,
        is_error=result.returncode != 0,
        metadata={"target": target, "returncode": result.returncode},
    )


async def handle_targets(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    config = _load_config(cwd)
    rows = _targets_table(config)
    if not rows:
        return ToolResult.text(
            "no deploy targets configured; add .poor-cli/deploy.json "
            '({"targets": {"name": {"cmd": "...", "description": "..."}}})'
        )
    return ToolResult(
        content=[TableBlock(columns=["target", "cmd", "description"], rows=rows)]
    )


async def handle_preview_start(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    cmd = args.get("cmd")
    port = args.get("port")
    if not cmd:
        # Try config.preview.cmd
        config = _load_config(cwd)
        cmd = (config.get("preview") or {}).get("cmd")
    if not cmd:
        return ToolResult.error(
            "cmd is required (or configure .poor-cli/deploy.json preview.cmd)"
        )
    argv = cmd if isinstance(cmd, list) else shlex.split(str(cmd))
    if port:
        argv.extend(["--port", str(port)])
    key = "preview"
    with _LOCK:
        if key in _PREVIEW and _PREVIEW[key]["proc"].poll() is None:
            return ToolResult.error(
                f"preview already running (pid={_PREVIEW[key]['proc'].pid}); "
                "stop it first with deploy.preview.stop"
            )
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _PREVIEW[key] = {
            "argv": argv,
            "proc": proc,
            "started_at": time.time(),
            "log": [],
        }
        log_lines = _PREVIEW[key]["log"]

        def _reader():
            assert proc.stdout is not None
            for line in proc.stdout:
                log_lines.append(line.rstrip("\n"))

        threading.Thread(target=_reader, daemon=True).start()
    return ToolResult.text(f"preview started: pid={proc.pid} — {' '.join(argv)}")


async def handle_preview_stop(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    with _LOCK:
        entry = _PREVIEW.get("preview")
    if entry is None or entry["proc"].poll() is not None:
        return ToolResult.text("no preview running")
    proc: subprocess.Popen = entry["proc"]
    try:
        proc.terminate()
    except Exception as e:
        return ToolResult.error(f"stop failed: {e}")
    return ToolResult.text(f"preview stopped (pid={proc.pid})")


async def handle_preview_status(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    with _LOCK:
        entry = _PREVIEW.get("preview")
    if entry is None:
        return ToolResult.text("preview: never started")
    proc: subprocess.Popen = entry["proc"]
    rc = proc.poll()
    state = "running" if rc is None else f"stopped (rc={rc})"
    return ToolResult.text(
        f"preview: {state}; argv={' '.join(entry['argv'])}"
    )


register_tool(
    name="deploy.run",
    description=(
        "Run a named deploy target from .poor-cli/deploy.json. Each target is "
        "a shell command. ``dry_run=true`` echoes the command without "
        "executing. This tool replaces the removed :PoorCLIDeploy command."
    ),
    schema={
        "type": "object",
        "required": ["target"],
        "properties": {
            "target": {"type": "string"},
            "dry_run": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    handler=handle_run_target,
    exclusive=True,
    timeout_s=600.0,
    max_per_minute=2,
)

register_tool(
    name="deploy.targets",
    description="List configured deploy targets (TableBlock of target, cmd, description).",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_targets,
    circuit_disabled=True,
)

register_tool(
    name="deploy.preview.start",
    description=(
        "Start a local preview server in the background. ``cmd`` overrides the "
        "config's preview.cmd. ``port`` is appended as ``--port <n>`` when given."
    ),
    schema={
        "type": "object",
        "properties": {
            "cmd": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
            "port": {"type": "integer", "minimum": 1, "maximum": 65535},
        },
        "additionalProperties": False,
    },
    handler=handle_preview_start,
    exclusive=True,
)

register_tool(
    name="deploy.preview.stop",
    description="Terminate the running preview server.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_preview_stop,
)

register_tool(
    name="deploy.preview.status",
    description="Return preview server status (running|stopped|never-started).",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_preview_status,
)


def _reset() -> None:
    with _LOCK:
        for entry in list(_PREVIEW.values()):
            proc = entry["proc"]
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        _PREVIEW.clear()
