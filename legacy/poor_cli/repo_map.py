from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .repo_graph import RepoGraph
from .token_counter import get_token_counter


@dataclass(frozen=True)
class SymbolEntry:
    name: str
    kind: str
    path: str
    line: int
    signature: str
    docstring: str
    tokens: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileSkeleton:
    path: str
    language: str
    top_symbols: List[SymbolEntry]
    total_lines: int
    skeleton_tokens: int
    full_tokens: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "top_symbols": [symbol.to_dict() for symbol in self.top_symbols],
            "topSymbols": [symbol.to_dict() for symbol in self.top_symbols],
            "total_lines": self.total_lines,
            "totalLines": self.total_lines,
            "skeleton_tokens": self.skeleton_tokens,
            "skeletonTokens": self.skeleton_tokens,
            "full_tokens": self.full_tokens,
            "fullTokens": self.full_tokens,
        }


class RepoMap:
    def __init__(self, repo_root: Path, graph: Optional[RepoGraph] = None):
        self.repo_root = repo_root.resolve()
        self.graph = graph or RepoGraph(self.repo_root)

    def skeleton_for(self, path: str) -> Optional[FileSkeleton]:
        self._ensure_graph()
        resolved = self._resolve_path(path)
        if not resolved.exists() or not resolved.is_file():
            return None
        rel_path = self._relative_path(resolved)
        symbols_payload = self.graph.repo_map_symbols(str(resolved), limit=40)
        symbols = [
            self._symbol_from_row(row, rel_path)
            for row in symbols_payload.get("symbols", [])
            if isinstance(row, dict)
        ][:24]
        language = self._language_for(symbols_payload, resolved)
        content = resolved.read_text(encoding="utf-8", errors="ignore")
        rendered = self.render_skeleton(rel_path, language, symbols, len(content.splitlines()))
        return FileSkeleton(
            path=rel_path,
            language=language,
            top_symbols=symbols,
            total_lines=len(content.splitlines()),
            skeleton_tokens=get_token_counter().count(rendered).count,
            full_tokens=get_token_counter().count(content).count,
        )

    def hot_symbols(self, query: str, limit: int = 30) -> List[SymbolEntry]:
        self._ensure_graph()
        terms = [term for term in _query_terms(query) if term]
        if not terms:
            paths = [path for path, _score in self.graph.top_k(limit)]
            symbols: List[SymbolEntry] = []
            for path in paths:
                skeleton = self.skeleton_for(path)
                if skeleton:
                    symbols.extend(skeleton.top_symbols[:3])
                if len(symbols) >= limit:
                    return symbols[:limit]
            return symbols[:limit]
        seen: set[tuple[str, str, int]] = set()
        matches: List[SymbolEntry] = []
        for term in terms:
            for row in self.graph.symbols_matching(term, limit=max(limit * 2, 20)):
                rel_path = self._relative_path(Path(str(row.get("file_path", ""))))
                entry = self._symbol_from_row(row, rel_path)
                key = (entry.path, entry.name, entry.line)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(entry)
        matches.sort(key=lambda item: (0 if any(term in item.name.lower() for term in terms) else 1, item.path, item.line))
        return matches[: max(0, int(limit or 0))]

    def diff_relevant_skeletons(self, changed_files: List[str], k_neighbors: int = 5) -> List[FileSkeleton]:
        self._ensure_graph()
        results: List[FileSkeleton] = []
        seen: set[str] = set()
        for changed in changed_files:
            skeleton = self.skeleton_for(changed)
            if skeleton and skeleton.path not in seen:
                results.append(skeleton)
                seen.add(skeleton.path)
            expanded = self.graph.repo_map_expand(changed)
            neighbors = list(expanded.get("imports", [])) + list(expanded.get("imported_by", []))
            neighbors.sort(key=lambda row: (-float(row.get("weight", 0) or 0), str(row.get("relative_path") or row.get("path") or "")))
            for row in neighbors[: max(0, int(k_neighbors or 0))]:
                candidate = str(row.get("relative_path") or row.get("path") or "")
                if not candidate:
                    continue
                neighbor = self.skeleton_for(candidate)
                if neighbor and neighbor.path not in seen:
                    results.append(neighbor)
                    seen.add(neighbor.path)
        return results

    def estimate_savings(self, requested_paths: List[str]) -> Dict[str, int]:
        tokens_if_read = 0
        tokens_if_map = 0
        for path in requested_paths:
            skeleton = self.skeleton_for(path)
            if skeleton is None:
                continue
            tokens_if_read += skeleton.full_tokens
            tokens_if_map += skeleton.skeleton_tokens
        return {
            "tokensIfRead": tokens_if_read,
            "tokensIfMap": tokens_if_map,
            "tokensSaved": max(0, tokens_if_read - tokens_if_map),
        }

    @staticmethod
    def render_skeleton(path: str, language: str, symbols: List[SymbolEntry], total_lines: int) -> str:
        lines = [
            f"### {path} [repo_map]",
            f"language: {language or 'text'} | lines: {total_lines}",
            "Use repo_map_query or read_file to expand exact implementation when needed.",
        ]
        if symbols:
            lines.append("symbols:")
            for symbol in symbols:
                sig = f" {symbol.signature}" if symbol.signature else ""
                lines.append(f"- {symbol.kind} {symbol.name}{sig} @ line {symbol.line}")
        else:
            lines.append("symbols: none indexed")
        return "\n".join(lines) + "\n"

    def _ensure_graph(self) -> None:
        stats = self.graph.get_stats() if hasattr(self.graph, "get_stats") else {}
        if int(stats.get("files", 0) or 0) <= 0:
            self.graph.build_index()

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(str(path))
        return candidate.resolve() if candidate.is_absolute() else (self.repo_root / candidate).resolve()

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repo_root))
        except Exception:
            return str(path)

    def _language_for(self, symbols_payload: Dict[str, Any], path: Path) -> str:
        language = str(symbols_payload.get("language") or "")
        if language:
            return language
        suffix = path.suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
        }.get(suffix, suffix.lstrip(".") or "text")

    def _symbol_from_row(self, row: Dict[str, Any], rel_path: str) -> SymbolEntry:
        signature = " ".join(str(row.get("signature") or "").split())[:160]
        line = int(row.get("line_start") or row.get("line") or 0)
        text = f"{row.get('kind', '')} {row.get('name', '')} {signature}"
        return SymbolEntry(
            name=str(row.get("name") or ""),
            kind=str(row.get("kind") or "symbol"),
            path=rel_path,
            line=line,
            signature=signature,
            docstring="",
            tokens=get_token_counter().count(text).count,
        )


def _query_terms(query: str) -> List[str]:
    raw = str(query or "").replace("_", " ").replace("-", " ").replace("/", " ")
    return [term.lower() for term in raw.split() if len(term.strip()) >= 2]
