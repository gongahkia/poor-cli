"""
Semantic codebase indexer for poor-cli.

Provides full-text and optional embedding-based search over the codebase.
Uses SQLite FTS5 for zero-dependency text search, with optional vector
embeddings from Gemini, OpenAI, or local Ollama models.

Index stored at .poor-cli/index/code.db.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

INDEX_DIR = "index"
INDEX_DB = "code.db"

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


@dataclass
class SearchResult:
    """A single search result from the index."""
    file_path: str
    chunk_index: int
    content: str
    score: float
    language: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filePath": self.file_path,
            "chunkIndex": self.chunk_index,
            "content": self.content[:500], # cap for display
            "score": self.score,
            "language": self.language,
        }


@dataclass
class IndexStats:
    """Statistics about the current index."""
    total_files: int
    total_chunks: int
    last_indexed: str
    index_size_bytes: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalFiles": self.total_files,
            "totalChunks": self.total_chunks,
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
                    FOREIGN KEY (file_path) REFERENCES files(file_path) ON DELETE CASCADE
                )
            """)
            # FTS5 virtual table for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    file_path,
                    content=chunks,
                    content_rowid=chunk_id,
                    tokenize='porter unicode61'
                )
            """)
            # triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, content, file_path)
                    VALUES (new.chunk_id, new.content, new.file_path);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content, file_path)
                    VALUES ('delete', old.chunk_id, old.content, old.file_path);
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

                # chunk and insert
                lang = _detect_language(file_path)
                chunks = _chunk_content(content)
                conn.execute(
                    "INSERT INTO files (file_path, file_hash, language, indexed_at) VALUES (?, ?, ?, ?)",
                    (rel, file_hash, lang, time.time()),
                )
                for i, chunk in enumerate(chunks):
                    conn.execute(
                        "INSERT INTO chunks (file_path, chunk_index, content) VALUES (?, ?, ?)",
                        (rel, i, chunk),
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
        """Full-text search over indexed chunks using FTS5."""
        if not query.strip():
            return []

        # escape FTS5 special chars for safety
        safe_query = _fts5_escape(query)

        sql = """
            SELECT c.file_path, c.chunk_index, c.content, f.language,
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
                # FTS query syntax error — fall back to LIKE
                return self._fallback_search(query, max_results, file_filter)
            for row in rows:
                results.append(SearchResult(
                    file_path=row["file_path"],
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    score=abs(row["score"]),
                    language=row["language"],
                ))
        return results

    def _fallback_search(
        self, query: str, max_results: int, file_filter: Optional[str]
    ) -> List[SearchResult]:
        """LIKE-based fallback when FTS query is invalid."""
        sql = """
            SELECT c.file_path, c.chunk_index, c.content, f.language
            FROM chunks c
            JOIN files f ON c.file_path = f.file_path
            WHERE c.content LIKE ?
        """
        params: List[Any] = [f"%{query}%"]
        if file_filter:
            sql += " AND c.file_path LIKE ?"
            params.append(f"%{file_filter}%")
        sql += " LIMIT ?"
        params.append(max_results)

        results = []
        with self._connect() as conn:
            for row in conn.execute(sql, params).fetchall():
                results.append(SearchResult(
                    file_path=row["file_path"],
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    score=1.0,
                    language=row["language"],
                ))
        return results

    # ── stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> IndexStats:
        with self._connect() as conn:
            files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            last_row = conn.execute("SELECT MAX(indexed_at) FROM files").fetchone()[0]
        last_indexed = ""
        if last_row:
            from datetime import datetime, timezone
            last_indexed = datetime.fromtimestamp(last_row, tz=timezone.utc).isoformat()
        size = self._db_path.stat().st_size if self._db_path.exists() else 0
        return IndexStats(
            total_files=files,
            total_chunks=chunks,
            last_indexed=last_indexed,
            index_size_bytes=size,
        )

    def clear(self) -> None:
        """Drop and recreate the index."""
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")
        logger.info("index cleared")


# ── helpers ──────────────────────────────────────────────────────────────

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


def _chunk_content(content: str) -> List[str]:
    """Split content into overlapping chunks by function/class boundaries or character limit."""
    # try to split on function/class boundaries
    boundaries = list(re.finditer(
        r'^(?:def |class |func |fn |function |pub fn |impl |module |package )',
        content,
        re.MULTILINE,
    ))

    if len(boundaries) >= 2:
        chunks = []
        for i, match in enumerate(boundaries):
            start = match.start()
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(content)
            chunk = content[start:end].strip()
            if chunk:
                # further split if too large
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
    # remove FTS5 operators to prevent syntax errors
    cleaned = re.sub(r'["\'\(\)\*\-\+]', ' ', query)
    tokens = cleaned.split()
    if not tokens:
        return '""'
    # use implicit AND by quoting each token
    return " ".join(f'"{t}"' for t in tokens[:10])
