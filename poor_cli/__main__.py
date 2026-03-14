"""Launch poor-cli TUI by default or run headless exec mode."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from .core import PoorCLICore
from .repo_config import get_repo_config


def _repo_binary_is_fresh(repo_root: Path, binary: Path) -> bool:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return False

    try:
        binary_mtime = binary.stat().st_mtime
    except OSError:
        return False

    watched_paths = [
        repo_root / "poor-cli-tui" / "Cargo.toml",
        repo_root / "poor-cli-tui" / "Cargo.lock",
    ]
    src_dir = repo_root / "poor-cli-tui" / "src"
    watched_paths.extend(path for path in src_dir.rglob("*") if path.is_file())

    try:
        return not any(path.stat().st_mtime > binary_mtime for path in watched_paths if path.exists())
    except OSError:
        return False


def _run_repo_tui_binary(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    binary = repo_root / "poor-cli-tui" / "target" / "release" / "poor-cli-tui"
    if not _repo_binary_is_fresh(repo_root, binary):
        return 1
    os.execv(str(binary), [str(binary), *argv])
    return 1


def _run_tui_from_repo(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "run_tui.sh"
    if not script.is_file():
        return 1
    return subprocess.call([str(script), *argv], cwd=str(repo_root))


def _run_tui_binary(argv: list[str]) -> int:
    binary = shutil.which("poor-cli-tui")
    if binary is None:
        return 1
    os.execvp(binary, [binary, *argv])
    return 1


def _launch_tui(argv: list[str]) -> int:
    if _run_repo_tui_binary(argv) == 0:
        return 0
    if _run_tui_binary(argv) == 0:
        return 0
    if _run_tui_from_repo(argv) == 0:
        return 0
    raise SystemExit(
        "Rust TUI launcher not found. Run ./run_tui.sh from the repo root "
        "or install the `poor-cli-tui` binary. The Python package always "
        "provides `poor-cli-server`, but `poor-cli` requires a repo checkout "
        "or a preinstalled Rust TUI binary."
    )


def _build_exec_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli exec")
    parser.add_argument("--prompt", help="Prompt to send to the shared poor-cli core")
    parser.add_argument(
        "--output-format",
        choices=("text", "json", "stream-json"),
        default="text",
        help="Output mode for headless execution",
    )
    parser.add_argument("--resume", action="store_true", help="Prefix the prompt with recent repo session history")
    parser.add_argument(
        "--allow-tool",
        action="append",
        default=[],
        help="Allow only the named tool(s); repeat to allow multiple",
    )
    parser.add_argument(
        "--deny-tool",
        action="append",
        default=[],
        help="Deny the named tool(s); repeat to block multiple",
    )
    parser.add_argument("--plan-only", action="store_true", help="Return a plan without executing tools")
    parser.add_argument("--provider", help="Override provider for this execution")
    parser.add_argument("--model", help="Override model for this execution")
    parser.add_argument("--api-key", help="Override API key for this execution")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--cwd", help="Working directory for this execution")
    parser.add_argument(
        "--context-file",
        action="append",
        default=[],
        help="Explicit context file to attach; repeat to attach multiple",
    )
    parser.add_argument(
        "--pinned-context-file",
        action="append",
        default=[],
        help="Pinned context file to attach; repeat to attach multiple",
    )
    parser.add_argument("--context-budget-tokens", type=int, help="Context token budget for backend context selection")
    return parser


def _coerce_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return str(args.prompt)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("`poor-cli exec` requires --prompt or piped stdin.")


def _build_resume_prefix() -> str:
    repo_config = get_repo_config(enable_legacy_history_migration=False)
    sessions = repo_config.list_sessions(limit=1)
    if not sessions:
        return ""

    session = sessions[0]
    if not session.messages:
        return ""

    lines = [
        "[Recent repository session context]",
        f"Session: {session.session_id}",
        f"Model: {session.model}",
    ]
    for message in session.messages[-8:]:
        role = "assistant" if message.role == "model" else message.role
        content = message.content.strip()
        if not content:
            continue
        if len(content) > 1200:
            content = f"{content[:1200]}\n... (truncated)"
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _build_exec_permission_callback(
    allow_tools: set[str],
    deny_tools: set[str],
    *,
    plan_only: bool,
):
    async def _callback(tool_name: str, tool_args: dict[str, Any], preview: Optional[dict[str, Any]] = None):
        del tool_args, preview
        if plan_only:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if tool_name in deny_tools:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if allow_tools and tool_name not in allow_tools:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        return {"allowed": True, "approvedPaths": [], "approvedChunks": []}

    return _callback


async def _run_exec_mode_async(args: argparse.Namespace) -> int:
    if args.cwd:
        os.chdir(Path(args.cwd).expanduser())

    prompt = _coerce_prompt(args).strip()
    if not prompt:
        raise SystemExit("Prompt cannot be empty.")

    if args.resume:
        resume_prefix = _build_resume_prefix()
        if resume_prefix:
            prompt = f"{resume_prefix}\n\nUser request:\n{prompt}"

    if args.plan_only:
        prompt = (
            "Return a concise numbered plan only. Do not call tools or make changes.\n\n"
            f"User request:\n{prompt}"
        )

    config_path = Path(args.config).expanduser() if args.config else None
    core = PoorCLICore(config_path=config_path)
    core.permission_callback = _build_exec_permission_callback(
        set(args.allow_tool or []),
        set(args.deny_tool or []),
        plan_only=bool(args.plan_only),
    )
    await core.initialize(
        provider_name=args.provider,
        model_name=args.model,
        api_key=args.api_key,
    )

    try:
        if args.output_format == "stream-json":
            async for event in core.send_message_events(
                prompt,
                context_files=list(args.context_file or []),
                pinned_context_files=list(args.pinned_context_file or []),
                context_budget_tokens=args.context_budget_tokens,
            ):
                print(
                    json.dumps(
                        {
                            "type": event.type,
                            "data": event.data,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            return 0

        response_text = await core.send_message_sync(
            prompt,
            context_files=list(args.context_file or []),
            pinned_context_files=list(args.pinned_context_file or []),
            context_budget_tokens=args.context_budget_tokens,
        )
        if args.output_format == "json":
            print(
                json.dumps(
                    {
                        "content": response_text,
                        "provider": core.get_provider_info(),
                        "instructionStack": core.inspect_instruction_stack(
                            list(args.context_file or []) + list(args.pinned_context_file or [])
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        print(response_text)
        return 0
    finally:
        await core.shutdown()


def _run_exec_mode(argv: Sequence[str]) -> int:
    parser = _build_exec_parser()
    args = parser.parse_args(list(argv))
    return asyncio.run(_run_exec_mode_async(args))


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "exec":
        raise SystemExit(_run_exec_mode(argv[1:]))
    if argv and argv[0] == "tui":
        raise SystemExit(_launch_tui(argv[1:]))
    raise SystemExit(_launch_tui(argv))


if __name__ == "__main__":
    main()
