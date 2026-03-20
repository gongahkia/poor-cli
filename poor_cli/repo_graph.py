"""Repo knowledge graph: file/symbol/edge index with unix tool acceleration."""

from __future__ import annotations
import ast
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

_ANIMATION_WIDTH = 50

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".git", ".poor-cli", "node_modules", "target", "dist", "build",
              "__pycache__", ".venv", "venv", ".mypy_cache", ".ruff_cache",
              ".tox", ".eggs", "*.egg-info"}
_MAX_FILES = 10000
_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".rb": "ruby", ".sh": "shell", ".toml": "toml",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".md": "markdown",
}
_IMPORT_PATTERNS = {
    "python": [r'^import\s+(\w+)', r'^from\s+(\w+(?:\.\w+)*)\s+import'],
    "javascript": [r'import\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]', r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'],
    "typescript": [r'import\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]', r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'],
    "go": [r'import\s+[\'"]([^\'"]+)[\'"]', r'import\s+\([^)]*[\'"]([^\'"]+)[\'"]'],
    "rust": [r'use\s+([\w:]+)', r'mod\s+(\w+)'],
    "java": [r'import\s+([\w.]+)'],
    "c": [r'#include\s*[<"]([^>"]+)[>"]'],
    "cpp": [r'#include\s*[<"]([^>"]+)[>"]'],
}
_SYMBOL_PATTERNS = {
    "python": [
        (r'^\s*(?:async\s+)?def\s+(\w+)', "function"),
        (r'^\s*class\s+(\w+)', "class"),
    ],
    "javascript": [
        (r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', "function"),
        (r'(?:export\s+)?class\s+(\w+)', "class"),
        (r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', "function"),
    ],
    "typescript": [
        (r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', "function"),
        (r'(?:export\s+)?class\s+(\w+)', "class"),
        (r'(?:export\s+)?interface\s+(\w+)', "type"),
        (r'(?:export\s+)?type\s+(\w+)', "type"),
        (r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', "function"),
    ],
    "go": [
        (r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)', "function"),
        (r'type\s+(\w+)\s+struct', "class"),
        (r'type\s+(\w+)\s+interface', "type"),
    ],
    "rust": [
        (r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', "function"),
        (r'(?:pub\s+)?struct\s+(\w+)', "class"),
        (r'(?:pub\s+)?enum\s+(\w+)', "type"),
        (r'(?:pub\s+)?trait\s+(\w+)', "type"),
        (r'impl(?:<[^>]*>)?\s+(\w+)', "class"),
    ],
    "java": [
        (r'(?:public|private|protected)?\s*(?:static\s+)?(?:[\w<>\[\]]+)\s+(\w+)\s*\(', "function"),
        (r'(?:public\s+)?class\s+(\w+)', "class"),
        (r'(?:public\s+)?interface\s+(\w+)', "type"),
    ],
}


class RepoGraph:
    """Lightweight repo knowledge graph stored in SQLite."""

    def __init__(self, repo_root: Path, db_dir: Optional[Path] = None):
        self.repo_root = repo_root.resolve()
        self._db_dir = db_dir or (self.repo_root / ".poor-cli")
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / "repo_graph.db"
        self._tools: Dict[str, Optional[str]] = {}
        self._repo_summary_cache: Optional[str] = None
        self._detect_tools()
        self._init_db()

    def _detect_tools(self) -> None:
        for tool in ("rg", "fd", "tree", "ctags"):
            self._tools[tool] = shutil.which(tool)
        available = [k for k, v in self._tools.items() if v]
        logger.info("repo-graph tools: %s", ", ".join(available) or "none (python fallback)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'text',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    mtime REAL NOT NULL DEFAULT 0,
                    indexed_at REAL NOT NULL DEFAULT 0,
                    symbol_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL REFERENCES files(path),
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    scope TEXT DEFAULT '',
                    signature TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_path);
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    UNIQUE(source_path, target_path, edge_type)
                );
                CREATE INDEX IF NOT EXISTS idx_edge_src ON edges(source_path);
                CREATE INDEX IF NOT EXISTS idx_edge_tgt ON edges(target_path);
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

    # -- discovery --------------------------------------------------------

    def _discover_files(self) -> List[Tuple[str, str]]:
        """Return list of (abs_path, rel_path) for indexable files."""
        if self._tools["fd"]:
            try:
                excludes = []
                for d in _SKIP_DIRS:
                    excludes += ["--exclude", d]
                result = subprocess.run(
                    ["fd", "--type", "f", "--hidden", "--no-ignore"] + excludes + [".", str(self.repo_root)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    paths = []
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        abs_p = str(Path(line).resolve())
                        try:
                            rel_p = str(Path(abs_p).relative_to(self.repo_root))
                        except ValueError:
                            rel_p = abs_p
                        paths.append((abs_p, rel_p))
                        if len(paths) >= _MAX_FILES:
                            break
                    return paths
            except Exception:
                pass
        # fallback: os.walk
        paths = []
        for root, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [d for d in sorted(dirnames) if d not in _SKIP_DIRS]
            for f in sorted(filenames):
                full = Path(root) / f
                if not full.is_file():
                    continue
                abs_p = str(full.resolve())
                try:
                    rel_p = str(full.resolve().relative_to(self.repo_root))
                except ValueError:
                    rel_p = abs_p
                paths.append((abs_p, rel_p))
                if len(paths) >= _MAX_FILES:
                    return paths
        return paths

    def _get_tree(self) -> Optional[str]:
        """Get directory tree string if `tree` available."""
        if not self._tools["tree"]:
            return None
        try:
            excludes = "|".join(_SKIP_DIRS)
            result = subprocess.run(
                ["tree", "-I", excludes, "--noreport", "-L", "3", str(self.repo_root)],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout if result.returncode == 0 else None
        except Exception:
            return None

    # -- symbol extraction ------------------------------------------------

    def _extract_symbols_ctags(self, files: List[Tuple[str, str]]) -> Dict[str, List[Dict]]:
        """Use universal-ctags JSON output for symbol extraction."""
        if not self._tools["ctags"]:
            return {}
        try:
            result = subprocess.run(
                ["ctags", "--output-format=json", "--fields=+neS", "-R", str(self.repo_root)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return {}
        except Exception:
            return {}
        by_file: Dict[str, List[Dict]] = defaultdict(list)
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                import json
                entry = json.loads(line)
            except Exception:
                continue
            path = entry.get("path", "")
            if not path:
                continue
            abs_path = str((self.repo_root / path).resolve())
            kind_map = {"function": "function", "class": "class", "method": "method",
                        "variable": "variable", "member": "variable", "struct": "class",
                        "interface": "type", "type": "type", "enum": "type",
                        "module": "module", "namespace": "module", "trait": "type"}
            kind = kind_map.get(entry.get("kind", ""), entry.get("kind", "variable"))
            by_file[abs_path].append({
                "name": entry.get("name", ""),
                "kind": kind,
                "line_start": entry.get("line", 0),
                "line_end": entry.get("end", entry.get("line", 0)),
                "scope": entry.get("scope", ""),
                "signature": entry.get("signature", ""),
            })
        return by_file

    def _extract_symbols_python_ast(self, abs_path: str, content: str) -> List[Dict]:
        """Extract symbols from Python via ast."""
        syms: List[Dict] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return syms
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                syms.append({"name": node.name, "kind": "function",
                             "line_start": node.lineno, "line_end": node.end_lineno or node.lineno,
                             "scope": "", "signature": ""})
            elif isinstance(node, ast.ClassDef):
                syms.append({"name": node.name, "kind": "class",
                             "line_start": node.lineno, "line_end": node.end_lineno or node.lineno,
                             "scope": "", "signature": ""})
        return syms

    def _extract_symbols_regex(self, abs_path: str, content: str, lang: str) -> List[Dict]:
        """Regex-based symbol extraction for non-Python files."""
        syms: List[Dict] = []
        patterns = _SYMBOL_PATTERNS.get(lang, [])
        if not patterns:
            return syms
        for i, line in enumerate(content.splitlines(), 1):
            for pattern, kind in patterns:
                m = re.search(pattern, line)
                if m:
                    syms.append({"name": m.group(1), "kind": kind,
                                 "line_start": i, "line_end": i,
                                 "scope": "", "signature": line.strip()[:120]})
        return syms

    # -- edge building ----------------------------------------------------

    def _resolve_import(self, raw_import: str, source_file: str, all_files: Set[str]) -> Optional[str]:
        """Resolve an import string to an actual file path."""
        source_dir = str(Path(source_file).parent)
        candidates = []
        # direct relative path
        for ext in ("", ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java"):
            candidate = str(Path(source_dir, raw_import.replace(".", "/") + ext).resolve())
            candidates.append(candidate)
            # also try without dots→slashes for simple names
            candidate2 = str(Path(source_dir, raw_import + ext).resolve())
            candidates.append(candidate2)
        # from repo root
        for ext in ("", ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java"):
            candidate = str((self.repo_root / (raw_import.replace(".", "/") + ext)).resolve())
            candidates.append(candidate)
        # __init__.py for Python packages
        candidates.append(str((self.repo_root / raw_import.replace(".", "/") / "__init__.py").resolve()))
        for c in candidates:
            if c in all_files and c != source_file:
                return c
        return None

    def _build_edges(self, file_records: Dict[str, str], all_files: Set[str]) -> List[Tuple[str, str, str, float]]:
        """Build import edges. file_records: {abs_path: content}."""
        edges: List[Tuple[str, str, str, float]] = []
        seen: Set[Tuple[str, str]] = set()
        for abs_path, content in file_records.items():
            lang = _LANG_MAP.get(Path(abs_path).suffix.lower(), "")
            patterns = _IMPORT_PATTERNS.get(lang, [])
            if not patterns:
                continue
            for line in content.splitlines():
                for pattern in patterns:
                    for m in re.finditer(pattern, line):
                        raw = m.group(1)
                        target = self._resolve_import(raw, abs_path, all_files)
                        if target and (abs_path, target) not in seen:
                            seen.add((abs_path, target))
                            edges.append((abs_path, target, "imports", 1.0))
        return edges

    # -- cross-reference edges via rg -------------------------------------

    def _build_reference_edges(self, top_symbols: List[str], all_files: Set[str]) -> List[Tuple[str, str, str, float]]:
        """Use rg to find cross-file references for high-frequency symbols."""
        if not self._tools["rg"] or not top_symbols:
            return []
        edges: List[Tuple[str, str, str, float]] = []
        seen: Set[Tuple[str, str]] = set()
        for sym_name in top_symbols[:30]: # cap to avoid slow indexing
            try:
                result = subprocess.run(
                    ["rg", "-l", "--no-heading", "-w", sym_name, str(self.repo_root)],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode != 0:
                    continue
                ref_files = [str(Path(f.strip()).resolve()) for f in result.stdout.splitlines() if f.strip()]
                ref_files = [f for f in ref_files if f in all_files]
                for i, f1 in enumerate(ref_files):
                    for f2 in ref_files[i + 1:]:
                        if (f1, f2) not in seen:
                            seen.add((f1, f2))
                            edges.append((f1, f2, "references", 0.3))
            except Exception:
                continue
        return edges

    # -- main indexing ----------------------------------------------------

    def build_index(self, on_progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """Full repo index. Returns stats dict."""
        t0 = time.time()
        emit = on_progress or (lambda _: None)
        emit("scanning files...")
        discovered = self._discover_files()
        emit(f"found {len(discovered)} files")
        with self._connect() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM symbols")
            conn.execute("DELETE FROM files")
        # read file contents + index
        file_contents: Dict[str, str] = {}
        all_files: Set[str] = set()
        sym_total = 0
        # try ctags first
        ctags_syms = self._extract_symbols_ctags(discovered)
        emit("extracting symbols...")
        with self._connect() as conn:
            for abs_path, rel_path in discovered:
                lang = _LANG_MAP.get(Path(abs_path).suffix.lower(), "text")
                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue
                all_files.add(abs_path)
                # read content for edge building (only code files, cap size)
                content = ""
                if lang not in ("text", "markdown", "json", "yaml", "toml") and stat.st_size < 200_000:
                    try:
                        with open(abs_path, "r", errors="replace") as f:
                            content = f.read()
                    except Exception:
                        pass
                if content:
                    file_contents[abs_path] = content
                # symbols
                syms = ctags_syms.get(abs_path, [])
                if not syms and content:
                    if lang == "python":
                        syms = self._extract_symbols_python_ast(abs_path, content)
                    else:
                        syms = self._extract_symbols_regex(abs_path, content, lang)
                conn.execute(
                    "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
                    (abs_path, rel_path, lang, stat.st_size, stat.st_mtime, time.time(), len(syms)),
                )
                for sym in syms:
                    conn.execute(
                        "INSERT INTO symbols (file_path, name, kind, line_start, line_end, scope, signature) VALUES (?,?,?,?,?,?,?)",
                        (abs_path, sym["name"], sym["kind"], sym.get("line_start"), sym.get("line_end"),
                         sym.get("scope", ""), sym.get("signature", "")),
                    )
                sym_total += len(syms)
        emit(f"extracted {sym_total} symbols")
        # build import edges
        emit("building dependency edges...")
        import_edges = self._build_edges(file_contents, all_files)
        # cross-ref edges via rg
        top_syms = self._get_top_symbols(20)
        ref_edges = self._build_reference_edges(top_syms, all_files)
        all_edges = import_edges + ref_edges
        with self._connect() as conn:
            for src, tgt, etype, w in all_edges:
                conn.execute(
                    "INSERT OR IGNORE INTO edges (source_path, target_path, edge_type, weight) VALUES (?,?,?,?)",
                    (src, tgt, etype, w),
                )
        emit(f"built {len(all_edges)} edges")
        self._store_index_metadata()
        self.invalidate_summary_cache()
        duration_ms = int((time.time() - t0) * 1000)
        dir_count = self._count_directories()
        stats = {"files": len(discovered), "symbols": sym_total, "edges": len(all_edges), "duration_ms": duration_ms}
        emit(f"indexing complete: {dir_count} directories, {len(discovered)} files in {duration_ms}ms")
        return stats

    def _get_top_symbols(self, limit: int = 20) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, COUNT(*) as cnt FROM symbols WHERE kind IN ('function','class','type') GROUP BY name ORDER BY cnt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["name"] for r in rows]

    def incremental_update(self, on_progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """Incremental re-index: only changed/new/deleted files."""
        emit = on_progress or (lambda _: None)
        with self._connect() as conn:
            existing = {r["path"]: r["mtime"] for r in conn.execute("SELECT path, mtime FROM files").fetchall()}
        if not existing: # no index yet → full build
            return self.build_index(on_progress)
        emit("checking for changes...")
        discovered = self._discover_files()
        current_files = {abs_p: rel_p for abs_p, rel_p in discovered}
        # deleted
        deleted = set(existing.keys()) - set(current_files.keys())
        # changed or new
        changed: List[Tuple[str, str]] = []
        for abs_p, rel_p in discovered:
            try:
                mtime = os.stat(abs_p).st_mtime
            except OSError:
                continue
            if abs_p not in existing or existing[abs_p] != mtime:
                changed.append((abs_p, rel_p))
        if not changed and not deleted:
            totals = self.get_stats()
            dir_count = self._count_directories()
            emit(f"index up to date: {dir_count} directories, {totals['files']} files, {totals['symbols']} symbols, {totals['edges']} edges")
            return {"files": 0, "symbols": 0, "edges": 0, "duration_ms": 0}
        emit(f"re-indexing {len(changed)} changed, removing {len(deleted)} deleted")
        t0 = time.time()
        with self._connect() as conn:
            for d in deleted:
                conn.execute("DELETE FROM symbols WHERE file_path = ?", (d,))
                conn.execute("DELETE FROM edges WHERE source_path = ? OR target_path = ?", (d, d))
                conn.execute("DELETE FROM files WHERE path = ?", (d,))
        # re-index changed files
        ctags_syms = self._extract_symbols_ctags(changed) if self._tools["ctags"] else {}
        all_files = set(current_files.keys())
        file_contents: Dict[str, str] = {}
        sym_total = 0
        with self._connect() as conn:
            for abs_path, rel_path in changed:
                lang = _LANG_MAP.get(Path(abs_path).suffix.lower(), "text")
                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue
                content = ""
                if lang not in ("text", "markdown", "json", "yaml", "toml") and stat.st_size < 200_000:
                    try:
                        with open(abs_path, "r", errors="replace") as f:
                            content = f.read()
                    except Exception:
                        pass
                if content:
                    file_contents[abs_path] = content
                conn.execute("DELETE FROM symbols WHERE file_path = ?", (abs_path,))
                conn.execute("DELETE FROM edges WHERE source_path = ? OR target_path = ?", (abs_path, abs_path))
                syms = ctags_syms.get(abs_path, [])
                if not syms and content:
                    if lang == "python":
                        syms = self._extract_symbols_python_ast(abs_path, content)
                    else:
                        syms = self._extract_symbols_regex(abs_path, content, lang)
                conn.execute(
                    "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
                    (abs_path, rel_path, lang, stat.st_size, stat.st_mtime, time.time(), len(syms)),
                )
                for sym in syms:
                    conn.execute(
                        "INSERT INTO symbols (file_path, name, kind, line_start, line_end, scope, signature) VALUES (?,?,?,?,?,?,?)",
                        (abs_path, sym["name"], sym["kind"], sym.get("line_start"), sym.get("line_end"),
                         sym.get("scope", ""), sym.get("signature", "")),
                    )
                sym_total += len(syms)
        # rebuild edges for changed files only
        import_edges = self._build_edges(file_contents, all_files)
        with self._connect() as conn:
            for src, tgt, etype, w in import_edges:
                conn.execute(
                    "INSERT OR IGNORE INTO edges (source_path, target_path, edge_type, weight) VALUES (?,?,?,?)",
                    (src, tgt, etype, w),
                )
        self._store_index_metadata()
        self.invalidate_summary_cache()
        duration_ms = int((time.time() - t0) * 1000)
        totals = self.get_stats()
        dir_count = self._count_directories()
        stats = {"files": totals["files"], "symbols": totals["symbols"], "edges": totals["edges"], "duration_ms": duration_ms}
        emit(f"incremental update: {dir_count} directories, {totals['files']} files in {duration_ms}ms")
        return stats

    def reindex_file(self, abs_path: str) -> None:
        """Re-index a single file after mutation."""
        abs_path = str(Path(abs_path).resolve())
        try:
            rel_path = str(Path(abs_path).relative_to(self.repo_root))
        except ValueError:
            return
        if not Path(abs_path).exists():
            with self._connect() as conn:
                conn.execute("DELETE FROM symbols WHERE file_path = ?", (abs_path,))
                conn.execute("DELETE FROM edges WHERE source_path = ? OR target_path = ?", (abs_path, abs_path))
                conn.execute("DELETE FROM files WHERE path = ?", (abs_path,))
            return
        lang = _LANG_MAP.get(Path(abs_path).suffix.lower(), "text")
        stat = os.stat(abs_path)
        content = ""
        if lang not in ("text", "markdown", "json", "yaml", "toml") and stat.st_size < 200_000:
            try:
                with open(abs_path, "r", errors="replace") as f:
                    content = f.read()
            except Exception:
                pass
        syms: List[Dict] = []
        if content:
            if lang == "python":
                syms = self._extract_symbols_python_ast(abs_path, content)
            else:
                syms = self._extract_symbols_regex(abs_path, content, lang)
        with self._connect() as conn:
            conn.execute("DELETE FROM symbols WHERE file_path = ?", (abs_path,))
            conn.execute("DELETE FROM edges WHERE source_path = ?", (abs_path,))
            conn.execute(
                "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
                (abs_path, rel_path, lang, stat.st_size, stat.st_mtime, time.time(), len(syms)),
            )
            for sym in syms:
                conn.execute(
                    "INSERT INTO symbols (file_path, name, kind, line_start, line_end, scope, signature) VALUES (?,?,?,?,?,?,?)",
                    (abs_path, sym["name"], sym["kind"], sym.get("line_start"), sym.get("line_end"),
                     sym.get("scope", ""), sym.get("signature", "")),
                )
        # rebuild edges from this file
        if content:
            with self._connect() as conn:
                all_files = {r["path"] for r in conn.execute("SELECT path FROM files").fetchall()}
            import_edges = self._build_edges({abs_path: content}, all_files)
            with self._connect() as conn:
                for src, tgt, etype, w in import_edges:
                    conn.execute(
                        "INSERT OR IGNORE INTO edges (source_path, target_path, edge_type, weight) VALUES (?,?,?,?)",
                        (src, tgt, etype, w),
                    )

    # -- query methods ----------------------------------------------------

    def files_related_to(self, path: str, max_depth: int = 2) -> List[Tuple[str, float]]:
        """BFS over edges from `path`, return [(path, score)] sorted by score desc."""
        path = str(Path(path).resolve())
        visited: Dict[str, float] = {}
        frontier = [(path, 0)]
        with self._connect() as conn:
            while frontier:
                current, depth = frontier.pop(0)
                if current in visited or depth > max_depth:
                    continue
                score = 1.0 / (depth + 1) if depth > 0 else 0 # seed file gets 0
                visited[current] = score
                if depth >= max_depth:
                    continue
                neighbors = conn.execute(
                    "SELECT target_path, weight FROM edges WHERE source_path = ? "
                    "UNION SELECT source_path, weight FROM edges WHERE target_path = ?",
                    (current, current),
                ).fetchall()
                for row in neighbors:
                    if row["target_path"] not in visited:
                        frontier.append((row["target_path"], depth + 1))
        visited.pop(path, None) # exclude seed
        return sorted(visited.items(), key=lambda x: -x[1])

    def symbols_matching(self, query: str, limit: int = 20) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file_path, name, kind, line_start, line_end, scope, signature FROM symbols WHERE name LIKE ? ORDER BY kind, name LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def dependency_chain(self, path: str, direction: str = "both") -> List[Dict]:
        path = str(Path(path).resolve())
        results = []
        with self._connect() as conn:
            if direction in ("upstream", "both"):
                for r in conn.execute(
                    "SELECT target_path as path, edge_type, weight FROM edges WHERE source_path = ?", (path,)
                ).fetchall():
                    results.append({"path": r["path"], "direction": "upstream", "type": r["edge_type"], "weight": r["weight"]})
            if direction in ("downstream", "both"):
                for r in conn.execute(
                    "SELECT source_path as path, edge_type, weight FROM edges WHERE target_path = ?", (path,)
                ).fetchall():
                    results.append({"path": r["path"], "direction": "downstream", "type": r["edge_type"], "weight": r["weight"]})
        return results

    def rank_files_for_query(self, keywords: List[str], limit: int = 24) -> List[Tuple[str, float]]:
        """Rank files by keyword relevance against symbols + paths + graph proximity."""
        scores: Dict[str, float] = defaultdict(float)
        with self._connect() as conn:
            if not keywords: # return structurally important files (high edge count)
                rows = conn.execute("""
                    SELECT path, (
                        SELECT COUNT(*) FROM edges WHERE source_path = path OR target_path = path
                    ) as edge_count, symbol_count FROM files ORDER BY edge_count DESC, symbol_count DESC LIMIT ?
                """, (limit,)).fetchall()
                return [(r["path"], r["edge_count"] + r["symbol_count"] * 0.1) for r in rows]
            for kw in keywords:
                kw_lower = kw.lower()
                # symbol name matches
                sym_rows = conn.execute(
                    "SELECT DISTINCT file_path FROM symbols WHERE name LIKE ?", (f"%{kw}%",)
                ).fetchall()
                for r in sym_rows:
                    scores[r["file_path"]] += 10.0
                # file path matches
                path_rows = conn.execute(
                    "SELECT path FROM files WHERE relative_path LIKE ?", (f"%{kw_lower}%",)
                ).fetchall()
                for r in path_rows:
                    scores[r["path"]] += 5.0
            # boost graph neighbors of matched files
            top_matches = sorted(scores.items(), key=lambda x: -x[1])[:5]
            for match_path, _ in top_matches:
                neighbors = conn.execute(
                    "SELECT target_path FROM edges WHERE source_path = ? "
                    "UNION SELECT source_path FROM edges WHERE target_path = ?",
                    (match_path, match_path),
                ).fetchall()
                for r in neighbors:
                    neighbor_path = r[0]
                    if neighbor_path not in scores:
                        scores[neighbor_path] += 3.0
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return ranked[:limit]

    def get_stats(self) -> Dict[str, int]:
        with self._connect() as conn:
            files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            symbols = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {"files": files, "symbols": symbols, "edges": edges}

    def _count_directories(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(DISTINCT SUBSTR(relative_path, 1, INSTR(relative_path || '/', '/'))) FROM files").fetchone()
        return row[0] if row else 0

    def get_tree_summary(self) -> Optional[str]:
        return self._get_tree()

    # -- smart change detection -------------------------------------------

    def _git_head_hash(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(self.repo_root), timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _git_index_mtime(self) -> Optional[float]:
        git_index = self.repo_root / ".git" / "index"
        try:
            return os.stat(git_index).st_mtime
        except OSError:
            return None

    def _fs_max_mtime(self) -> Optional[float]:
        """Sample max mtime from discovered files for non-git change detection."""
        try:
            discovered = self._discover_files()
            if not discovered:
                return None
            return max(os.stat(p).st_mtime for p, _ in discovered[:200] if os.path.exists(p))
        except Exception:
            return None

    def should_reindex(self) -> str:
        """Return "full", "incremental", or "skip"."""
        with self._connect() as conn:
            rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM index_metadata").fetchall()}
        if not rows: # no prior index
            return "full"
        head = self._git_head_hash()
        git_mtime = self._git_index_mtime()
        if head is None and git_mtime is None: # non-git dir: use filesystem mtime
            stored_fs_mtime = rows.get("fs_max_mtime")
            if stored_fs_mtime is None:
                return "incremental"
            current = self._fs_max_mtime()
            if current is not None and str(current) == stored_fs_mtime:
                return "skip"
            return "incremental"
        stored_head = rows.get("git_head")
        stored_mtime = rows.get("git_index_mtime")
        if head != stored_head:
            return "incremental"
        if stored_mtime is not None and git_mtime is not None:
            if str(git_mtime) != stored_mtime:
                return "incremental"
        return "skip"

    def _store_index_metadata(self) -> None:
        head = self._git_head_hash()
        git_mtime = self._git_index_mtime()
        fs_mtime = self._fs_max_mtime() if head is None else None
        with self._connect() as conn:
            if head is not None:
                conn.execute("INSERT OR REPLACE INTO index_metadata VALUES (?, ?)", ("git_head", head))
            if git_mtime is not None:
                conn.execute("INSERT OR REPLACE INTO index_metadata VALUES (?, ?)", ("git_index_mtime", str(git_mtime)))
            if fs_mtime is not None:
                conn.execute("INSERT OR REPLACE INTO index_metadata VALUES (?, ?)", ("fs_max_mtime", str(fs_mtime)))

    # -- repo summary for LLM --------------------------------------------

    def build_repo_summary(self) -> str:
        """~450 token summary: tree, languages, key modules, key symbols."""
        if self._repo_summary_cache is not None:
            return self._repo_summary_cache
        parts: List[str] = []
        # directory tree (3 levels)
        tree = self._get_tree()
        if tree:
            lines = tree.splitlines()[:40] # cap to avoid blowup
            parts.append("Directory structure:\n```\n" + "\n".join(lines) + "\n```")
        else: # fallback from files table
            with self._connect() as conn:
                rows = conn.execute("SELECT relative_path FROM files ORDER BY relative_path LIMIT 40").fetchall()
            if rows:
                parts.append("Files:\n" + "\n".join(r["relative_path"] for r in rows))
        # language breakdown
        with self._connect() as conn:
            lang_rows = conn.execute(
                "SELECT language, COUNT(*) as cnt FROM files WHERE language != 'text' GROUP BY language ORDER BY cnt DESC LIMIT 8"
            ).fetchall()
        if lang_rows:
            lang_parts = [f"{r['language']}({r['cnt']})" for r in lang_rows]
            parts.append("Languages: " + ", ".join(lang_parts))
        # key modules by edge degree
        with self._connect() as conn:
            mod_rows = conn.execute("""
                SELECT f.relative_path, (
                    SELECT COUNT(*) FROM edges WHERE source_path = f.path OR target_path = f.path
                ) as degree FROM files f ORDER BY degree DESC LIMIT 10
            """).fetchall()
        if mod_rows:
            mod_parts = [f"{r['relative_path']}({r['degree']})" for r in mod_rows if r["degree"] > 0]
            if mod_parts:
                parts.append("Key modules (by connections): " + ", ".join(mod_parts))
        # key symbols by frequency
        with self._connect() as conn:
            sym_rows = conn.execute(
                "SELECT name, kind, COUNT(*) as cnt FROM symbols WHERE kind IN ('function','class','type') "
                "GROUP BY name ORDER BY cnt DESC LIMIT 15"
            ).fetchall()
        if sym_rows:
            sym_parts = [f"{r['name']}[{r['kind']}]" for r in sym_rows]
            parts.append("Key symbols: " + ", ".join(sym_parts))
        summary = "\n\n".join(parts)
        self._repo_summary_cache = summary
        return summary

    def invalidate_summary_cache(self) -> None:
        self._repo_summary_cache = None

    # -- ASCII node animation ---------------------------------------------

    def generate_graph_frames(self, node_labels: Optional[List[str]] = None) -> List[str]:
        """Generate ASCII animation frames for graph indexing progress."""
        if node_labels is None:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT f.relative_path, (
                        SELECT COUNT(*) FROM edges WHERE source_path = f.path OR target_path = f.path
                    ) as degree FROM files f ORDER BY degree DESC LIMIT 8
                """).fetchall()
            node_labels = [Path(r["relative_path"]).stem[:10] for r in rows] if rows else []
        if not node_labels:
            return []
        labels = node_labels[:8]
        mid = len(labels) // 2
        row1, row2 = labels[:mid] or labels[:1], labels[mid:] or labels[-1:]
        def _render_nodes(nodes: List[str], connected: bool) -> str:
            sep = " ─── " if connected else "  ·  "
            return sep.join(f"[{n}]" for n in nodes)
        frames: List[str] = []
        # frames 1-3: nodes appear
        for i in range(1, min(4, len(labels) + 1)):
            visible1 = row1[:i]
            visible2 = row2[:max(0, i - len(row1))]
            line1 = _render_nodes(visible1, False)
            line2 = _render_nodes(visible2, False) if visible2 else ""
            frame = line1 + ("\n" + line2 if line2 else "")
            frames.append(frame)
        # frames 4-6: edges connect
        for i in range(3):
            partial1 = row1[:len(row1) - (2 - i)] if i < 2 else row1
            line1 = _render_nodes(partial1, True)
            line2 = _render_nodes(row2, i >= 1)
            frame = line1 + "\n" + line2
            frames.append(frame)
        # final frame: all connected + stats
        stats = self.get_stats()
        line1 = _render_nodes(row1, True)
        line2 = _render_nodes(row2, True)
        summary_line = f"  {stats['files']} files | {stats['symbols']} symbols | {stats['edges']} edges"
        frames.append(f"{line1}\n{line2}\n{summary_line}")
        return frames
