from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ..types import ChatChunk

_DEFAULT_TIMEOUT_SECONDS = 180
_MAX_PROMPT_CHARS = 24000
_SENTINEL_MODELS = {"", "default", "local", "runtime-default"}


def _timeout_seconds() -> int:
    raw = os.environ.get("HAUS_LOCAL_RUNTIME_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(5, int(raw))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def _workspace() -> str:
    return os.environ.get("HAUS_LOCAL_RUNTIME_CWD", str(Path.cwd()))


def _split_cmd(env_var: str, fallback: list[str]) -> list[str]:
    raw = os.environ.get(env_var, "").strip()
    return shlex.split(raw) if raw else list(fallback)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    lines: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            lines.append(str(block.get("text", "")))
        elif block_type == "tool_result":
            lines.append(f"Tool result: {block.get('content', '')}")
        elif block_type == "image":
            lines.append("[image attachment omitted by text-only local runtime]")
    return "\n".join(line for line in lines if line)


def _prompt(system: str, messages: list[dict[str, Any]]) -> str:
    parts = [
        "You are running as a text-only local runtime for Haus chat.",
        "Do not edit files, run shell commands, or call tools. Use only the supplied conversation and layout context.",
        "If the user asks for an applied edit, describe the safe Haus action or deterministic planner step instead of claiming it was applied.",
        "",
        "Haus system context:",
        system,
        "",
        "Conversation:",
    ]
    for msg in messages[-16:]:
        role = str(msg.get("role", "user")).upper()
        text = _content_text(msg.get("content"))
        if text:
            parts.append(f"{role}: {text}")
    prompt = "\n".join(parts).strip()
    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[-_MAX_PROMPT_CHARS:]
    return prompt


def _model_arg(model: str, flag: str = "--model") -> list[str]:
    clean = model.strip()
    return [] if clean in _SENTINEL_MODELS else [flag, clean]


def _codex_cmd(model: str) -> list[str]:
    cmd = _split_cmd(
        "HAUS_CODEX_CMD",
        [
            "codex",
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--color",
            "never",
            "-C",
            _workspace(),
        ],
    )
    if os.environ.get("HAUS_CODEX_OSS", "").lower() in {"1", "true", "yes", "on"} and "--oss" not in cmd:
        cmd.append("--oss")
    local_provider = os.environ.get("HAUS_CODEX_LOCAL_PROVIDER", "").strip()
    if local_provider and "--local-provider" not in cmd:
        cmd.extend(["--local-provider", local_provider])
    cmd.extend(_model_arg(model, "-m"))
    cmd.append("-")
    return cmd


def _claude_cmd(model: str) -> list[str]:
    cmd = _split_cmd(
        "HAUS_CLAUDE_CODE_CMD",
        [
            "claude",
            "-p",
            "--no-session-persistence",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--output-format",
            "text",
        ],
    )
    cmd.extend(_model_arg(model))
    return cmd


def _opencode_cmd(model: str) -> list[str]:
    cmd = _split_cmd("HAUS_OPENCODE_CMD", ["opencode", "run", "--format", "default", "--dir", _workspace(), "--pure"])
    cmd.extend(_model_arg(model, "-m"))
    return cmd


def _run(cmd: list[str], prompt: str, *, prompt_as_arg: bool = False) -> str:
    run_cmd = [*cmd, prompt] if prompt_as_arg else cmd
    try:
        proc = subprocess.run(
            run_cmd,
            input=None if prompt_as_arg else prompt,
            text=True,
            capture_output=True,
            timeout=_timeout_seconds(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Local runtime command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Local runtime timed out after {_timeout_seconds()}s.") from exc
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        detail = stderr or stdout or f"exit {proc.returncode}"
        raise RuntimeError(f"Local runtime failed: {detail}")
    return stdout or stderr


def _chat_with_cmd(
    cmd: list[str],
    messages: list[dict[str, Any]],
    model: str,
    *,
    system: str,
    prompt_as_arg: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    text = _run(cmd, _prompt(system, messages), prompt_as_arg=prompt_as_arg)
    updated = messages + [{"role": "assistant", "content": [{"type": "text", "text": text}]}]
    return text, updated


def chat_codex(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    del api_key, dispatch, tools_spec, max_tool_steps
    return _chat_with_cmd(_codex_cmd(model), messages, model, system=system)


def chat_claude_code(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    del api_key, dispatch, tools_spec, max_tool_steps
    return _chat_with_cmd(_claude_cmd(model), messages, model, system=system, prompt_as_arg=True)


def chat_opencode(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    del api_key, dispatch, tools_spec, max_tool_steps
    return _chat_with_cmd(_opencode_cmd(model), messages, model, system=system, prompt_as_arg=True)


def stream_from_chat(
    fn: Callable[..., tuple[str, list[dict[str, Any]]]],
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> Iterator[ChatChunk]:
    text, updated = fn(api_key, messages, model, dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)
    if text:
        yield ChatChunk("text", {"delta": text})
    yield ChatChunk("done", {"response": text, "history": updated})
