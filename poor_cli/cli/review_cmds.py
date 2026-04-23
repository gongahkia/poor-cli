"""Code review and commit CLI subcommands."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from ..core import PoorCLICore


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def run_review_file_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli review")
    parser.add_argument("file", nargs="?", help="file to review (default: staged diff)")
    parser.add_argument("--output-format", choices=("text", "json"), default="text")
    parser.add_argument("--config", help="config file path")
    args = parser.parse_args(list(argv))
    if args.file:
        prompt = f"Review the following file for issues, improvements, and best practices:\n\nFile: {args.file}"
    else:
        prompt = "Review the current staged git diff for issues, improvements, and best practices. Use git_diff to inspect changes."
    async def _run():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize()
        from .._exec_helpers import build_exec_permission_callback
        core.permission_callback = build_exec_permission_callback(
            core, set(), set(), plan_only=False, permission_mode="auto-safe",
            sandbox_preset="review-only", auto_approve=True,
        )
        try:
            return await core.send_message_sync(prompt, source_kind="exec", source_id="cli-review")
        finally:
            await core.shutdown()
    result = asyncio.run(_run())
    if args.output_format == "json":
        _print_json({"review": result})
    else:
        print(result)
    return 0


def _git_diff_text(*, staged_only: bool = False, max_chars: int = 120_000) -> str:
    commands = [["git", "diff", "--cached"]]
    if not staged_only:
        commands.append(["git", "diff"])
    chunks = []
    for command in commands:
        try:
            output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL)
        except Exception:
            output = ""
        if output.strip():
            chunks.append(f"$ {' '.join(command)}\n{output}")
    diff = "\n\n".join(chunks)
    if len(diff) > max_chars:
        diff = diff[:max_chars] + f"\n[diff_truncated_to_chars={max_chars}]"
    return diff


def build_review_loop_prompt(diff_text: str) -> str:
    return (
        "Run a clean-context code review loop over this diff.\n"
        "Act as reviewer only: find bugs, regressions, missing tests, and scope risks.\n"
        "Then synthesize findings for the writer: keep valid issues, discard style-only noise, and list exact files/lines when possible.\n"
        "Do not edit files. Output: findings first, then suggested verification.\n\n"
        f"{diff_text or '[no git diff found]'}"
    )


def run_review_loop_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli review-loop")
    parser.add_argument("--staged-only", action="store_true")
    parser.add_argument("--max-diff-chars", type=int, default=120_000)
    parser.add_argument("--dry-run", action="store_true", help="print prompt without calling the model")
    parser.add_argument("--output-format", choices=("text", "json"), default="text")
    parser.add_argument("--config", help="config file path")
    args = parser.parse_args(list(argv))
    prompt = build_review_loop_prompt(
        _git_diff_text(staged_only=args.staged_only, max_chars=max(1000, args.max_diff_chars))
    )
    if args.dry_run:
        if args.output_format == "json":
            _print_json({"prompt": prompt})
        else:
            print(prompt)
        return 0
    async def _run():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize()
        from .._exec_helpers import build_exec_permission_callback
        core.permission_callback = build_exec_permission_callback(
            core, set(), set(), plan_only=False, permission_mode="auto-safe",
            sandbox_preset="review-only", auto_approve=True,
        )
        try:
            return await core.send_message_sync(prompt, source_kind="exec", source_id="cli-review-loop")
        finally:
            await core.shutdown()
    result = asyncio.run(_run())
    if args.output_format == "json":
        _print_json({"review": result})
    else:
        print(result)
    return 0


def run_commit_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli commit")
    parser.add_argument("--output-format", choices=("text", "json"), default="text")
    parser.add_argument("--config", help="config file path")
    args = parser.parse_args(list(argv))
    prompt = (
        "Generate a concise, conventional commit message for the currently staged git changes. "
        "Use git_diff and git_status to inspect the staged changes. "
        "Output ONLY the commit message, nothing else."
    )
    async def _run():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize()
        from .._exec_helpers import build_exec_permission_callback
        core.permission_callback = build_exec_permission_callback(
            core, set(), set(), plan_only=False, permission_mode="auto-safe",
            sandbox_preset="review-only", auto_approve=True,
        )
        try:
            return await core.send_message_sync(prompt, source_kind="exec", source_id="cli-commit")
        finally:
            await core.shutdown()
    result = asyncio.run(_run())
    if args.output_format == "json":
        _print_json({"commit_message": result})
    else:
        print(result)
    return 0
