"""Repo-task runner tools (Phase B).

When overseer.nvim is available the agent's ``task.run`` invocation fires
an overseer template so the user sees the task in their overseer UI. CLI
fallback spawns a managed subprocess and returns a ``task_id`` that
``task.logs`` and ``task.cancel`` address.

Naming note: ``task.*`` refers to *repo build tasks* (test, lint, build,
package run-scripts). The unrelated Phase-A ``:PoorCLIAgent task-*`` verb
set addresses long-running agent tasks — a different subsystem.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


# In-process task registry. Keyed by task_id. Production path would use the
# server's ManagedServiceRuntime; for Phase B we keep it minimal and
# self-contained so the tool can be exercised without the full server.
_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _ctx_cwd(ctx: Any) -> str:
    return getattr(ctx, "cwd", None) or os.getcwd()


async def _notify(ctx: Any, method: str, params: Dict[str, Any]) -> None:
    fn = getattr(ctx, "notify_client", None)
    if fn is None:
        return
    try:
        maybe = fn(method, params)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass


def _new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:10]}"


def _spawn_cli_task(cwd: str, argv: List[str]) -> Dict[str, Any]:
    task_id = _new_task_id()
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_lines: List[str] = []

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))
        proc.wait()

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    with _LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "argv": argv,
            "proc": proc,
            "thread": thread,
            "log": log_lines,
            "started_at": time.time(),
            "cwd": cwd,
        }
    return _TASKS[task_id]


def _task_status(task: Dict[str, Any]) -> str:
    proc: subprocess.Popen = task["proc"]
    rc = proc.poll()
    if rc is None:
        return "running"
    return "completed" if rc == 0 else f"failed (rc={rc})"


async def handle_run(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    name = str(args.get("name") or "").strip()
    cmd = args.get("cmd") or args.get("command")
    if not name and not cmd:
        return ToolResult.error("name (overseer template) or cmd (shell string) is required")
    if getattr(ctx, "has_plugin", lambda _: False)("overseer") and name:
        await _notify(
            ctx,
            "integration.overseer.runTemplate",
            {"name": name, "args": args.get("args") or {}},
        )
        # Overseer tracks the lifecycle visually; our side returns a metadata
        # handle so the agent can phrase "running task <name>".
        return ToolResult(
            content=[TextBlock(text=f"dispatched overseer template: {name}")],
            metadata={"overseer_template": name},
        )
    # CLI fallback.
    if cmd:
        argv = cmd if isinstance(cmd, list) else shlex.split(str(cmd))
    else:
        # No overseer and only a template name — use `make <name>` as a
        # best-effort convention so users with Makefile targets still work.
        argv = ["make", name]
    task = _spawn_cli_task(cwd=cwd, argv=argv)
    return ToolResult(
        content=[
            TextBlock(text=f"started task {task['task_id']}: {' '.join(argv)}"),
        ],
        metadata={"task_id": task["task_id"], "degraded": "cli"},
    )


async def handle_status(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        with _LOCK:
            rows = [
                [t["task_id"], _task_status(t), " ".join(t["argv"])]
                for t in _TASKS.values()
            ]
        if not rows:
            return ToolResult.text("no managed tasks")
        return ToolResult(content=[TableBlock(columns=["task_id", "status", "cmd"], rows=rows)])
    with _LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return ToolResult.error(f"unknown task_id {task_id!r}")
    return ToolResult(
        content=[
            TextBlock(
                text=f"{task['task_id']}: {_task_status(task)} (started {int(time.time()-task['started_at'])}s ago)"
            )
        ]
    )


async def handle_logs(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return ToolResult.error("task_id is required")
    tail = int(args.get("tail_lines") or 100)
    with _LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return ToolResult.error(f"unknown task_id {task_id!r}")
    lines = task["log"][-max(1, tail):]
    text = "\n".join(lines) if lines else "(no output yet)"
    return ToolResult(content=[CodeBlock(language="text", code=text)])


async def handle_cancel(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return ToolResult.error("task_id is required")
    with _LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return ToolResult.error(f"unknown task_id {task_id!r}")
    proc: subprocess.Popen = task["proc"]
    if proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
        except Exception as e:
            return ToolResult.error(f"cancel failed: {e}")
    return ToolResult.text(f"cancelled {task_id}")


async def handle_list(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    # When overseer is available, we forward to its templates; for the CLI
    # path we list in-process tasks only.
    with _LOCK:
        rows = [[t["task_id"], _task_status(t), " ".join(t["argv"])] for t in _TASKS.values()]
    if not rows:
        return ToolResult.text("no in-process tasks. When overseer is available, prefer its task pane for templates.")
    return ToolResult(content=[TableBlock(columns=["task_id", "status", "cmd"], rows=rows)])


register_tool(
    name="task.run",
    description=(
        "Run a repo task. If overseer.nvim is available and ``name`` matches "
        "an overseer template, dispatch there. Otherwise run the shell ``cmd`` "
        "(or ``make <name>`` as a best-effort fallback) as a managed subprocess "
        "and return a ``task_id`` usable with task.logs and task.cancel."
    ),
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "cmd": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
            "args": {"type": "object"},
        },
        "additionalProperties": False,
    },
    handler=handle_run,
    exclusive=True,
    max_per_minute=10,
)

register_tool(
    name="task.status",
    description="Status of a task (args.task_id) or all in-process tasks.",
    schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_status,
    circuit_disabled=True,
)

register_tool(
    name="task.logs",
    description="Tail the last N lines of a task's output.",
    schema={
        "type": "object",
        "required": ["task_id"],
        "properties": {
            "task_id": {"type": "string"},
            "tail_lines": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 100},
        },
        "additionalProperties": False,
    },
    handler=handle_logs,
    circuit_disabled=True,
)

register_tool(
    name="task.cancel",
    description="Send SIGTERM to a running task.",
    schema={
        "type": "object",
        "required": ["task_id"],
        "properties": {"task_id": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_cancel,
)

register_tool(
    name="task.list",
    description="List in-process managed tasks (overseer has its own view).",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_list,
    circuit_disabled=True,
)


# Test hook — flush the global registry so per-test tasks don't leak.
def _reset() -> None:
    with _LOCK:
        for t in list(_TASKS.values()):
            proc = t["proc"]
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        _TASKS.clear()
