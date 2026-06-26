from __future__ import annotations

import os
import json
import shlex
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ..types import ChatChunk

_DEFAULT_TIMEOUT_SECONDS = 180
_MAX_PROMPT_CHARS = 90000
_MAX_TOOL_SCHEMA_CHARS = 70000
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


def _tool_prompt(system: str, messages: list[dict[str, Any]], tools_spec: list[dict[str, Any]]) -> str:
    tools = [
        {
            "name": str(tool.get("name", "")),
            "description": str(tool.get("description", "")),
            "parameters": tool.get("parameters", {}),
        }
        for tool in tools_spec
    ]
    tools_json = json.dumps(tools, separators=(",", ":"))
    if len(tools_json) > _MAX_TOOL_SCHEMA_CHARS:
        tools_json = tools_json[:_MAX_TOOL_SCHEMA_CHARS] + "...[truncated]"
    parts = [
        "You are running as a local runtime for Haus chat.",
        "Do not edit files, run shell commands, or use runtime-native tools.",
        "You may call Haus tools by returning strict JSON only.",
        'For tool calls, return {"tool_calls":[{"name":"tool_name","arguments":{}}],"response":""}.',
        'For a final answer, return {"tool_calls":[],"response":"final text"}.',
        "Return no markdown fences or prose outside the JSON object.",
        "",
        "Haus system context:",
        system,
        "",
        "Available Haus tools:",
        tools_json,
        "",
        "Conversation:",
    ]
    for msg in messages[-18:]:
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


def _append_missing(cmd: list[str], args: list[str]) -> None:
    for arg in args:
        if arg not in cmd:
            cmd.append(arg)


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


def _gemini_cmd(model: str) -> list[str]:
    cmd = _split_cmd("HAUS_GEMINI_CLI_CMD", ["gemini"])
    cmd.extend(_model_arg(model, "-m"))
    _append_missing(cmd, ["--output-format", "json"])
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


def _aider_cmd(model: str) -> list[str]:
    cmd = _split_cmd("HAUS_AIDER_CMD", ["aider"])
    cmd.extend(_model_arg(model))
    _append_missing(cmd, ["--dry-run", "--no-auto-commits", "--no-dirty-commits", "--no-stream", "--no-pretty", "--yes-always"])
    return cmd


def _with_prompt_arg(cmd: list[str], prompt: str, flags: set[str]) -> list[str]:
    out: list[str] = []
    inserted = False
    for arg in cmd:
        if arg == "{prompt}":
            out.append(prompt)
            inserted = True
            continue
        out.append(arg)
        if arg in flags:
            inserted = True
            out.append(prompt)
    if inserted:
        return out
    flag = next(iter(flags))
    return [*out, flag, prompt]


def _extract_json_text(raw: str) -> str:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    def walk(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(part for item in value if (part := walk(item)))
        if not isinstance(value, dict):
            return ""
        for key in ("text", "response", "output", "content", "message"):
            if key in value and (part := walk(value[key])):
                return part
        return "\n".join(part for item in value.values() if (part := walk(item)))

    return walk(parsed) or raw


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_tool_call_response(raw: str) -> tuple[str, list[dict[str, Any]]]:
    parsed = _extract_json_object(raw)
    if parsed is None:
        return raw.strip(), []
    response = str(parsed.get("response") or parsed.get("final") or parsed.get("answer") or "")
    raw_calls = parsed.get("tool_calls") or parsed.get("tools") or parsed.get("calls") or []
    if isinstance(raw_calls, dict):
        raw_calls = [raw_calls]
    calls: list[dict[str, Any]] = []
    if isinstance(raw_calls, list):
        for call in raw_calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or call.get("tool") or call.get("function") or "")
            args = call.get("arguments", call.get("args", {}))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if name and isinstance(args, dict):
                calls.append({"name": name, "arguments": args})
    return response, calls


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


def _run_gemini(cmd: list[str], prompt: str) -> str:
    return _extract_json_text(_run(_with_prompt_arg(cmd, prompt, {"-p", "--prompt"}), prompt, prompt_as_arg=False))


def _run_aider(cmd: list[str], prompt: str) -> str:
    return _run(_with_prompt_arg(cmd, prompt, {"--message", "--msg", "-m"}), prompt, prompt_as_arg=False)


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


def _chat_with_tool_protocol(
    run_once: Callable[[str], str],
    messages: list[dict[str, Any]],
    *,
    dispatch: Callable[[str, dict[str, Any]], str],
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    for step in range(max_tool_steps):
        raw = run_once(_tool_prompt(system, messages, tools_spec))
        text, calls = _parse_tool_call_response(raw)
        if not calls:
            final_text = text or raw.strip()
            messages.append({"role": "assistant", "content": [{"type": "text", "text": final_text}]})
            return final_text, messages

        assistant_content: list[dict[str, Any]] = []
        if text:
            assistant_content.append({"type": "text", "text": text})
        tool_results: list[dict[str, Any]] = []
        for index, call in enumerate(calls):
            name = str(call["name"])
            args = dict(call.get("arguments", {}))
            call_id = f"local-runtime-call-{step}-{index}"
            result = dispatch(name, args)
            assistant_content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})
            tool_results.append({"type": "tool_result", "tool_use_id": call_id, "content": result})
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
    raise RuntimeError("Too many tool iterations")


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
    del api_key
    cmd = _codex_cmd(model)
    return _chat_with_tool_protocol(lambda prompt: _run(cmd, prompt), messages, dispatch=dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)


def chat_gemini_cli(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    del api_key
    cmd = _gemini_cmd(model)
    return _chat_with_tool_protocol(lambda prompt: _run_gemini(cmd, prompt), messages, dispatch=dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)


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
    del api_key
    cmd = _claude_cmd(model)
    return _chat_with_tool_protocol(lambda prompt: _run(cmd, prompt, prompt_as_arg=True), messages, dispatch=dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)


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
    del api_key
    cmd = _opencode_cmd(model)
    return _chat_with_tool_protocol(lambda prompt: _run(cmd, prompt, prompt_as_arg=True), messages, dispatch=dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)


def chat_aider(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    del api_key
    cmd = _aider_cmd(model)
    return _chat_with_tool_protocol(lambda prompt: _run_aider(cmd, prompt), messages, dispatch=dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)


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
