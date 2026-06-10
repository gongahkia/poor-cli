from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiofiles

from .exceptions import CommandExecutionError, ToolExecutionError, ValidationError, validate_file_path
from .tool_stream import CallbackStreamingResult, SubprocessStreamingResult


def bind_stream_function(registry: Any, tool_name: str) -> Optional[Callable[..., Any]]:
    mapping = {
        "bash": stream_bash,
        "run_tests": stream_run_tests,
        "process_logs": stream_process_logs,
    }
    function = mapping.get(tool_name)
    if function is None:
        return None

    async def bound(**kwargs: Any) -> Any:
        return await function(registry, **kwargs)

    return bound


async def stream_bash(registry: Any, command: str, timeout: int = 60) -> SubprocessStreamingResult:
    security_cfg = getattr(getattr(registry, "config", None), "security", None)
    timeout_ceiling = getattr(security_cfg, "max_bash_timeout_seconds", None)
    if isinstance(timeout_ceiling, int) and timeout_ceiling > 0:
        timeout = min(timeout, timeout_ceiling)

    validation = registry.command_validator.validate(command)
    if not validation.is_safe:
        warning_text = "; ".join(validation.warnings) if validation.warnings else "Unsafe command blocked"
        suggestion_text = (
            f" Suggested alternative: {validation.suggested_alternative}"
            if validation.suggested_alternative
            else ""
        )
        raise CommandExecutionError(
            command,
            (
                f"Command blocked by validator "
                f"(risk={validation.risk_level.value}): {warning_text}{suggestion_text}"
            ),
        )
    if not command.strip():
        raise CommandExecutionError(command, "Command is empty after parsing")

    wrapped_cmd = f"{command}; echo __CWD__=$(pwd)"
    from .docker_sandbox import docker_sandbox_enabled, docker_sandboxed_command
    from .sandbox import os_sandbox_available, sandboxed_command

    if registry._core:
        core_preset = getattr(registry._core, "_sandbox_preset", None)
    else:
        core_preset = None
    sandbox_preset = getattr(registry, "_sandbox_preset", None) or core_preset or "workspace-write"
    if docker_sandbox_enabled() and sandbox_preset != "full-access":
        argv = docker_sandboxed_command(wrapped_cmd, sandbox_preset)
    elif os_sandbox_available() and sandbox_preset != "full-access":
        argv = sandboxed_command(wrapped_cmd, sandbox_preset)
    else:
        argv = ["sh", "-c", wrapped_cmd]

    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=registry._cwd,
        **registry._subprocess_spawn_kwargs(),
    )

    def finalize(
        stdout_text: str,
        stderr_text: str,
        return_code: int,
        timed_out: bool,
        stdout_truncated: bool,
        stderr_truncated: bool,
        cancelled: bool,
    ) -> str:
        if cancelled:
            raise CommandExecutionError(command, "Command cancelled")
        if timed_out:
            raise CommandExecutionError(command, f"Command timed out after {timeout} seconds")
        cwd_lines = []
        output_lines = []
        for line in stdout_text.splitlines(True):
            if line.rstrip("\n\r").startswith("__CWD__="):
                cwd_lines.append(line.rstrip("\n\r")[len("__CWD__="):])
            else:
                output_lines.append(line)
        if cwd_lines and return_code == 0:
            registry._cwd = cwd_lines[-1]
        stdout_rendered = "".join(output_lines)
        notes: List[str] = []
        if stdout_truncated:
            notes.append(f"stdout truncated at {registry.MAX_CAPTURED_OUTPUT_BYTES} bytes")
        if stderr_truncated:
            notes.append(f"stderr truncated at {registry.MAX_CAPTURED_OUTPUT_BYTES} bytes")
        suffix = "\n[Output truncated: " + ", ".join(notes) + "]" if notes else ""
        if return_code != 0:
            error_msg = stderr_text or stdout_rendered or "Command failed"
            raise CommandExecutionError(
                command,
                f"Command failed with exit code {return_code}: {error_msg}{suffix}",
                return_code=return_code,
            )
        return (stdout_rendered or "(No output)") + suffix

    return SubprocessStreamingResult(
        process=process,
        timeout=timeout,
        max_bytes=registry.MAX_CAPTURED_OUTPUT_BYTES,
        signal_process=registry._signal_async_process,
        finalizer=finalize,
    )


async def stream_run_tests(
    registry: Any,
    command: Optional[str] = None,
    path: Optional[str] = None,
    timeout: int = 300,
) -> SubprocessStreamingResult:
    work_dir = registry._resolve_directory(path)
    argv = shlex.split(command) if command else registry._infer_test_command(work_dir)
    if not argv:
        raise ToolExecutionError(
            "run_tests",
            "Could not infer a test command. Provide `command`, for example `pytest -q`.",
        )
    started = time.time()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **registry._subprocess_spawn_kwargs(),
    )

    def finalize(
        stdout_text: str,
        stderr_text: str,
        return_code: int,
        timed_out: bool,
        stdout_truncated: bool,
        stderr_truncated: bool,
        _cancelled: bool,
    ) -> str:
        duration = round(time.time() - started, 2)
        combined_output = "\n".join(part for part in [stdout_text, stderr_text] if part)
        payload = {
            "ok": (not timed_out) and return_code == 0,
            "command": " ".join(argv),
            "working_directory": str(work_dir),
            "duration_seconds": duration,
            "timed_out": timed_out,
            "exit_code": return_code,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "output_truncated": bool(stdout_truncated or stderr_truncated),
            "failing_locations": registry._extract_failure_locations(combined_output),
            "output_excerpt": combined_output[:6000],
        }
        return json.dumps(payload, indent=2)

    return SubprocessStreamingResult(
        process=process,
        timeout=timeout,
        max_bytes=registry.MAX_CAPTURED_OUTPUT_BYTES,
        signal_process=registry._signal_async_process,
        finalizer=finalize,
    )


async def stream_process_logs(
    _registry: Any,
    path: Optional[str] = None,
    pattern: Optional[str] = None,
    max_lines: int = 5000,
) -> CallbackStreamingResult:
    async def run(emit: Callable[[str], Any]) -> str:
        if max_lines <= 0:
            raise ValidationError("max_lines must be a positive integer")
        target = validate_file_path(path, must_exist=True) if path else Path.cwd()
        files = [target] if target.is_file() else _discover_log_files(target)
        if not files:
            raise ToolExecutionError("process_logs", "No log files found to process")

        regex = re.compile(pattern) if pattern else None
        per_file_budget = max(50, max_lines // max(len(files), 1))
        level_counts: Counter = Counter()
        error_signatures: Counter = Counter()
        signature_samples: Dict[str, str] = {}
        lines_analyzed = 0
        files_analyzed: List[str] = []

        for log_file in files[:25]:
            await emit(f"processing {log_file}\n")
            try:
                async with aiofiles.open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
                    lines = await handle.readlines()
            except Exception:
                continue
            files_analyzed.append(str(log_file))
            for raw_line in lines[-per_file_budget:]:
                line = raw_line.strip()
                if not line or (regex and not regex.search(line)):
                    continue
                lines_analyzed += 1
                _count_log_line(line, level_counts, error_signatures, signature_samples)

        top_errors = [
            {"signature": signature, "count": count, "sample": signature_samples.get(signature, "")}
            for signature, count in error_signatures.most_common(5)
        ]
        return json.dumps(
            {
                "files_analyzed": files_analyzed,
                "lines_analyzed": lines_analyzed,
                "level_counts": dict(level_counts),
                "top_errors": top_errors,
                "likely_root_cause": top_errors[0]["sample"] if top_errors else "",
            },
            indent=2,
        )

    return CallbackStreamingResult(run)


def _discover_log_files(target: Path) -> List[Path]:
    candidates: List[Path] = []
    for extension in ("*.log", "*.txt", "*.out"):
        candidates.extend(target.rglob(extension))
    return sorted({candidate for candidate in candidates if candidate.is_file()})


def _count_log_line(
    line: str,
    level_counts: Counter,
    error_signatures: Counter,
    signature_samples: Dict[str, str],
) -> None:
    lowered = line.lower()
    if "error" in lowered or "exception" in lowered or "traceback" in lowered:
        level_counts["error"] += 1
        signature = re.sub(r"\d+", "<num>", line)
        signature = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", signature, flags=re.IGNORECASE)
        error_signatures[signature] += 1
        signature_samples.setdefault(signature, line[:240])
    elif "warn" in lowered:
        level_counts["warning"] += 1
    elif "info" in lowered:
        level_counts["info"] += 1
    elif "debug" in lowered:
        level_counts["debug"] += 1
    else:
        level_counts["other"] += 1
