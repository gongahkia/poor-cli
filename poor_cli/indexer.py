"""
Semantic codebase indexer for poor-cli.

Provides full-text and optional embedding-based search over the codebase.
Uses SQLite FTS5 for zero-dependency text search, with optional vector
embeddings from Gemini, OpenAI, or local Ollama models.

AST-aware chunking via tree-sitter produces syntactically complete chunks
(functions, classes, impl blocks) with natural language descriptions and
dual embedding (code + description).

Index stored at .poor-cli/index/code.db.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import setup_logger
from .embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)

logger = setup_logger(__name__)

INDEX_DIR = "index"
INDEX_DB = "code.db"
_DB_SCHEMA_VERSION = 2 # bump when schema changes

# file extensions to index
INDEXABLE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".c", ".cpp",
    ".h", ".hpp", ".rb", ".php", ".swift", ".kt", ".scala", ".cs", ".lua",
    ".sh", ".bash", ".zsh", ".fish", ".yaml", ".yml", ".toml", ".json",
    ".md", ".txt", ".html", ".css", ".scss", ".sql", ".r", ".jl",
    ".ex", ".exs", ".erl", ".hs", ".ml", ".mli", ".vim", ".el",
})

# directories to always skip
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".poor-cli",
    ".venv", "venv", ".env", "target", "build", "dist", ".next",
    ".cache", ".tox", ".mypy_cache", ".ruff_cache", "vendor",
})

MAX_FILE_SIZE = 100_000 # 100KB
MAX_CHUNK_CHARS = 2000
OVERLAP_CHARS = 200
MAX_CHUNK_LINES = 500 # split at method boundaries above this

# tree-sitter language modules (shared with repo_graph.py)
_TREE_SITTER_MODULES = {
    "python": ("tree_sitter_python", ("language",)),
    "lua": ("tree_sitter_lua", ("language",)),
    "javascript": ("tree_sitter_javascript", ("language",)),
    "typescript": ("tree_sitter_typescript", ("language_typescript", "typescript", "language")),
    "rust": ("tree_sitter_rust", ("language",)),
}

# AST node types that define chunk boundaries per language
CHUNK_TYPES: Dict[str, List[str]] = {
    "python": ["function_definition", "class_definition", "decorated_definition"],
    "lua": ["function_declaration", "local_function", "function_definition_statement",
            "function", "variable_declaration"],
    "javascript": ["function_declaration", "class_declaration", "arrow_function",
                    "method_definition", "export_statement", "lexical_declaration"],
    "typescript": ["function_declaration", "class_declaration", "interface_declaration",
                    "type_alias_declaration", "export_statement", "lexical_declaration"],
    "rust": ["function_item", "impl_item", "struct_item", "enum_item", "trait_item",
             "mod_item", "const_item", "static_item"],
}

# node types representing methods inside a class/impl (for splitting large chunks)
_METHOD_TYPES: Dict[str, List[str]] = {
    "python": ["function_definition", "decorated_definition"],
    "lua": ["function_declaration", "local_function", "function_definition_statement"],
    "javascript": ["method_definition", "function_declaration"],
    "typescript": ["method_definition", "function_declaration", "method_signature"],
    "rust": ["function_item", "associated_type"],
}


@dataclass
class CodeChunk:
    """A syntactically-complete chunk of code with metadata."""
    filepath: str
    start_line: int
    end_line: int
    content: str
    node_type: str
    name: str
    language: str
    description: str = ""

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class SearchResult:
    """A single search result from the index."""
    file_path: str
    chunk_index: int
    content: str
    score: float
    language: str
    node_type: str = ""
    name: str = ""
    start_line: int = 0
    end_line: int = 0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "filePath": self.file_path,
            "chunkIndex": self.chunk_index,
            "content": self.content[:500],
            "score": self.score,
            "language": self.language,
        }
        if self.node_type:
            d["nodeType"] = self.node_type
            d["name"] = self.name
            d["startLine"] = self.start_line
            d["endLine"] = self.end_line
        if self.description:
            d["description"] = self.description
        return d


@dataclass
class IndexStats:
    """Statistics about the current index."""
    total_files: int
    total_chunks: int
    last_indexed: str
    index_size_bytes: int
    ast_chunks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalFiles": self.total_files,
            "totalChunks": self.total_chunks,
            "astChunks": self.ast_chunks,
            "lastIndexed": self.last_indexed,
            "indexSizeBytes": self.index_size_bytes,
        }


class CodebaseIndexer:
    """Full-text + optional embedding search over codebase files."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self._index_dir = self.repo_root / ".poor-cli" / INDEX_DIR
        self._db_path = self._index_dir / INDEX_DB
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            # check schema version and migrate if needed
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            current_version = int(row["value"]) if row else 0
            if current_version < _DB_SCHEMA_VERSION:
                # drop old tables and recreate (index is rebuildable)
                for tbl in ("chunks_fts", "embeddings", "chunks", "files"):
                    try:
                        conn.execute(f"DROP TABLE IF EXISTS {tbl}")
                    except sqlite3.OperationalError:
                        pass
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                             (str(_DB_SCHEMA_VERSION),))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    language TEXT NOT NULL,
                    indexed_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    node_type TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    start_line INTEGER NOT NULL DEFAULT 0,
                    end_line INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (file_path) REFERENCES files(file_path) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    file_path,
                    description,
                    content=chunks,
                    content_rowid=chunk_id,
                    tokenize='porter unicode61'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    chunk_id INTEGER PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    desc_embedding TEXT NOT NULL DEFAULT '[]',
                    provider TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, content, file_path, description)
                    VALUES (new.chunk_id, new.content, new.file_path, new.description);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content, file_path, description)
                    VALUES ('delete', old.chunk_id, old.content, old.file_path, old.description);
                END
            """)

    # ── indexing ─────────────────────────────────────────────────────────

    def index(self, force: bool = False, progress_callback: Any = None) -> IndexStats:
        """Index the codebase. Only re-indexes changed files unless force=True."""
        files = list(self._discover_files())
        indexed = 0
        skipped = 0

        with self._connect() as conn:
            existing = {}
            if not force:
                rows = conn.execute("SELECT file_path, file_hash FROM files").fetchall()
                existing = {r["file_path"]: r["file_hash"] for r in rows}

            for file_path in files:
                rel = str(file_path.relative_to(self.repo_root))
                content = self._read_file(file_path)
                if content is None:
                    continue
                file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

                if not force and existing.get(rel) == file_hash:
                    skipped += 1
                    continue

                # remove old data for this file
                conn.execute("DELETE FROM chunks WHERE file_path = ?", (rel,))
                conn.execute("DELETE FROM files WHERE file_path = ?", (rel,))

                lang = _detect_language(file_path)
                # try AST-aware chunking first, fall back to regex/size-based
                ast_chunks = _chunk_file_ast(file_path, content, lang)
                conn.execute(
                    "INSERT INTO files (file_path, file_hash, language, indexed_at) VALUES (?, ?, ?, ?)",
                    (rel, file_hash, lang, time.time()),
                )
                if ast_chunks:
                    for i, chunk in enumerate(ast_chunks):
                        desc = _describe_chunk(chunk)
                        conn.execute(
                            "INSERT INTO chunks (file_path, chunk_index, content, node_type, name, start_line, end_line, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (rel, i, chunk.content, chunk.node_type, chunk.name,
                             chunk.start_line, chunk.end_line, desc),
                        )
                else:
                    for i, text in enumerate(_chunk_content(content)):
                        conn.execute(
                            "INSERT INTO chunks (file_path, chunk_index, content) VALUES (?, ?, ?)",
                            (rel, i, text),
                        )
                indexed += 1
                if progress_callback:
                    progress_callback(f"indexed {indexed} files ({rel})")

        logger.info("indexing complete: %d indexed, %d skipped", indexed, skipped)
        return self.get_stats()

    def _discover_files(self) -> List[Path]:
        """Walk the repo and yield indexable files."""
        results = []
        for root, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix.lower() in INDEXABLE_EXTENSIONS:
                    if fpath.stat().st_size <= MAX_FILE_SIZE:
                        results.append(fpath)
        return results

    def _read_file(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

    # ── search ───────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 10,
        file_filter: Optional[str] = None,
    ) -> List[SearchResult]:
        """Full-text search over indexed chunks using FTS5 (searches content + description)."""
        if not query.strip():
            return []
        safe_query = _fts5_escape(query)
        sql = """
            SELECT c.file_path, c.chunk_index, c.content, f.language,
                   c.node_type, c.name, c.start_line, c.end_line, c.description,
                   rank AS score
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.chunk_id
            JOIN files f ON c.file_path = f.file_path
            WHERE chunks_fts MATCH ?
        """
        params: List[Any] = [safe_query]
        if file_filter:
            sql += " AND c.file_path LIKE ?"
            params.append(f"%{file_filter}%")
        sql += " ORDER BY rank LIMIT ?"
        params.append(max_results)
        results = []
        with self._connect() as conn:
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return self._fallback_search(query, max_results, file_filter)
            for row in rows:
                results.append(_row_to_result(row, abs(row["score"])))
        return results

    def _fallback_search(
        self, query: str, max_results: int, file_filter: Optional[str]
    ) -> List[SearchResult]:
        """LIKE-based fallback when FTS query is invalid."""
        sql = """
            SELECT c.file_path, c.chunk_index, c.content, f.language,
                   c.node_type, c.name, c.start_line, c.end_line, c.description
            FROM chunks c
            JOIN files f ON c.file_path = f.file_path
            WHERE c.content LIKE ? OR c.description LIKE ?
        """
        params: List[Any] = [f"%{query}%", f"%{query}%"]
        if file_filter:
            sql += " AND c.file_path LIKE ?"
            params.append(f"%{file_filter}%")
        sql += " LIMIT ?"
        params.append(max_results)
        results = []
        with self._connect() as conn:
            for row in conn.execute(sql, params).fetchall():
                results.append(_row_to_result(row, 1.0))
        return results

    # ── stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> IndexStats:
        with self._connect() as conn:
            files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            ast_chunks = conn.execute("SELECT COUNT(*) FROM chunks WHERE node_type != ''").fetchone()[0]
            last_row = conn.execute("SELECT MAX(indexed_at) FROM files").fetchone()[0]
        last_indexed = ""
        if last_row:
            from datetime import datetime, timezone
            last_indexed = datetime.fromtimestamp(last_row, tz=timezone.utc).isoformat()
        size = self._db_path.stat().st_size if self._db_path.exists() else 0
        return IndexStats(
            total_files=files,
            total_chunks=chunks,
            ast_chunks=ast_chunks,
            last_indexed=last_indexed,
            index_size_bytes=size,
        )

    # ── embedding indexing ──────────────────────────────────────────────

    async def index_embeddings(
        self,
        provider: Optional[EmbeddingProvider] = None,
        batch_size: int = 50,
        force: bool = False,
        progress_callback: Any = None,
    ) -> Dict[str, Any]:
        """Generate and store dual embeddings (code + description) for all indexed chunks."""
        if provider is None:
            provider = get_embedding_provider()
        if provider is None:
            return {"error": "no embedding provider available", "embedded": 0}

        with self._connect() as conn:
            if force:
                conn.execute("DELETE FROM embeddings")
                rows = conn.execute("SELECT chunk_id, content, description FROM chunks").fetchall()
            else:
                rows = conn.execute("""
                    SELECT c.chunk_id, c.content, c.description FROM chunks c
                    LEFT JOIN embeddings e ON c.chunk_id = e.chunk_id
                    WHERE e.chunk_id IS NULL
                """).fetchall()

        if not rows:
            return {"provider": provider.name, "embedded": 0, "message": "all chunks already embedded"}

        embedded = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            code_texts = [row["content"][:2000] for row in batch]
            desc_texts = [row["description"] or "" for row in batch]
            chunk_ids = [row["chunk_id"] for row in batch]
            try:
                code_vectors = await provider.embed(code_texts)
            except Exception as exc:
                logger.error("code embedding batch failed: %s", exc)
                continue
            # embed descriptions (skip empty ones, store empty vec)
            desc_vectors: List[List[float]] = []
            non_empty_descs = [d for d in desc_texts if d.strip()]
            if non_empty_descs:
                try:
                    desc_vecs_raw = await provider.embed(non_empty_descs)
                except Exception:
                    desc_vecs_raw = [[] for _ in non_empty_descs]
                desc_iter = iter(desc_vecs_raw)
                for d in desc_texts:
                    desc_vectors.append(next(desc_iter) if d.strip() else [])
            else:
                desc_vectors = [[] for _ in desc_texts]

            with self._connect() as conn:
                for cid, cvec, dvec in zip(chunk_ids, code_vectors, desc_vectors):
                    if not cvec:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO embeddings (chunk_id, embedding, desc_embedding, provider, dimensions) VALUES (?, ?, ?, ?, ?)",
                        (cid, json.dumps(cvec), json.dumps(dvec), provider.name, len(cvec)),
                    )
                    embedded += 1

            if progress_callback:
                progress_callback(f"embedded {embedded}/{len(rows)} chunks")

        logger.info("embedding complete: %d chunks via %s", embedded, provider.name)
        return {"provider": provider.name, "embedded": embedded, "total": len(rows)}

    # ── vector search ────────────────────────────────────────────────────

    async def vector_search(
        self,
        query: str,
        max_results: int = 10,
        file_filter: Optional[str] = None,
        provider: Optional[EmbeddingProvider] = None,
        code_weight: float = 0.3,
        desc_weight: float = 0.7,
    ) -> List[SearchResult]:
        """Dual-embedding vector search (code + description). Falls back to FTS5 if no embeddings."""
        if provider is None:
            provider = get_embedding_provider()
        if provider is None:
            logger.debug("no embedding provider, falling back to FTS5")
            return self.search(query, max_results, file_filter)
        with self._connect() as conn:
            emb_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        if emb_count == 0:
            logger.debug("no embeddings in index, falling back to FTS5")
            return self.search(query, max_results, file_filter)
        try:
            query_vecs = await provider.embed([query])
            if not query_vecs or not query_vecs[0]:
                return self.search(query, max_results, file_filter)
            query_vec = query_vecs[0]
        except Exception as exc:
            logger.warning("query embedding failed, falling back to FTS5: %s", exc)
            return self.search(query, max_results, file_filter)
        with self._connect() as conn:
            filter_clause = ""
            params: List[Any] = []
            if file_filter:
                filter_clause = "AND c.file_path LIKE ?"
                params.append(f"%{file_filter}%")
            rows = conn.execute(f"""
                SELECT c.chunk_id, c.file_path, c.chunk_index, c.content,
                       c.node_type, c.name, c.start_line, c.end_line, c.description,
                       f.language, e.embedding, e.desc_embedding
                FROM chunks c
                JOIN files f ON c.file_path = f.file_path
                JOIN embeddings e ON c.chunk_id = e.chunk_id
                {filter_clause}
            """, params).fetchall()
        # dual-embedding weighted scoring
        scored: List[Tuple[Any, float]] = []
        for row in rows:
            try:
                code_vec = json.loads(row["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            code_sim = cosine_similarity(query_vec, code_vec) if code_vec else 0.0
            desc_sim = 0.0
            try:
                desc_vec = json.loads(row["desc_embedding"]) if row["desc_embedding"] else []
                if desc_vec:
                    desc_sim = cosine_similarity(query_vec, desc_vec)
            except (json.JSONDecodeError, TypeError):
                pass
            # weighted combination
            combined = code_weight * code_sim + desc_weight * desc_sim if desc_sim else code_sim
            scored.append((row, combined))
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for row, score in scored[:max_results]:
            results.append(_row_to_result(row, round(score, 4)))
        return results

    # ── hybrid search ────────────────────────────────────────────────────

    async def hybrid_search(
        self,
        query: str,
        max_results: int = 10,
        file_filter: Optional[str] = None,
        provider: Optional[EmbeddingProvider] = None,
        fts_weight: float = 0.3,
        vec_weight: float = 0.7,
    ) -> List[SearchResult]:
        """
        Combine FTS5 and vector search with weighted scoring.

        Falls back gracefully: vector-only if FTS fails, FTS-only if no embeddings.
        """
        fts_results = self.search(query, max_results=max_results * 2, file_filter=file_filter)
        vec_results = await self.vector_search(query, max_results=max_results * 2,
                                                file_filter=file_filter, provider=provider)

        # merge: combine scores by file_path:chunk_index key
        scored: Dict[str, Tuple[SearchResult, float]] = {}
        fts_max = max((r.score for r in fts_results), default=1.0) or 1.0
        vec_max = max((r.score for r in vec_results), default=1.0) or 1.0

        for r in fts_results:
            key = f"{r.file_path}:{r.chunk_index}"
            norm_score = (r.score / fts_max) * fts_weight
            scored[key] = (r, norm_score)

        for r in vec_results:
            key = f"{r.file_path}:{r.chunk_index}"
            norm_score = (r.score / vec_max) * vec_weight
            if key in scored:
                existing_result, existing_score = scored[key]
                scored[key] = (existing_result, existing_score + norm_score)
            else:
                scored[key] = (r, norm_score)

        # sort by combined score
        ranked = sorted(scored.values(), key=lambda x: x[1], reverse=True)
        results = []
        for result, score in ranked[:max_results]:
            result.score = round(score, 4)
            results.append(result)
        return results

    def clear(self) -> None:
        """Drop and recreate the index."""
        with self._connect() as conn:
            conn.execute("DELETE FROM embeddings")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")
        logger.info("index cleared")


# ── helpers ──────────────────────────────────────────────────────────────

def _row_to_result(row: Any, score: float) -> SearchResult:
    """Build SearchResult from a DB row."""
    return SearchResult(
        file_path=row["file_path"],
        chunk_index=row["chunk_index"],
        content=row["content"],
        score=score,
        language=row["language"],
        node_type=row["node_type"] if "node_type" in row.keys() else "",
        name=row["name"] if "name" in row.keys() else "",
        start_line=row["start_line"] if "start_line" in row.keys() else 0,
        end_line=row["end_line"] if "end_line" in row.keys() else 0,
        description=row["description"] if "description" in row.keys() else "",
    )


def _detect_language(path: Path) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".rs": "rust",
        ".go": "go", ".java": "java", ".c": "c", ".cpp": "cpp",
        ".h": "c", ".hpp": "cpp", ".rb": "ruby", ".php": "php",
        ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
        ".cs": "csharp", ".lua": "lua", ".sh": "shell", ".bash": "shell",
        ".zsh": "shell", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".json": "json", ".md": "markdown",
        ".html": "html", ".css": "css", ".sql": "sql",
    }
    return ext_map.get(path.suffix.lower(), "text")


# ── tree-sitter AST chunking ──────────────────────────────────────────

_ts_languages: Dict[str, Any] = {} # cached tree-sitter Language objects


def _load_ts_language(lang: str) -> Any:
    """Load and cache a tree-sitter language. Returns None if unavailable."""
    if lang in _ts_languages:
        return _ts_languages[lang]
    module_info = _TREE_SITTER_MODULES.get(lang)
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
                _ts_languages[lang] = value
                return value
        except TypeError:
            pass
        try:
            language = Language(value)
        except Exception:
            continue
        _ts_languages[lang] = language
        return language
    return None


def _make_parser(lang: str) -> Any:
    """Create a tree-sitter parser for the given language."""
    language = _load_ts_language(lang)
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


def _extract_name(node: Any, language: str) -> str:
    """Extract the name identifier from an AST node."""
    # for wrapper nodes, look inside the actual definition
    if node.type in ("decorated_definition", "export_statement"):
        for child in node.children:
            if child.type in CHUNK_TYPES.get(language, []):
                return _extract_name(child, language)
    # for Lua variable_declaration, dig into assignment_statement
    if node.type == "variable_declaration":
        for child in node.children:
            if child.type == "assignment_statement":
                return _extract_name(child, language)
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier", "name"):
            return child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
        # Lua: function M.setup → dot_index_expression → get full text
        if child.type in ("dot_index_expression", "method_index_expression"):
            return child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
        # nested: variable_list > identifier
        if child.type == "variable_list":
            return _extract_name(child, language)
    return ""


def _chunk_file_ast(filepath: Path, content: str, language: str) -> List[CodeChunk]:
    """AST-aware chunking using tree-sitter. Returns [] if tree-sitter unavailable."""
    if language not in CHUNK_TYPES:
        return []
    parser = _make_parser(language)
    if parser is None:
        return []
    try:
        src = content.encode("utf-8") if isinstance(content, str) else content
        tree = parser.parse(src)
    except Exception:
        logger.debug("tree-sitter parse failed for %s", filepath)
        return []
    chunk_types = set(CHUNK_TYPES[language])
    chunks: List[CodeChunk] = []
    # collect top-level and significant nested nodes
    _walk_for_chunks(tree.root_node, chunk_types, language, str(filepath), chunks)
    # if no chunks found (file has no functions/classes), return [] to trigger fallback
    if not chunks:
        return []
    # collect any preamble (imports, module-level code before first chunk)
    first_start = chunks[0].start_line if chunks else 0
    if first_start > 0:
        lines = content.split("\n")
        preamble = "\n".join(lines[:first_start]).strip()
        if preamble:
            chunks.insert(0, CodeChunk(
                filepath=str(filepath), start_line=0, end_line=first_start - 1,
                content=preamble, node_type="preamble", name="<imports>", language=language,
            ))
    return chunks


def _walk_for_chunks(
    node: Any, chunk_types: set, language: str, filepath: str, out: List[CodeChunk],
) -> None:
    """Recursively walk AST, extracting chunk-worthy nodes."""
    for child in node.children:
        if child.type in chunk_types:
            text = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
            name = _extract_name(child, language)
            chunk = CodeChunk(
                filepath=filepath,
                start_line=child.start_point[0],
                end_line=child.end_point[0],
                content=text,
                node_type=child.type,
                name=name,
                language=language,
            )
            if chunk.line_count > MAX_CHUNK_LINES:
                out.extend(_split_large_chunk(child, chunk, language, filepath))
            else:
                out.append(chunk)
        else:
            # recurse into non-chunk nodes (e.g., module bodies)
            _walk_for_chunks(child, chunk_types, language, filepath, out)


def _split_large_chunk(
    node: Any, parent_chunk: CodeChunk, language: str, filepath: str,
) -> List[CodeChunk]:
    """Split a large node (>500 lines) at method/function boundaries."""
    method_types = set(_METHOD_TYPES.get(language, []))
    methods: List[Any] = []
    _find_methods(node, method_types, methods)
    if not methods:
        return [parent_chunk] # can't split further
    chunks: List[CodeChunk] = []
    parent_start = node.start_point[0]
    # header: everything from parent start to first method
    first_method_line = methods[0].start_point[0]
    if first_method_line > parent_start:
        lines = parent_chunk.content.split("\n")
        header_end = first_method_line - parent_start
        header = "\n".join(lines[:header_end]).strip()
        if header:
            chunks.append(CodeChunk(
                filepath=filepath, start_line=parent_start, end_line=first_method_line - 1,
                content=header, node_type=parent_chunk.node_type + "_header",
                name=parent_chunk.name, language=language,
            ))
    # each method as its own chunk
    for m in methods:
        text = m.text.decode("utf-8") if isinstance(m.text, bytes) else m.text
        name = _extract_name(m, language)
        chunks.append(CodeChunk(
            filepath=filepath, start_line=m.start_point[0], end_line=m.end_point[0],
            content=text, node_type=m.type, name=name, language=language,
        ))
    return chunks if chunks else [parent_chunk]


def _find_methods(node: Any, method_types: set, out: List[Any]) -> None:
    """Find direct child nodes that are methods."""
    for child in node.children:
        if child.type in method_types:
            out.append(child)
        elif child.type in ("block", "body", "declaration_list", "field_declaration_list"):
            _find_methods(child, method_types, out)


# ── chunk descriptions ────────────────────────────────────────────────

def _describe_chunk(chunk: CodeChunk) -> str:
    """Generate a natural language description for a chunk."""
    if chunk.node_type == "preamble":
        return f"imports and module-level code in {Path(chunk.filepath).name}"
    # try to extract docstring
    doc = _extract_docstring(chunk.content, chunk.language)
    if doc:
        return doc[:200]
    # heuristic description from signature
    kind = _human_node_type(chunk.node_type)
    fname = Path(chunk.filepath).name
    if chunk.name:
        return f"{kind} '{chunk.name}' in {fname}:{chunk.start_line + 1}"
    return f"{kind} in {fname}:{chunk.start_line + 1}-{chunk.end_line + 1}"


def _extract_docstring(content: str, language: str) -> str:
    """Extract the first docstring/doc comment from chunk content."""
    if language == "python":
        m = re.search(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'', content, re.DOTALL)
        if m:
            doc = (m.group(1) or m.group(2) or "").strip()
            first_line = doc.split("\n")[0].strip()
            return first_line if first_line else doc[:100]
    elif language == "rust":
        lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("///") or stripped.startswith("//!"):
                lines.append(stripped.lstrip("/!").strip())
            elif lines:
                break
        if lines:
            return lines[0]
    elif language in ("javascript", "typescript"):
        m = re.search(r'/\*\*(.*?)\*/', content, re.DOTALL)
        if m:
            doc = m.group(1).strip()
            # extract first meaningful line from JSDoc
            for line in doc.split("\n"):
                cleaned = line.strip().lstrip("* ").strip()
                if cleaned and not cleaned.startswith("@"):
                    return cleaned
    elif language == "lua":
        lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("---") or stripped.startswith("--"):
                lines.append(stripped.lstrip("-").strip())
            elif lines:
                break
        if lines:
            return lines[0]
    return ""


def _human_node_type(node_type: str) -> str:
    """Convert AST node type to human-readable label."""
    mapping = {
        "function_definition": "function",
        "class_definition": "class",
        "decorated_definition": "decorated definition",
        "function_declaration": "function",
        "local_function": "local function",
        "function_definition_statement": "function",
        "class_declaration": "class",
        "arrow_function": "arrow function",
        "method_definition": "method",
        "export_statement": "export",
        "lexical_declaration": "declaration",
        "interface_declaration": "interface",
        "type_alias_declaration": "type alias",
        "function_item": "function",
        "impl_item": "impl block",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "mod_item": "module",
        "const_item": "constant",
        "static_item": "static",
        "method_signature": "method signature",
    }
    return mapping.get(node_type, node_type.replace("_", " "))


# ── fallback chunking (non-AST languages) ─────────────────────────────

def _chunk_content(content: str) -> List[str]:
    """Fallback: split content by regex boundaries or character limit."""
    boundaries = list(re.finditer(
        r'^(?:def |class |func |fn |function |pub fn |impl |module |package )',
        content, re.MULTILINE,
    ))
    if len(boundaries) >= 2:
        chunks = []
        for i, match in enumerate(boundaries):
            start = match.start()
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(content)
            chunk = content[start:end].strip()
            if chunk:
                if len(chunk) > MAX_CHUNK_CHARS:
                    chunks.extend(_split_by_size(chunk))
                else:
                    chunks.append(chunk)
        return chunks if chunks else _split_by_size(content)
    return _split_by_size(content)


def _split_by_size(text: str) -> List[str]:
    """Split text into overlapping fixed-size chunks."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text] if text.strip() else []
    chunks = []
    pos = 0
    while pos < len(text):
        end = pos + MAX_CHUNK_CHARS
        chunk = text[pos:end].strip()
        if chunk:
            chunks.append(chunk)
        pos += MAX_CHUNK_CHARS - OVERLAP_CHARS
    return chunks


def _fts5_escape(query: str) -> str:
    """Escape special FTS5 characters and format for matching."""
    cleaned = re.sub(r'["\'\(\)\*\-\+]', ' ', query)
    tokens = cleaned.split()
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens[:10])
