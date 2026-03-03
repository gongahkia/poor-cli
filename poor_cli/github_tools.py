"""
Async GitHub CLI wrappers for tool calls.
"""

import asyncio
from typing import List


async def _run_gh(args: List[str]) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return f"GitHub CLI unavailable: {e}"

    stdout, stderr = await process.communicate()
    out_text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        return f"gh command failed ({process.returncode}): {err_text or out_text or 'Unknown error'}"

    return out_text or "(No output)"


async def gh_pr_list(state: str = "open", limit: int = 10) -> str:
    return await _run_gh([
        "pr",
        "list",
        "--state",
        str(state),
        "--limit",
        str(limit),
        "--json",
        "number,title,author,url,state",
    ])


async def gh_pr_view(number: int) -> str:
    return await _run_gh([
        "pr",
        "view",
        str(number),
        "--json",
        "number,title,body,state,author,url,comments",
    ])


async def gh_issue_list(state: str = "open", limit: int = 10) -> str:
    return await _run_gh([
        "issue",
        "list",
        "--state",
        str(state),
        "--limit",
        str(limit),
        "--json",
        "number,title,author,url,state",
    ])


async def gh_issue_view(number: int) -> str:
    return await _run_gh([
        "issue",
        "view",
        str(number),
        "--json",
        "number,title,body,state,author,url,comments",
    ])


async def gh_pr_create(title: str, body: str, base: str = "main") -> str:
    return await _run_gh([
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        base,
    ])


async def gh_pr_comment(number: int, body: str) -> str:
    return await _run_gh([
        "pr",
        "comment",
        str(number),
        "--body",
        body,
    ])
