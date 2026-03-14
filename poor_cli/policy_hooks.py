"""
Repo-local policy hook execution.

Hooks live under `.poor-cli/hooks/*.json` and receive a JSON payload on stdin.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

HOOK_EVENTS: tuple[str, ...] = (
    "session_start",
    "user_prompt_submitted",
    "pre_tool_use",
    "post_tool_use",
)


@dataclass
class HookDefinition:
    """Single hook command declaration."""

    event: str
    command: str
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    timeout_sec: int = 15
    env: Dict[str, str] = field(default_factory=dict)
    name: str = ""
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "timeoutSec": self.timeout_sec,
            "env": self.env,
            "name": self.name,
            "sourcePath": self.source_path,
        }


@dataclass
class HookExecutionResult:
    """Result of a hook process invocation."""

    hook: HookDefinition
    return_code: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def blocked(self) -> bool:
        return self.hook.event == "pre_tool_use" and self.return_code != 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hook": self.hook.to_dict(),
            "returnCode": self.return_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "durationMs": self.duration_ms,
            "blocked": self.blocked,
        }


class PolicyHookManager:
    """Load and run repo-local policy hooks."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.hooks_dir = self.repo_root / ".poor-cli" / "hooks"
        self._hooks_by_event: Dict[str, List[HookDefinition]] = {event: [] for event in HOOK_EVENTS}
        self.reload()

    def reload(self) -> None:
        hooks_by_event: Dict[str, List[HookDefinition]] = {event: [] for event in HOOK_EVENTS}
        if self.hooks_dir.is_dir():
            for path in sorted(self.hooks_dir.glob("*.json")):
                for hook in self._load_hooks_from_file(path):
                    hooks_by_event.setdefault(hook.event, []).append(hook)
        self._hooks_by_event = hooks_by_event

    def status(self) -> Dict[str, Any]:
        return {
            "hooksDir": str(self.hooks_dir),
            "totalHooks": sum(len(hooks) for hooks in self._hooks_by_event.values()),
            "events": {
                event: [hook.to_dict() for hook in hooks]
                for event, hooks in self._hooks_by_event.items()
            },
        }

    async def run(self, event: str, payload: Dict[str, Any]) -> List[HookExecutionResult]:
        hooks = self._hooks_by_event.get(event, [])
        if not hooks:
            return []

        encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        results: List[HookExecutionResult] = []

        for hook in hooks:
            argv = self._hook_argv(hook)
            if not argv:
                logger.warning("Skipping hook with empty argv from %s", hook.source_path)
                continue

            cwd = self.repo_root
            if hook.cwd:
                candidate = Path(hook.cwd).expanduser()
                cwd = (self.repo_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()

            started = time.monotonic()
            process = await asyncio.create_subprocess_exec(
                argv[0],
                *argv[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env={**os.environ, **hook.env},
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(encoded_payload),
                    timeout=max(1, hook.timeout_sec),
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                stdout = b""
                stderr = b"hook timed out"
                return_code = 1
            else:
                return_code = process.returncode if process.returncode is not None else 1

            duration_ms = int((time.monotonic() - started) * 1000)
            result = HookExecutionResult(
                hook=hook,
                return_code=return_code,
                stdout=stdout.decode("utf-8", errors="replace").strip(),
                stderr=stderr.decode("utf-8", errors="replace").strip(),
                duration_ms=duration_ms,
            )
            results.append(result)
            if result.blocked:
                break

        return results

    def _load_hooks_from_file(self, path: Path) -> List[HookDefinition]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Failed to parse hook file %s: %s", path, error)
            return []

        hooks: List[HookDefinition] = []
        if isinstance(payload, dict) and isinstance(payload.get("hooks"), dict):
            for event, entries in payload["hooks"].items():
                hooks.extend(self._hook_entries_from_payload(path, event, entries))
        elif isinstance(payload, dict) and payload.get("event"):
            hooks.extend(self._hook_entries_from_payload(path, str(payload.get("event")), [payload]))
        elif isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict) and entry.get("event"):
                    hooks.extend(self._hook_entries_from_payload(path, str(entry.get("event")), [entry]))
        return hooks

    def _hook_entries_from_payload(
        self,
        source_path: Path,
        event: str,
        entries: Any,
    ) -> List[HookDefinition]:
        if event not in HOOK_EVENTS or not isinstance(entries, list):
            return []

        hooks: List[HookDefinition] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            command = str(entry.get("command", "")).strip()
            if not command:
                continue
            args = entry.get("args", [])
            if not isinstance(args, list):
                args = []
            env = entry.get("env", {})
            if not isinstance(env, dict):
                env = {}
            hooks.append(
                HookDefinition(
                    event=event,
                    command=command,
                    args=[str(value) for value in args],
                    cwd=str(entry.get("cwd", "")).strip() or None,
                    timeout_sec=max(1, int(entry.get("timeoutSec", 15))),
                    env={str(key): str(value) for key, value in env.items()},
                    name=str(entry.get("name", "")).strip() or source_path.stem,
                    source_path=str(source_path),
                )
            )
        return hooks

    @staticmethod
    def _hook_argv(hook: HookDefinition) -> List[str]:
        if hook.args:
            return [hook.command, *hook.args]
        return shlex.split(hook.command)
