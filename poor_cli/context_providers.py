"""@-mention context providers for expanding typed context references."""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

_MENTION_RE = re.compile(r'@(codebase|diff|terminal|docs|web|symbol)\b(?:\s+(.+?))?(?=\s*@|\s*$)', re.IGNORECASE)
_FILE_MENTION_RE = re.compile(r'@"([^"]+)"|@([\w./\-]+\.\w+)')


async def _resolve_codebase(query: str, core: Any) -> str:
    """@codebase <query> — semantic search over indexed repo."""
    if not query.strip():
        return "[codebase: no query provided]"
    if hasattr(core, "tool_registry") and core.tool_registry:
        try:
            result = await core.tool_registry.execute_tool("semantic_search", {"query": query})
            return f"[codebase search: {query}]\n{result}"
        except Exception:
            pass
    # fallback: grep
    try:
        result = await core.tool_registry.execute_tool("grep_files", {"pattern": query, "max_results": 10})
        return f"[codebase grep: {query}]\n{result}"
    except Exception as e:
        return f"[codebase: search failed: {e}]"


async def _resolve_diff(_query: str, _core: Any) -> str:
    """@diff — current git diff (staged + unstaged)."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, timeout=15, cwd=str(Path.cwd()),
        )
        diff = result.stdout.strip()
        if not diff:
            return "[diff: no changes]"
        if len(diff) > 10000:
            diff = diff[:10000] + "\n... [truncated]"
        return f"[git diff]\n{diff}"
    except Exception as e:
        return f"[diff: error: {e}]"


async def _resolve_terminal(_query: str, core: Any) -> str:
    """@terminal — recent terminal output from bash tool executions."""
    last_outputs = getattr(core, "_last_bash_outputs", [])
    if not last_outputs:
        return "[terminal: no recent output]"
    parts = ["[recent terminal output]"]
    for entry in last_outputs[-5:]: # last 5 commands
        cmd = entry.get("command", "")
        output = entry.get("output", "")[:2000]
        parts.append(f"$ {cmd}\n{output}")
    return "\n\n".join(parts)


async def _resolve_docs(query: str, _core: Any) -> str:
    """@docs <query> — search project documentation files."""
    if not query.strip():
        return "[docs: no query provided]"
    root = Path.cwd()
    doc_files = []
    for pattern in ["*.md", "docs/**/*.md", "doc/**/*.md", "README*"]:
        doc_files.extend(root.glob(pattern))
    if not doc_files:
        return "[docs: no documentation files found]"
    results = []
    query_lower = query.lower()
    for f in doc_files[:50]: # cap search
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if query_lower in content.lower():
                # extract relevant context around match
                idx = content.lower().index(query_lower)
                start = max(0, idx - 200)
                end = min(len(content), idx + 500)
                snippet = content[start:end].strip()
                results.append(f"[{f.relative_to(root)}]\n{snippet}")
        except Exception:
            continue
    if not results:
        return f"[docs: no matches for '{query}']"
    return "\n\n".join(results[:5])


async def _resolve_web(query: str, core: Any) -> str:
    """@web <query> — web search."""
    if not query.strip():
        return "[web: no query provided]"
    if hasattr(core, "tool_registry") and core.tool_registry:
        try:
            result = await core.tool_registry.execute_tool("web_search", {"query": query})
            return f"[web: {query}]\n{result}"
        except Exception:
            pass
    return f"[web: search unavailable for '{query}']"


async def _resolve_symbol(query: str, core: Any) -> str:
    """@symbol <name> — look up symbol definition in repo graph."""
    if not query.strip():
        return "[symbol: no name provided]"
    try:
        from .repo_graph import RepoGraph
        rg = RepoGraph(Path.cwd())
        matches = rg.symbols_matching(query.strip(), limit=5)
        if not matches:
            return f"[symbol: '{query}' not found in repo graph]"
        results = []
        for m in matches:
            fp = m["file_path"]
            ls = m.get("line_start", 1)
            le = m.get("line_end", ls)
            kind = m.get("kind", "symbol")
            sig = m.get("signature", "")
            # read source lines with padding
            try:
                content = Path(fp).read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                start = max(0, ls - 1)
                end = min(len(lines), le + 5)
                snippet = "\n".join(lines[start:end])
                rel = str(Path(fp).relative_to(Path.cwd())) if fp.startswith(str(Path.cwd())) else fp
                results.append(f"[{kind}: {m['name']} @ {rel}:{ls}]\n```\n{snippet}\n```")
            except Exception:
                results.append(f"[{kind}: {m['name']} @ {fp}:{ls}] {sig}")
        return "\n\n".join(results)
    except Exception as e:
        return f"[symbol: error: {e}]"


_PROVIDERS: Dict[str, Callable] = {
    "codebase": _resolve_codebase,
    "diff": _resolve_diff,
    "terminal": _resolve_terminal,
    "docs": _resolve_docs,
    "web": _resolve_web,
    "symbol": _resolve_symbol,
}


async def resolve_mentions(message: str, core: Any) -> Tuple[str, List[str]]:
    """
    Parse @mentions from user message, resolve each, return (cleaned_message, context_blocks).
    File mentions (@path/to/file) are not handled here — they're handled by existing context logic.
    """
    mentions = _MENTION_RE.findall(message)
    if not mentions:
        return message, []
    context_blocks: List[str] = []
    tasks = []
    for provider_name, query in mentions:
        provider_name = provider_name.lower()
        resolver = _PROVIDERS.get(provider_name)
        if resolver:
            tasks.append(resolver(query.strip(), core))
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                context_blocks.append(f"[context error: {r}]")
            else:
                context_blocks.append(str(r))
    # strip @mention syntax from the message
    cleaned = _MENTION_RE.sub("", message).strip()
    return cleaned, context_blocks
