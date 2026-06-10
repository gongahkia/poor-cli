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
_TOKEN_MENTION_RE = re.compile(r"@(file|buffer|lsp):([^\s`]+)", re.IGNORECASE)
_MAX_TOKEN_FILE_CHARS = 20000


def _repo_root(core: Any) -> Path:
    root = getattr(core, "_repo_root", None)
    return Path(root).expanduser().resolve() if root else Path.cwd().resolve()


def _safe_resolve_path(raw_path: str, core: Any) -> Optional[Path]:
    root = _repo_root(core)
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except Exception:
        return None
    return resolved


def _path_lang(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "lua": "lua",
        "md": "markdown",
        "rs": "rust",
        "go": "go",
    }.get(suffix, suffix)


def _split_path_range(raw_target: str) -> Tuple[str, Optional[Tuple[int, int]]]:
    match = re.match(r"^(.+?):(\d+)(?:-(\d+))?$", raw_target)
    if not match:
        return raw_target, None
    start = int(match.group(2))
    end = int(match.group(3) or match.group(2))
    return match.group(1), (min(start, end), max(start, end))


def _read_file_block(kind: str, raw_target: str, core: Any) -> str:
    raw_path, line_range = _split_path_range(raw_target)
    path = _safe_resolve_path(raw_path, core)
    if path is None:
        return f"[{kind}: path outside workspace: {raw_path}]"
    if not path.is_file():
        return f"[{kind}: not found: {raw_path}]"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return f"[{kind}: read failed: {raw_path}: {e}]"
    lines = text.splitlines()
    range_label = ""
    if line_range is not None:
        start, end = line_range
        lines = lines[max(start - 1, 0):end]
        range_label = f":{start}" if start == end else f":{start}-{end}"
    content = "\n".join(lines)
    if len(content) > _MAX_TOKEN_FILE_CHARS:
        content = content[:_MAX_TOKEN_FILE_CHARS] + "\n... [truncated]"
    try:
        display = str(path.relative_to(_repo_root(core)))
    except ValueError:
        display = str(path)
    lang = _path_lang(path)
    fence = f"```{lang}" if lang else "```"
    return f"[{kind}: {display}{range_label}]\n{fence}\n{content}\n```"


def _read_lsp_block(raw_target: str, core: Any) -> str:
    raw_path, line_range = _split_path_range(raw_target)
    if line_range is None:
        return f"[lsp: missing line: {raw_target}]"
    start, _ = line_range
    return _read_file_block("lsp", f"{raw_path}:{start}", core)


async def _resolve_token_mentions(message: str, core: Any) -> Tuple[str, List[str]]:
    blocks: List[str] = []

    def replace(match: re.Match[str]) -> str:
        kind = match.group(1).lower()
        target = match.group(2)
        if kind == "lsp":
            blocks.append(_read_lsp_block(target, core))
        else:
            blocks.append(_read_file_block(kind, target, core))
        return ""

    cleaned = _TOKEN_MENTION_RE.sub(replace, message).strip()
    return cleaned, blocks


async def _resolve_codebase(query: str, core: Any) -> str:
    """@codebase <query> — semantic search over indexed repo."""
    normalized = query.strip()
    repo_graph = getattr(core, "_repo_graph", None)
    if repo_graph is not None and (not normalized or normalized.lower() in {"map", "repo-map", "workspace-map", "overview"}):
        try:
            return "[workspace map]\n" + repo_graph.build_repo_summary()
        except Exception as e:
            return f"[codebase: repo map failed: {e}]"
    if not normalized:
        return "[codebase: no query provided]"
    if hasattr(core, "tool_registry") and core.tool_registry:
        try:
            result = await core.tool_registry.execute_tool("semantic_search", {"query": normalized})
            return f"[codebase search: {normalized}]\n{result}"
        except Exception:
            pass
    # fallback: grep
    try:
        result = await core.tool_registry.execute_tool("grep_files", {"pattern": normalized, "max_results": 10})
        return f"[codebase grep: {normalized}]\n{result}"
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
    """
    context_blocks: List[str] = []
    message, token_blocks = await _resolve_token_mentions(message, core)
    context_blocks.extend(token_blocks)
    mentions = _MENTION_RE.findall(message)
    if not mentions:
        return message, context_blocks
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


# ── delta-based context construction ────────────────────────────────────


async def build_context_with_delta(
    message: str,
    core: Any,
    context_files: Optional[Dict[str, str]] = None,
    full_history_tokens: int = 0,
) -> Tuple[str, Dict[str, Any]]:
    """Build context using delta mode when available, falling back to full history.
    Returns (enriched_message, delta_info).
    delta_info contains: mode, metrics, and whether caller should use full history.
    """
    from .working_memory import WorkingMemoryManager
    wm_mgr: Optional[WorkingMemoryManager] = getattr(core, "_working_memory_mgr", None)
    if wm_mgr is None or wm_mgr.memory is None:
        return message, {"mode": "full", "use_full_history": True}
    # resolve @mentions first (always needed)
    cleaned, mention_blocks = await resolve_mentions(message, core)
    if mention_blocks:
        cleaned = cleaned + "\n\n" + "\n\n".join(mention_blocks)
    # compute context pressure
    max_ctx = getattr(core, "_max_context_tokens", 100_000)
    pressure = full_history_tokens / max_ctx if max_ctx > 0 else 0.0
    # get current active files
    files = context_files or {}
    # run working memory pre-turn
    tool_results = getattr(core, "_last_tool_results", None)
    delta_prompt, metrics = wm_mgr.pre_turn(
        user_message=cleaned,
        current_files=files,
        context_pressure=pressure,
        full_history_tokens=full_history_tokens,
        tool_results=tool_results,
    )
    if not delta_prompt: # full history or recovery mode
        return cleaned, {"mode": metrics.mode, "use_full_history": True, "metrics": metrics}
    # delta mode: return the delta prompt instead of full history
    return delta_prompt, {"mode": "delta", "use_full_history": False, "metrics": metrics}
