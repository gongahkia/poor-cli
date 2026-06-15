from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .repo_graph import RepoGraph, RepoGraphError, graph_dependency_report


def build_graph_context(root: Path, query: str, *, max_symbols: int = 8) -> dict[str, Any]:
    report = graph_dependency_report()
    try:
        graph = RepoGraph(root).build_index()
    except RepoGraphError as exc:
        return {
            "schema_version": "poor-cli-graph-context-v1",
            "available": False,
            "warning": str(exc),
            "dependencies": report,
            "query_terms": _terms(query),
            "symbols": [],
            "imports": [],
            "callers": [],
        }
    terms = _terms(query)
    symbols = _symbols(graph, terms, max_symbols)
    imports = []
    callers = []
    for symbol in symbols[:3]:
        path = str(symbol["path"])
        try:
            imports.append(graph.imports_of(path))
        except RepoGraphError:
            pass
        callers.extend(graph.callers_of(str(symbol["name"]), max_results=3))
    return {
        "schema_version": "poor-cli-graph-context-v1",
        "available": True,
        "warning": "",
        "dependencies": report,
        "query_terms": terms,
        "module_count": len(graph.modules),
        "symbols": symbols,
        "imports": imports[:5],
        "callers": callers[:8],
    }


def graph_context_text(context: dict[str, Any]) -> str:
    if not context.get("available"):
        warning = str(context.get("warning") or "graph unavailable")
        return f"Graph context: unavailable; fallback to grep/manual context. Warning: {warning}"
    lines = [f"Graph context: {context.get('module_count', 0)} indexed modules."]
    for symbol in context.get("symbols", [])[:8]:
        scope = f"{symbol.get('scope')}." if symbol.get("scope") else ""
        lines.append(f"- symbol {scope}{symbol.get('name')} {symbol.get('kind')} {symbol.get('path')}:{symbol.get('line_start')}")
    for row in context.get("imports", [])[:3]:
        imports = ", ".join(str(item) for item in row.get("imports", [])[:6])
        if imports:
            lines.append(f"- imports {row.get('path')}: {imports}")
    for row in context.get("callers", [])[:5]:
        lines.append(f"- caller {row.get('path')} calls {row.get('calls')} x{row.get('call_count')}")
    return "\n".join(lines)


def _symbols(graph: RepoGraph, terms: list[str], max_symbols: int) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, int]] = set()
    out = []
    for term in terms or [""]:
        for symbol in graph.find_symbol(term, max_results=max_symbols):
            key = (str(symbol["path"]), str(symbol["name"]), int(symbol["line_start"]))
            if key in seen:
                continue
            seen.add(key)
            out.append(symbol)
            if len(out) >= max_symbols:
                return out
    return out


def _terms(query: str) -> list[str]:
    terms = []
    for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query):
        lowered = raw.lower()
        if lowered in {"the", "and", "for", "with", "from", "that", "this", "into", "through"}:
            continue
        terms.append(raw)
    return terms[:12]
