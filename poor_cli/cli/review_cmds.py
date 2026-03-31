"""Code review and commit CLI subcommands."""

from __future__ import annotations

import argparse
import asyncio
import json
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
