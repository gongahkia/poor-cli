"""Aider-style repo map backed by tree-sitter, PageRank, and git-aware caching."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .indexer import INDEXABLE_EXTENSIONS, MAX_FILE_SIZE, SKIP_DIRS as INDEXER_SKIP_DIRS

_ANIMATION_WIDTH = 50
_MAX_FILES = 10000
_DEFAULT_MAP_TOKEN_BUDGET = 2000
_MAP_CACHE_FILE = "repo_map_cache.json"
_MAX_REPO_MAP_FILE_SIZE = max(MAX_FILE_SIZE, 500_000)

logger = logging.getLogger(__name__)

_SKIP_DIRS = set(INDEXER_SKIP_DIRS) | {
    "_archived",
    ".eggs",
    "*.egg-info",
}

_LANG_MAP = {
    ".py": "python",
    ".lua": "lua",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".sh": "shell",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
}

_IMPORT_PATTERNS = {
    "python": [r"^\s*import\s+([A-Za-z_][\w.]*)", r"^\s*from\s+([A-Za-z_][\w.]*)\s+import"],
    "lua": [r'require\s*\(\s*["\']([^"\']+)["\']\s*\)'],
    "javascript": [
        r'import\s+.*?\s+from\s+["\']([^"\']+)["\']',
        r'import\s*\(\s*["\']([^"\']+)["\']\s*\)',
        r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ],
    "typescript": [
        r'import\s+.*?\s+from\s+["\']([^"\']+)["\']',
        r'import\s*\(\s*["\']([^"\']+)["\']\s*\)',
        r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ],
    "rust": [r"\buse\s+([A-Za-z_][\w:]*)", r"\bmod\s+([A-Za-z_][\w]*)"],
    "go": [r'import\s+["\']([^"\']+)["\']'],
    "java": [r"import\s+([A-Za-z_][\w.]*)"],
    "c": [r'#include\s*[<"]([^>"]+)[>"]'],
    "cpp": [r'#include\s*[<"]([^>"]+)[>"]'],
}

_SYMBOL_PATTERNS = {
    "python": [
        (r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)", "function"),
        (r"^\s*class\s+([A-Za-z_]\w*)", "class"),
        (r"^([A-Z][A-Z0-9_]*)\s*=", "variable"),
    ],
    "lua": [
        (r"^\s*local\s+function\s+([A-Za-z_]\w*)", "function"),
        (r"^\s*function\s+([A-Za-z_][\w.:]*)", "function"),
        (r"^\s*local\s+([A-Za-z_]\w*)\s*=", "variable"),
    ],
    "javascript": [
        (r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)", "function"),
        (r"(?:export\s+)?class\s+([A-Za-z_]\w*)", "class"),
        (r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s+)?(?:\(|[A-Za-z_]\w*\s*=>)", "function"),
        (r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=", "variable"),
    ],
    "typescript": [
        (r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)", "function"),
        (r"(?:export\s+)?class\s+([A-Za-z_]\w*)", "class"),
        (r"(?:export\s+)?interface\s+([A-Za-z_]\w*)", "type"),
        (r"(?:export\s+)?type\s+([A-Za-z_]\w*)", "type"),
        (r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s+)?(?:\(|[A-Za-z_]\w*\s*=>)", "function"),
        (r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=", "variable"),
    ],
    "rust": [
        (r"(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)", "function"),
        (r"(?:pub\s+)?struct\s+([A-Za-z_]\w*)", "class"),
        (r"(?:pub\s+)?enum\s+([A-Za-z_]\w*)", "type"),
        (r"(?:pub\s+)?trait\s+([A-Za-z_]\w*)", "type"),
        (r"(?:pub\s+)?(?:const|static)\s+([A-Za-z_]\w*)", "variable"),
    ],
    "go": [
        (r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?([A-Za-z_]\w*)", "function"),
        (r"type\s+([A-Za-z_]\w*)\s+struct", "class"),
        (r"type\s+([A-Za-z_]\w*)\s+interface", "type"),
    ],
    "java": [
        (r"(?:public|private|protected)?\s*(?:static\s+)?(?:[\w<>\[\]]+)\s+([A-Za-z_]\w*)\s*\(", "function"),
        (r"(?:public\s+)?class\s+([A-Za-z_]\w*)", "class"),
        (r"(?:public\s+)?interface\s+([A-Za-z_]\w*)", "type"),
    ],
}

_CALL_PATTERNS = {
    "python": [r"\b([A-Za-z_]\w*)\s*\("],
    "lua": [r"\b([A-Za-z_]\w*)\s*\("],
    "javascript": [r"\b([A-Za-z_]\w*)\s*\("],
    "typescript": [r"\b([A-Za-z_]\w*)\s*\("],
    "rust": [r"\b([A-Za-z_]\w*)!\s*\(", r"\b([A-Za-z_]\w*)\s*\("],
}

_TREE_SITTER_MODULES = {
    "python": ("tree_sitter_python", ("language",)),
    "lua": ("tree_sitter_lua", ("language",)),
    "javascript": ("tree_sitter_javascript", ("language",)),
    "typescript": ("tree_sitter_typescript", ("language_typescript", "typescript", "language")),
    "rust": ("tree_sitter_rust", ("language",)),
}

_ROOT_LIKE_NODE_TYPES = {"module", "program", "chunk", "source_file", "export_statement"}
_IDENTIFIER_NODE_TYPES = {
    "identifier",
    "type_identifier",
    "property_identifier",
    "field_identifier",
}
_FUNCTION_VALUE_NODE_TYPES = {
    "arrow_function",
    "function",
    "function_expression",
    "generator_function",
}
_ENTRY_FILE_NAMES = {"main", "__init__", "index", "cli", "server", "core"}
_ENTRY_SYMBOL_NAMES = {"main", "run", "start", "cli", "serve", "execute"}
_LANGUAGE_PRIORITY_BOOST = {
    "python": 0.025,
    "lua": 0.01,
    "typescript": 0.003,
    "javascript": 0.003,
    "rust": 0.0,
}
_CALL_IGNORE_NAMES = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "require",
    "str",
    "int",
    "float",
    "bool",
    "len",
    "print",
}


@dataclass
class ParsedFile:
    abs_path: str
    relative_path: str
    language: str
    size_bytes: int
    mtime: float
    symbols: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)
    inherits: List[str] = field(default_factory=list)


class RepoGraph:
    """Repo knowledge graph persisted in SQLite."""

    def __init__(self, repo_root: Path, db_dir: Optional[Path] = None):
        self.repo_root = repo_root.resolve()
        self._db_dir = db_dir or (self.repo_root / ".poor-cli")
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / "repo_graph.db"
        self._map_cache_path = self._db_dir / _MAP_CACHE_FILE
        self._tools: Dict[str, Optional[str]] = {}
        self._tree_sitter_languages: Dict[str, Any] = {}
        self._repo_summary_cache: Dict[Tuple[str, int], str] = {}
        self._detect_tools()
        self._init_db()

    def _detect_tools(self) -> None:
        for tool in ("rg", "fd", "tree", "git"):
            self._tools[tool] = shutil.which(tool)
        available = [name for name, path in self._tools.items() if path]
        logger.info("repo-graph tools: %s", ", ".join(available) or "none")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
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
                """
            )

    def _discover_files(self) -> List[Tuple[str, str]]:
        results: List[Tuple[str, str]] = []
        if self._tools["fd"]:
            try:
                cmd = ["fd", "--type", "f", "--hidden", "--no-ignore"]
                for skipped in sorted(_SKIP_DIRS):
                    cmd.extend(["--exclude", skipped])
                cmd.extend([".", str(self.repo_root)])
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        if len(results) >= _MAX_FILES:
                            break
                        candidate = Path(line.strip())
                        if not candidate.is_file():
                            continue
                        if candidate.suffix.lower() not in INDEXABLE_EXTENSIONS or candidate.suffix.lower() not in _LANG_MAP:
                            continue
                        if candidate.stat().st_size > _MAX_REPO_MAP_FILE_SIZE:
                            continue
                        abs_path = str(candidate.resolve())
                        rel_path = str(candidate.resolve().relative_to(self.repo_root))
                        results.append((abs_path, rel_path))
                    return results
            except Exception:
                logger.debug("fd discovery failed", exc_info=True)
        for root, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [name for name in sorted(dirnames) if name not in _SKIP_DIRS]
            for filename in sorted(filenames):
                path = Path(root) / filename
                if path.suffix.lower() not in INDEXABLE_EXTENSIONS or path.suffix.lower() not in _LANG_MAP:
                    continue
                try:
                    if path.stat().st_size > _MAX_REPO_MAP_FILE_SIZE:
                        continue
                except OSError:
                    continue
                results.append((str(path.resolve()), str(path.resolve().relative_to(self.repo_root))))
                if len(results) >= _MAX_FILES:
                    return results
        return results

    def _get_tree(self) -> Optional[str]:
        if not self._tools["tree"]:
            return None
        try:
            excludes = "|".join(sorted(_SKIP_DIRS))
            proc = subprocess.run(
                ["tree", "-I", excludes, "--noreport", "-L", "3", str(self.repo_root)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.stdout if proc.returncode == 0 else None
        except Exception:
            logger.debug("tree summary failed", exc_info=True)
            return None

    def _read_text(self, abs_path: str) -> str:
        try:
            return Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def _load_tree_sitter_language(self, language_name: str) -> Any:
        cached = self._tree_sitter_languages.get(language_name)
        if cached is not None:
            return cached
        module_info = _TREE_SITTER_MODULES.get(language_name)
        if module_info is None:
            return None
        try:
            from tree_sitter import Language
        except ImportError:
            return None
        module_name, attrs = module_info
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            return None
        for attr in attrs:
            loader = getattr(module, attr, None)
            if loader is None:
                continue
            try:
                value = loader() if callable(loader) else loader
            except TypeError:
                value = loader
            try:
                if isinstance(value, Language):
                    self._tree_sitter_languages[language_name] = value
                    return value
            except TypeError:
                pass
            try:
                language = Language(value)
            except Exception:
                continue
            self._tree_sitter_languages[language_name] = language
            return language
        return None

    def _new_tree_sitter_parser(self, language_name: str) -> Any:
        language = self._load_tree_sitter_language(language_name)
        if language is None:
            return None
        try:
            from tree_sitter import Parser
        except ImportError:
            return None
        parser = Parser()
        try:
            parser.language = language
        except Exception:
            try:
                parser.set_language(language)
            except Exception:
                return None
        return parser

    def _node_text(self, content_bytes: bytes, node: Any) -> str:
        return content_bytes[node.start_byte:node.end_byte].decode("utf-8", "ignore")

    def _signature_text(self, content_bytes: bytes, node: Any) -> str:
        text = self._node_text(content_bytes, node).strip()
        return text.splitlines()[0].strip()[:160] if text else ""

    def _first_child_of_type(self, node: Any, wanted: Set[str]) -> Any:
        for child in getattr(node, "children", []):
            if child.type in wanted:
                return child
        return None

    def _last_identifier_text(self, content_bytes: bytes, node: Any) -> str:
        if node is None:
            return ""
        if node.type in _IDENTIFIER_NODE_TYPES:
            return self._node_text(content_bytes, node)
        for child in reversed(getattr(node, "children", [])):
            identifier = self._last_identifier_text(content_bytes, child)
            if identifier:
                return identifier
        return ""

    def _strip_quotes(self, value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    def _extract_python_tree_sitter(self, root: Any, content: str) -> Dict[str, Any]:
        payload = {"symbols": [], "imports": [], "calls": [], "inherits": []}
        content_bytes = content.encode("utf-8")

        def visit(node: Any, class_scope: str = "", top_level: bool = True) -> None:
            if node.type == "import_statement":
                import re

                statement = self._node_text(content_bytes, node)
                for match in re.finditer(r"\bimport\s+([A-Za-z_][\w.]*)", statement):
                    payload["imports"].append(match.group(1))
                return
            if node.type == "import_from_statement":
                import re

                statement = self._node_text(content_bytes, node)
                match = re.search(r"from\s+([.\w]+)\s+import", statement)
                if match:
                    payload["imports"].append(match.group(1))
                return
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"identifier"})
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "class",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                    args = self._first_child_of_type(node, {"argument_list"})
                    if args is not None:
                        for child in getattr(args, "children", []):
                            base = self._last_identifier_text(content_bytes, child)
                            if base and base != name:
                                payload["inherits"].append(base)
                block = self._first_child_of_type(node, {"block"})
                for child in getattr(block, "children", []):
                    visit(child, class_scope=name, top_level=False)
                return
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"identifier"})
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "method" if class_scope else "function",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": class_scope,
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                block = self._first_child_of_type(node, {"block"})
                for child in getattr(block, "children", []):
                    visit(child, class_scope=class_scope, top_level=False)
                return
            if top_level and node.type == "assignment":
                left = getattr(node, "children", [None])[0]
                for child in getattr(left, "children", []) if left is not None else []:
                    if child.type == "identifier":
                        payload["symbols"].append(
                            {
                                "name": self._node_text(content_bytes, child),
                                "kind": "variable",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "scope": "",
                                "signature": self._signature_text(content_bytes, node),
                            }
                        )
            if node.type == "call":
                callee = self._last_identifier_text(content_bytes, getattr(node, "children", [None])[0])
                if callee:
                    payload["calls"].append(callee)
            next_top_level = top_level and node.type in _ROOT_LIKE_NODE_TYPES
            for child in getattr(node, "children", []):
                visit(child, class_scope=class_scope, top_level=next_top_level)

        visit(root)
        return payload

    def _extract_js_like_tree_sitter(self, root: Any, content: str, language_name: str) -> Dict[str, Any]:
        payload = {"symbols": [], "imports": [], "calls": [], "inherits": []}
        content_bytes = content.encode("utf-8")

        def visit(node: Any, class_scope: str = "", top_level: bool = True) -> None:
            if node.type == "import_statement":
                string_node = self._first_child_of_type(node, {"string"})
                if string_node is not None:
                    payload["imports"].append(self._strip_quotes(self._node_text(content_bytes, string_node)))
                return
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, _IDENTIFIER_NODE_TYPES)
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "class",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                heritage = self._first_child_of_type(node, {"class_heritage", "extends_clause"})
                if heritage is not None:
                    base = self._last_identifier_text(content_bytes, heritage)
                    if base and base != name:
                        payload["inherits"].append(base)
                body = self._first_child_of_type(node, {"class_body"})
                for child in getattr(body, "children", []):
                    visit(child, class_scope=name, top_level=False)
                return
            if node.type == "method_definition":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"property_identifier", "identifier"})
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "method",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": class_scope,
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                next_top_level = False
                for child in getattr(node, "children", []):
                    visit(child, class_scope=class_scope, top_level=next_top_level)
                return
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"identifier"})
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "function",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
            if language_name == "typescript" and node.type in {"interface_declaration", "type_alias_declaration"}:
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"type_identifier"})
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "type",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                return
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"identifier"})
                value_node = node.child_by_field_name("value")
                if value_node is None:
                    named_children = [child for child in getattr(node, "children", []) if getattr(child, "is_named", False)]
                    value_node = named_children[-1] if len(named_children) > 1 else None
                name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                if name:
                    if value_node is not None and value_node.type in _FUNCTION_VALUE_NODE_TYPES:
                        payload["symbols"].append(
                            {
                                "name": name,
                                "kind": "function",
                                "line_start": node.start_point[0] + 1,
                                "line_end": node.end_point[0] + 1,
                                "scope": "",
                                "signature": self._signature_text(content_bytes, node),
                            }
                        )
                    elif top_level:
                        payload["symbols"].append(
                            {
                                "name": name,
                                "kind": "variable",
                                "line_start": node.start_point[0] + 1,
                                "line_end": node.end_point[0] + 1,
                                "scope": "",
                                "signature": self._signature_text(content_bytes, node),
                            }
                        )
            if node.type == "call_expression":
                callee = self._last_identifier_text(content_bytes, getattr(node, "children", [None])[0])
                if callee == "require":
                    args_node = self._first_child_of_type(node, {"arguments"})
                    string_node = self._first_child_of_type(args_node, {"string"}) if args_node else self._first_child_of_type(node, {"string"})
                    if string_node is not None:
                        payload["imports"].append(self._strip_quotes(self._node_text(content_bytes, string_node)))
                elif callee:
                    payload["calls"].append(callee)
            next_top_level = top_level and node.type in _ROOT_LIKE_NODE_TYPES
            for child in getattr(node, "children", []):
                visit(child, class_scope=class_scope, top_level=next_top_level)

        visit(root)
        return payload

    def _extract_lua_tree_sitter(self, root: Any, content: str) -> Dict[str, Any]:
        payload = {"symbols": [], "imports": [], "calls": [], "inherits": []}
        content_bytes = content.encode("utf-8")

        def visit(node: Any, top_level: bool = True) -> None:
            if node.type == "function_declaration":
                name_node = self._first_child_of_type(node, {"identifier", "dot_index_expression"})
                full_name = self._node_text(content_bytes, name_node) if name_node is not None else ""
                scope = ""
                name = full_name
                for separator in (":", "."):
                    if separator in full_name:
                        scope, name = full_name.rsplit(separator, 1)
                        break
                if name:
                    payload["symbols"].append(
                        {
                            "name": name,
                            "kind": "method" if scope else "function",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": scope,
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
            if top_level and node.type == "variable_declaration":
                assignment = self._first_child_of_type(node, {"assignment_statement"})
                if assignment is not None:
                    variable_list = self._first_child_of_type(assignment, {"variable_list"})
                    for child in getattr(variable_list, "children", []) if variable_list is not None else []:
                        if child.type == "identifier":
                            payload["symbols"].append(
                                {
                                    "name": self._node_text(content_bytes, child),
                                    "kind": "variable",
                                    "line_start": child.start_point[0] + 1,
                                    "line_end": child.end_point[0] + 1,
                                    "scope": "",
                                    "signature": self._signature_text(content_bytes, assignment),
                                }
                            )
            if node.type == "function_call":
                callee = self._last_identifier_text(content_bytes, self._first_child_of_type(node, {"identifier", "dot_index_expression"}))
                if callee == "require":
                    args_node = self._first_child_of_type(node, {"arguments"})
                    string_node = self._first_child_of_type(args_node, {"string"}) if args_node else self._first_child_of_type(node, {"string"})
                    if string_node is not None:
                        payload["imports"].append(self._strip_quotes(self._node_text(content_bytes, string_node)))
                elif callee:
                    payload["calls"].append(callee)
            next_top_level = top_level and node.type in _ROOT_LIKE_NODE_TYPES
            for child in getattr(node, "children", []):
                visit(child, top_level=next_top_level)

        visit(root)
        return payload

    def _extract_rust_tree_sitter(self, root: Any, content: str) -> Dict[str, Any]:
        payload = {"symbols": [], "imports": [], "calls": [], "inherits": []}
        content_bytes = content.encode("utf-8")

        def visit(node: Any, impl_scope: str = "", top_level: bool = True) -> None:
            if node.type == "use_declaration":
                scoped = self._first_child_of_type(node, {"scoped_identifier", "identifier"})
                if scoped is not None:
                    payload["imports"].append(self._node_text(content_bytes, scoped))
                return
            if node.type == "struct_item":
                name_node = self._first_child_of_type(node, {"type_identifier"})
                if name_node is not None:
                    payload["symbols"].append(
                        {
                            "name": self._node_text(content_bytes, name_node),
                            "kind": "class",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                return
            if node.type in {"enum_item", "trait_item"}:
                name_node = self._first_child_of_type(node, {"type_identifier"})
                if name_node is not None:
                    payload["symbols"].append(
                        {
                            "name": self._node_text(content_bytes, name_node),
                            "kind": "type",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
                return
            if node.type == "impl_item":
                scope_node = self._first_child_of_type(node, {"type_identifier", "identifier"})
                scope_name = self._node_text(content_bytes, scope_node) if scope_node is not None else ""
                for child in getattr(node, "children", []):
                    visit(child, impl_scope=scope_name, top_level=False)
                return
            if node.type == "function_item":
                name_node = node.child_by_field_name("name") or self._first_child_of_type(node, {"identifier"})
                if name_node is not None:
                    payload["symbols"].append(
                        {
                            "name": self._node_text(content_bytes, name_node),
                            "kind": "method" if impl_scope else "function",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": impl_scope,
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
            if top_level and node.type in {"const_item", "static_item"}:
                name_node = self._first_child_of_type(node, {"identifier"})
                if name_node is not None:
                    payload["symbols"].append(
                        {
                            "name": self._node_text(content_bytes, name_node),
                            "kind": "variable",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "scope": "",
                            "signature": self._signature_text(content_bytes, node),
                        }
                    )
            if node.type == "call_expression":
                callee = self._last_identifier_text(content_bytes, getattr(node, "children", [None])[0])
                if callee:
                    payload["calls"].append(callee)
            next_top_level = top_level and node.type in _ROOT_LIKE_NODE_TYPES
            for child in getattr(node, "children", []):
                visit(child, impl_scope=impl_scope, top_level=next_top_level)

        visit(root)
        return payload

    def _extract_treesitter_data(self, content: str, language_name: str) -> Optional[Dict[str, Any]]:
        parser = self._new_tree_sitter_parser(language_name)
        if parser is None:
            return None
        try:
            tree = parser.parse(content.encode("utf-8"))
        except Exception:
            logger.debug("tree-sitter parse failed for %s", language_name, exc_info=True)
            return None
        root = tree.root_node
        if language_name == "python":
            return self._extract_python_tree_sitter(root, content)
        if language_name in {"javascript", "typescript"}:
            return self._extract_js_like_tree_sitter(root, content, language_name)
        if language_name == "lua":
            return self._extract_lua_tree_sitter(root, content)
        if language_name == "rust":
            return self._extract_rust_tree_sitter(root, content)
        return None

    def _extract_symbols_treesitter(self, abs_path: str, content: str, lang: str) -> Optional[List[Dict[str, Any]]]:
        del abs_path
        payload = self._extract_treesitter_data(content, lang)
        if payload is None:
            return None
        return payload["symbols"]

    def _extract_python_ast_data(self, content: str) -> Dict[str, Any]:
        payload = {"symbols": [], "imports": [], "calls": [], "inherits": []}

        class Visitor(ast.NodeVisitor):
            def __init__(self, outer: "RepoGraph") -> None:
                self.outer = outer
                self.class_stack: List[str] = []

            def _signature(self, node: ast.AST) -> str:
                snippet = ast.get_source_segment(content, node) or ""
                return snippet.splitlines()[0].strip()[:160]

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    payload["imports"].append(alias.name)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                if node.module:
                    payload["imports"].append("." * int(getattr(node, "level", 0) or 0) + node.module)
                elif getattr(node, "level", 0):
                    payload["imports"].append("." * int(node.level))

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                payload["symbols"].append(
                    {
                        "name": node.name,
                        "kind": "class",
                        "line_start": node.lineno,
                        "line_end": getattr(node, "end_lineno", node.lineno),
                        "scope": "",
                        "signature": self._signature(node),
                    }
                )
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        payload["inherits"].append(base.id)
                    elif isinstance(base, ast.Attribute):
                        payload["inherits"].append(base.attr)
                self.class_stack.append(node.name)
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                payload["symbols"].append(
                    {
                        "name": node.name,
                        "kind": "method" if self.class_stack else "function",
                        "line_start": node.lineno,
                        "line_end": getattr(node, "end_lineno", node.lineno),
                        "scope": self.class_stack[-1] if self.class_stack else "",
                        "signature": self._signature(node),
                    }
                )
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self.visit_FunctionDef(node)

            def visit_Assign(self, node: ast.Assign) -> None:
                if not self.class_stack:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            payload["symbols"].append(
                                {
                                    "name": target.id,
                                    "kind": "variable",
                                    "line_start": node.lineno,
                                    "line_end": getattr(node, "end_lineno", node.lineno),
                                    "scope": "",
                                    "signature": self._signature(node),
                                }
                            )
                self.generic_visit(node)

            def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
                if not self.class_stack and isinstance(node.target, ast.Name):
                    payload["symbols"].append(
                        {
                            "name": node.target.id,
                            "kind": "variable",
                            "line_start": node.lineno,
                            "line_end": getattr(node, "end_lineno", node.lineno),
                            "scope": "",
                            "signature": self._signature(node),
                        }
                    )
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call) -> None:
                if isinstance(node.func, ast.Name):
                    payload["calls"].append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    payload["calls"].append(node.func.attr)
                self.generic_visit(node)

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return payload
        Visitor(self).visit(tree)
        return payload

    def _extract_symbols_python_ast(self, abs_path: str, content: str) -> List[Dict[str, Any]]:
        del abs_path
        return self._extract_python_ast_data(content)["symbols"]

    def _extract_symbols_regex(self, abs_path: str, content: str, lang: str) -> List[Dict[str, Any]]:
        del abs_path
        matches: List[Dict[str, Any]] = []
        for line_number, line in enumerate(content.splitlines(), 1):
            for pattern, kind in _SYMBOL_PATTERNS.get(lang, []):
                import re

                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    scope = ""
                    if lang == "lua" and kind == "function" and "." in name:
                        scope, name = name.rsplit(".", 1)
                    matches.append(
                        {
                            "name": name,
                            "kind": kind,
                            "line_start": line_number,
                            "line_end": line_number,
                            "scope": scope,
                            "signature": line.strip()[:160],
                        }
                    )
        return matches

    def _extract_imports_regex(self, content: str, lang: str) -> List[str]:
        import re

        imports: List[str] = []
        for line in content.splitlines():
            for pattern in _IMPORT_PATTERNS.get(lang, []):
                for match in re.finditer(pattern, line):
                    imports.append(match.group(1))
        return imports

    def _extract_calls_regex(self, content: str, lang: str) -> List[str]:
        import re

        calls: List[str] = []
        for line in content.splitlines():
            for pattern in _CALL_PATTERNS.get(lang, []):
                for match in re.finditer(pattern, line):
                    name = match.group(1)
                    if name not in _CALL_IGNORE_NAMES:
                        calls.append(name)
        return calls

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {"symbols": [], "imports": [], "calls": [], "inherits": []}
        seen_symbols: Set[Tuple[str, str, int, str]] = set()
        for symbol in payload.get("symbols", []):
            name = str(symbol.get("name", "")).strip()
            if not name:
                continue
            key = (
                name,
                str(symbol.get("kind", "symbol")).strip(),
                int(symbol.get("line_start") or 0),
                str(symbol.get("scope", "")).strip(),
            )
            if key in seen_symbols:
                continue
            seen_symbols.add(key)
            normalized["symbols"].append(
                {
                    "name": name,
                    "kind": str(symbol.get("kind", "symbol")).strip() or "symbol",
                    "line_start": int(symbol.get("line_start") or 0),
                    "line_end": int(symbol.get("line_end") or symbol.get("line_start") or 0),
                    "scope": str(symbol.get("scope", "")).strip(),
                    "signature": str(symbol.get("signature", "")).strip()[:160],
                }
            )
        for key in ("imports", "calls", "inherits"):
            seen_values: Set[str] = set()
            for raw_value in payload.get(key, []):
                value = str(raw_value or "").strip()
                if not value:
                    continue
                leaf = value.split("::")[-1].split(".")[-1].strip()
                if key == "calls" and leaf in _CALL_IGNORE_NAMES:
                    continue
                cleaned = leaf if key != "imports" else value
                if cleaned in seen_values:
                    continue
                seen_values.add(cleaned)
                normalized[key].append(cleaned)
        normalized["symbols"].sort(key=lambda item: (item["line_start"], item["name"].lower()))
        return normalized

    def _parse_file(self, abs_path: str, rel_path: str, language_name: str, size_bytes: int, mtime: float) -> ParsedFile:
        content = self._read_text(abs_path)
        payload: Optional[Dict[str, Any]] = None
        if language_name in _TREE_SITTER_MODULES:
            payload = self._extract_treesitter_data(content, language_name)
        if payload is None and language_name == "python":
            payload = self._extract_python_ast_data(content)
        if payload is None:
            payload = {
                "symbols": self._extract_symbols_regex(abs_path, content, language_name),
                "imports": self._extract_imports_regex(content, language_name),
                "calls": self._extract_calls_regex(content, language_name),
                "inherits": [],
            }
        normalized = self._normalize_payload(payload)
        return ParsedFile(
            abs_path=abs_path,
            relative_path=rel_path,
            language=language_name,
            size_bytes=size_bytes,
            mtime=mtime,
            symbols=normalized["symbols"],
            imports=normalized["imports"],
            calls=normalized["calls"],
            inherits=normalized["inherits"],
        )

    def _resolve_import(self, raw_import: str, source_file: str, source_language: str, all_files: Set[str]) -> Optional[str]:
        raw_import = str(raw_import or "").strip().strip("/")
        if not raw_import:
            return None
        normalized = raw_import
        if source_language in {"python", "lua"}:
            normalized = raw_import.lstrip(".").replace(".", "/")
        elif source_language == "rust":
            normalized = raw_import.removeprefix("crate::").removeprefix("self::").replace("::", "/")
        source_dir = Path(source_file).parent
        variants = {normalized, raw_import}
        candidate_roots: List[Path] = []
        if source_language == "python" and raw_import.startswith("."):
            level = len(raw_import) - len(raw_import.lstrip("."))
            module_path = raw_import[level:].replace(".", "/")
            base_dir = source_dir
            for _ in range(max(level - 1, 0)):
                base_dir = base_dir.parent
            candidate_roots.append((base_dir / module_path).resolve() if module_path else base_dir.resolve())
        elif raw_import.startswith("."):
            candidate_roots.append((source_dir / raw_import).resolve())
        for variant in variants:
            candidate_roots.append((source_dir / variant).resolve())
            candidate_roots.append((self.repo_root / variant).resolve())
        extensions = list(_LANG_MAP)
        package_entries = {
            "__init__.py",
            "index.js",
            "index.jsx",
            "index.ts",
            "index.tsx",
            "mod.rs",
        }
        for root in candidate_roots:
            candidates = [root]
            candidates.extend(Path(f"{root}{ext}") for ext in extensions)
            candidates.extend(root / entry for entry in package_entries)
            for candidate in candidates:
                candidate_path = str(candidate.resolve())
                if candidate_path in all_files and candidate_path != source_file:
                    return candidate_path
        return None

    def _build_edges(self, parsed_files: Dict[str, ParsedFile]) -> Dict[Tuple[str, str, str], float]:
        all_files = set(parsed_files)
        symbol_defs: Dict[str, Set[str]] = defaultdict(set)
        for parsed in parsed_files.values():
            for symbol in parsed.symbols:
                if symbol["kind"] in {"function", "method", "class", "type"}:
                    symbol_defs[symbol["name"]].add(parsed.abs_path)
        weights: Dict[Tuple[str, str, str], float] = defaultdict(float)
        for parsed in parsed_files.values():
            for imported in parsed.imports:
                target = self._resolve_import(imported, parsed.abs_path, parsed.language, all_files)
                if target and target != parsed.abs_path:
                    weights[(parsed.abs_path, target, "imports")] += 2.0
            for inherited in parsed.inherits:
                targets = sorted(symbol_defs.get(inherited, set()) - {parsed.abs_path})
                if not targets or len(targets) > 6:
                    continue
                boost = 1.25 / len(targets)
                for target in targets:
                    weights[(parsed.abs_path, target, "inherits")] += boost
            for called in parsed.calls:
                targets = sorted(symbol_defs.get(called, set()) - {parsed.abs_path})
                if not targets or len(targets) > 6:
                    continue
                boost = 1.0 / len(targets)
                for target in targets:
                    weights[(parsed.abs_path, target, "calls")] += boost
        return weights

    def build_index(self, on_progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        emit = on_progress or (lambda _: None)
        started = time.time()
        emit("scanning files...")
        discovered = self._discover_files()
        emit(f"found {len(discovered)} files")
        parsed_files: Dict[str, ParsedFile] = {}
        for abs_path, rel_path in discovered:
            language_name = _LANG_MAP.get(Path(abs_path).suffix.lower(), "text")
            try:
                stat = os.stat(abs_path)
            except OSError:
                continue
            parsed_files[abs_path] = self._parse_file(
                abs_path=abs_path,
                rel_path=rel_path,
                language_name=language_name,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
            )
        emit("building dependency graph...")
        edge_weights = self._build_edges(parsed_files)
        with self._connect() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM symbols")
            conn.execute("DELETE FROM files")
            for parsed in parsed_files.values():
                conn.execute(
                    "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        parsed.abs_path,
                        parsed.relative_path,
                        parsed.language,
                        parsed.size_bytes,
                        parsed.mtime,
                        time.time(),
                        len(parsed.symbols),
                    ),
                )
                for symbol in parsed.symbols:
                    conn.execute(
                        "INSERT INTO symbols (file_path, name, kind, line_start, line_end, scope, signature) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            parsed.abs_path,
                            symbol["name"],
                            symbol["kind"],
                            symbol["line_start"],
                            symbol["line_end"],
                            symbol["scope"],
                            symbol["signature"],
                        ),
                    )
            for (source_path, target_path, edge_type), weight in edge_weights.items():
                conn.execute(
                    "INSERT INTO edges (source_path, target_path, edge_type, weight) VALUES (?, ?, ?, ?)",
                    (source_path, target_path, edge_type, weight),
                )
        self._store_index_metadata()
        self.invalidate_summary_cache()
        self._invalidate_map_cache()
        duration_ms = int((time.time() - started) * 1000)
        emit(f"indexed {len(parsed_files)} files, {sum(len(item.symbols) for item in parsed_files.values())} symbols, {len(edge_weights)} edges")
        return {
            "files": len(parsed_files),
            "symbols": sum(len(item.symbols) for item in parsed_files.values()),
            "edges": len(edge_weights),
            "duration_ms": duration_ms,
        }

    def incremental_update(self, on_progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        emit = on_progress or (lambda _: None)
        emit("repo graph changed; rebuilding index")
        return self.build_index(on_progress)

    def reindex_file(self, abs_path: str) -> None:
        del abs_path
        self.build_index()

    def files_related_to(self, path: str, max_depth: int = 2) -> List[Tuple[str, float]]:
        candidate = Path(path)
        resolved = str(candidate.resolve()) if candidate.is_absolute() else str((self.repo_root / candidate).resolve())
        scores: Dict[str, float] = {}
        with self._connect() as conn:
            queue: deque[Tuple[str, int, float]] = deque([(resolved, 0, 0.0)])
            seen: Set[str] = set()
            while queue:
                current, depth, score = queue.popleft()
                if current in seen or depth > max_depth:
                    continue
                seen.add(current)
                if depth > 0:
                    scores[current] = max(scores.get(current, 0.0), score)
                if depth == max_depth:
                    continue
                neighbors = conn.execute(
                    """
                    SELECT target_path AS path, weight FROM edges WHERE source_path = ?
                    UNION ALL
                    SELECT source_path AS path, weight FROM edges WHERE target_path = ?
                    """,
                    (current, current),
                ).fetchall()
                for row in neighbors:
                    next_score = max(score, 1.0 / (depth + 1)) + float(row["weight"]) * 0.05
                    queue.append((row["path"], depth + 1, next_score))
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))

    def symbols_matching(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT file_path, name, kind, line_start, line_end, scope, signature
                FROM symbols
                WHERE name LIKE ?
                ORDER BY name, line_start
                LIMIT ?
                """,
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def dependency_chain(self, path: str, direction: str = "both") -> List[Dict[str, Any]]:
        candidate = Path(path)
        resolved = str(candidate.resolve()) if candidate.is_absolute() else str((self.repo_root / candidate).resolve())
        results: List[Dict[str, Any]] = []
        with self._connect() as conn:
            if direction in {"upstream", "both"}:
                for row in conn.execute(
                    "SELECT target_path AS path, edge_type, weight FROM edges WHERE source_path = ?",
                    (resolved,),
                ).fetchall():
                    results.append(
                        {
                            "path": row["path"],
                            "direction": "upstream",
                            "type": row["edge_type"],
                            "weight": row["weight"],
                        }
                    )
            if direction in {"downstream", "both"}:
                for row in conn.execute(
                    "SELECT source_path AS path, edge_type, weight FROM edges WHERE target_path = ?",
                    (resolved,),
                ).fetchall():
                    results.append(
                        {
                            "path": row["path"],
                            "direction": "downstream",
                            "type": row["edge_type"],
                            "weight": row["weight"],
                        }
                    )
        return results

    def _git_head_hash(self) -> Optional[str]:
        if not self._tools["git"]:
            return None
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self.repo_root),
                timeout=5,
            )
            return proc.stdout.strip() if proc.returncode == 0 else None
        except Exception:
            return None

    def _git_status_lines(self) -> List[str]:
        if not self._tools["git"]:
            return []
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
                capture_output=True,
                text=True,
                cwd=str(self.repo_root),
                timeout=10,
            )
        except Exception:
            return []
        if proc.returncode != 0:
            return []
        results: List[str] = []
        for raw_line in proc.stdout.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            path_text = line[3:] if len(line) > 3 else line
            if " -> " in path_text:
                path_text = path_text.split(" -> ", 1)[-1]
            path = Path(path_text)
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            results.append(f"{line[:2]} {path_text}")
        return results

    def _git_status_digest(self) -> Optional[str]:
        head = self._git_head_hash()
        if head is None and not self._tools["git"]:
            return None
        payload = "\n".join(self._git_status_lines())
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _fs_fingerprint(self) -> str:
        discovered = self._discover_files()
        digest = hashlib.sha256()
        for abs_path, rel_path in discovered:
            digest.update(rel_path.encode("utf-8"))
            try:
                stat = os.stat(abs_path)
            except OSError:
                continue
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
            digest.update(str(stat.st_size).encode("utf-8"))
        return digest.hexdigest()

    def should_reindex(self) -> str:
        with self._connect() as conn:
            metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM index_metadata").fetchall()}
        if not metadata:
            return "full"
        head = self._git_head_hash()
        status_digest = self._git_status_digest()
        if head is not None:
            if metadata.get("git_head") != head:
                return "incremental"
            if metadata.get("git_status_digest") != status_digest:
                return "incremental"
            return "skip"
        current_fs = self._fs_fingerprint()
        if metadata.get("fs_fingerprint") != current_fs:
            return "incremental"
        return "skip"

    def _store_index_metadata(self) -> None:
        head = self._git_head_hash()
        status_digest = self._git_status_digest()
        fs_fingerprint = self._fs_fingerprint() if head is None else None
        with self._connect() as conn:
            conn.execute("DELETE FROM index_metadata")
            if head is not None:
                conn.execute("INSERT INTO index_metadata VALUES (?, ?)", ("git_head", head))
            if status_digest is not None:
                conn.execute("INSERT INTO index_metadata VALUES (?, ?)", ("git_status_digest", status_digest))
            if fs_fingerprint is not None:
                conn.execute("INSERT INTO index_metadata VALUES (?, ?)", ("fs_fingerprint", fs_fingerprint))

    def _repo_state_fingerprint(self) -> str:
        head = self._git_head_hash()
        status_digest = self._git_status_digest()
        if head is not None:
            raw = json.dumps({"git_head": head, "git_status_digest": status_digest}, sort_keys=True)
        else:
            raw = json.dumps({"fs_fingerprint": self._fs_fingerprint()}, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _invalidate_map_cache(self) -> None:
        try:
            self._map_cache_path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            logger.debug("failed to remove repo map cache", exc_info=True)

    def invalidate_summary_cache(self) -> None:
        self._repo_summary_cache.clear()

    def _load_cached_map_data(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        if not self._map_cache_path.exists():
            return None
        try:
            payload = json.loads(self._map_cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if payload.get("fingerprint") != fingerprint:
            return None
        if not isinstance(payload.get("entries"), list):
            return None
        return payload

    def _store_cached_map_data(self, payload: Dict[str, Any]) -> None:
        try:
            self._map_cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            logger.debug("failed to persist repo map cache", exc_info=True)

    def _compute_recency_scores(self, relative_paths: Sequence[str], mtimes: Dict[str, float]) -> Dict[str, float]:
        timestamps: Dict[str, float] = {}
        if self._tools["git"]:
            try:
                proc = subprocess.run(
                    ["git", "log", "--name-only", "--format=__TS__%ct", "--"],
                    capture_output=True,
                    text=True,
                    cwd=str(self.repo_root),
                    timeout=20,
                )
                if proc.returncode == 0:
                    current_ts: Optional[int] = None
                    wanted = set(relative_paths)
                    for line in proc.stdout.splitlines():
                        if line.startswith("__TS__"):
                            try:
                                current_ts = int(line[len("__TS__") :])
                            except ValueError:
                                current_ts = None
                            continue
                        rel_path = line.strip()
                        if current_ts is None or rel_path not in wanted or rel_path in timestamps:
                            continue
                        timestamps[rel_path] = float(current_ts)
                        if len(timestamps) >= len(wanted):
                            break
            except Exception:
                logger.debug("git recency lookup failed", exc_info=True)
        for rel_path in relative_paths:
            timestamps.setdefault(rel_path, float(mtimes.get(rel_path, 0.0)))
        if not timestamps:
            return {}
        min_ts = min(timestamps.values())
        max_ts = max(timestamps.values())
        if max_ts <= min_ts:
            return {rel_path: 1.0 for rel_path in relative_paths}
        return {rel_path: (timestamps[rel_path] - min_ts) / (max_ts - min_ts) for rel_path in relative_paths}

    def _pagerank(self, nodes: Sequence[str], edges: Iterable[Tuple[str, str, float]], damping: float = 0.85, max_iter: int = 50, tol: float = 1e-6) -> Dict[str, float]:
        node_list = list(nodes)
        if not node_list:
            return {}
        incoming: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        out_weight: Dict[str, float] = defaultdict(float)
        for source_path, target_path, weight in edges:
            if source_path == target_path:
                continue
            incoming[target_path].append((source_path, weight))
            out_weight[source_path] += weight
        base = 1.0 / len(node_list)
        scores = {path: base for path in node_list}
        for _ in range(max_iter):
            new_scores = {path: (1.0 - damping) * base for path in node_list}
            sink_total = sum(scores[path] for path in node_list if out_weight.get(path, 0.0) <= 0.0)
            sink_share = damping * sink_total * base
            for path in node_list:
                new_scores[path] += sink_share
                for source_path, weight in incoming.get(path, []):
                    new_scores[path] += damping * scores[source_path] * (weight / max(out_weight[source_path], 1.0))
            delta = sum(abs(new_scores[path] - scores[path]) for path in node_list)
            scores = new_scores
            if delta < tol:
                break
        return scores

    def _entry_point_boost(self, relative_path: str, symbols: Sequence[Dict[str, Any]]) -> float:
        boost = 0.0
        stem = Path(relative_path).stem
        if stem in _ENTRY_FILE_NAMES:
            boost += 0.02
        for symbol in symbols:
            if symbol["kind"] in {"function", "method"} and symbol["name"] in _ENTRY_SYMBOL_NAMES:
                boost += 0.005
        return min(boost, 0.03)

    def _language_priority_boost(self, relative_path: str, language_name: str) -> float:
        boost = _LANGUAGE_PRIORITY_BOOST.get(language_name, 0.0)
        if relative_path.startswith("poor_cli/"):
            boost += 0.02
        elif relative_path.startswith("nvim-poor-cli/"):
            boost += 0.008
        return boost

    def _symbol_priority(self, symbol: Dict[str, Any]) -> float:
        priority = {
            "class": 5.0,
            "function": 4.0,
            "method": 3.5,
            "type": 3.0,
            "variable": 1.5,
        }.get(symbol["kind"], 1.0)
        if symbol["name"] in _ENTRY_SYMBOL_NAMES:
            priority += 2.0
        if symbol.get("scope"):
            priority += 0.2
        return priority

    def _symbol_render_text(self, symbol: Dict[str, Any]) -> str:
        signature = str(symbol.get("signature", "") or "").strip()
        if signature:
            return signature
        kind = symbol["kind"]
        name = symbol["name"]
        if kind == "class":
            return f"class {name}"
        if kind in {"function", "method"}:
            return f"def {name}(...)"
        if kind == "type":
            return f"type {name}"
        return name

    def _render_entry_block(self, entry: Dict[str, Any]) -> List[str]:
        lines = [f"{entry['relative_path']} (rank={entry['score']:.4f}, {entry['language']})"]
        classes = [symbol for symbol in entry["symbols"] if symbol["kind"] == "class"]
        methods = [symbol for symbol in entry["symbols"] if symbol["kind"] == "method"]
        emitted_methods: Set[Tuple[str, str]] = set()
        for class_symbol in classes:
            lines.append(f"  {self._symbol_render_text(class_symbol)}")
            scoped_methods = [method for method in methods if method.get("scope") == class_symbol["name"]]
            scoped_methods.sort(key=lambda item: (-self._symbol_priority(item), item["line_start"], item["name"]))
            for method in scoped_methods[:6]:
                emitted_methods.add((method["scope"], method["name"]))
                lines.append(f"    {self._symbol_render_text(method)}")
        remaining = [
            symbol
            for symbol in entry["symbols"]
            if symbol["kind"] != "method" or (symbol.get("scope", ""), symbol["name"]) not in emitted_methods
        ]
        remaining.sort(key=lambda item: (-self._symbol_priority(item), item["line_start"], item["name"]))
        for symbol in remaining[:8]:
            if symbol["kind"] == "class":
                continue
            lines.append(f"  {self._symbol_render_text(symbol)}")
        return lines

    def _estimate_tokens(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4)

    def _render_repo_map(self, data: Dict[str, Any], token_budget: int) -> str:
        entries = json.loads(json.dumps(data["entries"]))
        header = [
            f"Workspace map | files={data['stats']['files']} symbols={data['stats']['symbols']} edges={data['stats']['edges']} | budget~{token_budget}t",
            "Languages: " + ", ".join(data["languages"]),
            "",
        ]

        def render(entries_to_render: Sequence[Dict[str, Any]]) -> str:
            lines = list(header)
            for entry in entries_to_render:
                lines.extend(self._render_entry_block(entry))
                lines.append("")
            return "\n".join(lines).rstrip()

        rendered = render(entries)
        if self._estimate_tokens(rendered) <= token_budget:
            return rendered
        while entries and self._estimate_tokens(rendered) > token_budget:
            lowest = entries[-1]
            if lowest["symbols"]:
                lowest["symbols"].pop()
            else:
                entries.pop()
            rendered = render(entries)
        return rendered

    def _compute_map_data(self, fingerprint: str) -> Dict[str, Any]:
        with self._connect() as conn:
            file_rows = conn.execute(
                "SELECT path, relative_path, language, mtime, symbol_count FROM files ORDER BY relative_path"
            ).fetchall()
            symbol_rows = conn.execute(
                "SELECT file_path, name, kind, line_start, line_end, scope, signature FROM symbols ORDER BY file_path, line_start, name"
            ).fetchall()
            edge_rows = conn.execute(
                "SELECT source_path, target_path, edge_type, weight FROM edges"
            ).fetchall()
        symbols_by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in symbol_rows:
            symbols_by_file[row["file_path"]].append(dict(row))
        mtimes = {row["relative_path"]: float(row["mtime"]) for row in file_rows}
        recency_scores = self._compute_recency_scores([row["relative_path"] for row in file_rows], mtimes)
        pagerank_scores = self._pagerank(
            [row["path"] for row in file_rows],
            [(row["source_path"], row["target_path"], float(row["weight"])) for row in edge_rows],
        )
        degree_counts: Dict[str, float] = defaultdict(float)
        inbound_weights: Dict[str, float] = defaultdict(float)
        outbound_weights: Dict[str, float] = defaultdict(float)
        for row in edge_rows:
            degree_counts[row["source_path"]] += float(row["weight"])
            degree_counts[row["target_path"]] += float(row["weight"])
            outbound_weights[row["source_path"]] += float(row["weight"])
            inbound_weights[row["target_path"]] += float(row["weight"])
        max_degree = max(degree_counts.values(), default=1.0)
        max_balanced = max(
            (min(inbound_weights.get(row["path"], 0.0), outbound_weights.get(row["path"], 0.0)) for row in file_rows),
            default=1.0,
        )
        entries: List[Dict[str, Any]] = []
        for row in file_rows:
            file_symbols = symbols_by_file.get(row["path"], [])
            file_symbols.sort(key=lambda item: (-self._symbol_priority(item), item["line_start"], item["name"]))
            recency_boost = recency_scores.get(row["relative_path"], 0.0) * 0.015
            entry_boost = self._entry_point_boost(row["relative_path"], file_symbols)
            language_boost = self._language_priority_boost(row["relative_path"], row["language"])
            degree_boost = (degree_counts.get(row["path"], 0.0) / max_degree) * 0.01 if max_degree else 0.0
            balanced_flow = min(inbound_weights.get(row["path"], 0.0), outbound_weights.get(row["path"], 0.0))
            balance_boost = (balanced_flow / max_balanced) * 0.08 if max_balanced else 0.0
            score = float(pagerank_scores.get(row["path"], 0.0)) + recency_boost + entry_boost + language_boost + degree_boost + balance_boost
            entries.append(
                {
                    "path": row["path"],
                    "relative_path": row["relative_path"],
                    "language": row["language"],
                    "pagerank": float(pagerank_scores.get(row["path"], 0.0)),
                    "recency_boost": recency_boost,
                    "entry_boost": entry_boost,
                    "language_boost": language_boost,
                    "degree_boost": degree_boost,
                    "balance_boost": balance_boost,
                    "score": score,
                    "symbols": file_symbols,
                }
            )
        entries.sort(key=lambda item: (-item["score"], item["relative_path"]))
        payload = {
            "fingerprint": fingerprint,
            "generated_at": time.time(),
            "languages": sorted({row["language"] for row in file_rows if row["language"] and row["language"] != "text"}),
            "stats": {
                "files": len(file_rows),
                "symbols": len(symbol_rows),
                "edges": len(edge_rows),
            },
            "entries": entries,
        }
        return payload

    def _ensure_index_current(self) -> None:
        mode = self.should_reindex()
        if mode == "full":
            self.build_index()
        elif mode == "incremental":
            self.incremental_update()

    def build_repo_map(self, token_budget: int = _DEFAULT_MAP_TOKEN_BUDGET, refresh: bool = False) -> str:
        if refresh:
            self.build_index()
        else:
            self._ensure_index_current()
        fingerprint = self._repo_state_fingerprint()
        cache_key = (fingerprint, token_budget)
        if not refresh and cache_key in self._repo_summary_cache:
            return self._repo_summary_cache[cache_key]
        data = None if refresh else self._load_cached_map_data(fingerprint)
        if data is None:
            data = self._compute_map_data(fingerprint)
            self._store_cached_map_data(data)
        rendered = self._render_repo_map(data, token_budget=max(64, int(token_budget or _DEFAULT_MAP_TOKEN_BUDGET)))
        self._repo_summary_cache[cache_key] = rendered
        return rendered

    def build_repo_summary(self, token_budget: int = _DEFAULT_MAP_TOKEN_BUDGET) -> str:
        return self.build_repo_map(token_budget=token_budget)

    def rank_files_for_query(self, keywords: List[str], limit: int = 24) -> List[Tuple[str, float]]:
        self._ensure_index_current()
        fingerprint = self._repo_state_fingerprint()
        data = self._load_cached_map_data(fingerprint)
        if data is None:
            data = self._compute_map_data(fingerprint)
            self._store_cached_map_data(data)
        entries = data["entries"]
        if not keywords:
            return [(entry["path"], entry["score"]) for entry in entries[:limit]]
        lowered = [keyword.lower() for keyword in keywords if keyword.strip()]
        ranked: List[Tuple[str, float]] = []
        for entry in entries:
            score = float(entry["score"])
            rel_path = entry["relative_path"].lower()
            symbol_names = [symbol["name"].lower() for symbol in entry["symbols"]]
            matched = False
            for keyword in lowered:
                if keyword in rel_path:
                    score += 2.5
                    matched = True
                if keyword == Path(rel_path).stem:
                    score += 1.0
                    matched = True
                if any(keyword in name for name in symbol_names):
                    score += 4.0
                    matched = True
            if matched:
                ranked.append((entry["path"], score))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        if ranked:
            return ranked[:limit]
        return [(entry["path"], entry["score"]) for entry in entries[:limit]]

    def get_stats(self) -> Dict[str, int]:
        with self._connect() as conn:
            files = int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            symbols = int(conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0])
            edges = int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])
        return {"files": files, "symbols": symbols, "edges": edges}

    def _count_directories(self) -> int:
        with self._connect() as conn:
            rows = conn.execute("SELECT relative_path FROM files").fetchall()
        return len({str(Path(row["relative_path"]).parent) for row in rows if row["relative_path"]})

    def get_tree_summary(self) -> Optional[str]:
        return self._get_tree()

    def generate_graph_frames(self, node_labels: Optional[List[str]] = None) -> List[str]:
        if node_labels is None:
            node_labels = [Path(path).stem[:10] for path, _score in self.rank_files_for_query([], limit=8)]
        if not node_labels:
            return []
        labels = node_labels[:8]
        midpoint = max(1, len(labels) // 2)
        first_row = labels[:midpoint]
        second_row = labels[midpoint:]

        def render(nodes: List[str], connected: bool) -> str:
            separator = " --- " if connected else "  .  "
            return separator.join(f"[{label}]" for label in nodes)

        frames: List[str] = []
        for index in range(1, len(labels) + 1):
            visible_first = first_row[: min(index, len(first_row))]
            visible_second = second_row[: max(0, index - len(first_row))]
            lines = [render(visible_first, False)]
            if visible_second:
                lines.append(render(visible_second, False))
            frames.append("\n".join(lines))
        connected = "\n".join(filter(None, [render(first_row, True), render(second_row, True) if second_row else ""]))
        frames.append(connected)
        pulse = connected.replace("---", "===")
        frames.append(pulse)
        return frames
