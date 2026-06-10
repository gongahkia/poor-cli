"""Tests for AST-aware code chunking in the indexer."""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from poor_cli.indexer import (
    CHUNK_TYPES,
    MAX_CHUNK_LINES,
    CodeChunk,
    CodebaseIndexer,
    SearchResult,
    _chunk_content,
    _chunk_file_ast,
    _describe_chunk,
    _detect_language,
    _extract_name,
    _make_parser,
    _split_large_chunk,
)

# ── fixtures ──────────────────────────────────────────────────────────

TS_AVAILABLE = _make_parser("python") is not None

PYTHON_CODE = '''import os
import sys

def greet(name):
    """Say hello to someone."""
    print(f"Hello, {name}!")

class Greeter:
    """A greeter class."""
    def __init__(self, prefix):
        self.prefix = prefix
    def greet(self, name):
        return f"{self.prefix} {name}"

def farewell():
    print("goodbye")
'''

LUA_CODE = '''local M = {}
function M.setup(opts)
  M.opts = opts
end
local function helper()
  return 42
end
return M
'''

JS_CODE = '''import { foo } from "bar";

function greet(name) {
  /** Greets someone by name */
  return "Hello " + name;
}

class Widget {
  constructor(id) { this.id = id; }
  render() { return "<div>"; }
}
'''

TS_CODE = '''interface Config {
  name: string;
}

type ID = string | number;

function create(cfg: Config): void {
  console.log(cfg);
}
'''

RUST_CODE = '''/// A simple greeter
fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

struct Config {
    name: String,
}

impl Config {
    fn new(name: String) -> Self {
        Config { name }
    }
}
'''


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temp repo with sample files."""
    (tmp_path / "main.py").write_text(PYTHON_CODE)
    (tmp_path / "init.lua").write_text(LUA_CODE)
    (tmp_path / "app.js").write_text(JS_CODE)
    (tmp_path / "types.ts").write_text(TS_CODE)
    (tmp_path / "lib.rs").write_text(RUST_CODE)
    (tmp_path / "data.json").write_text('{"key": "value"}')
    return tmp_path


# ── AST chunking tests ────────────────────────────────────────────────

@pytest.mark.skipif(not TS_AVAILABLE, reason="tree-sitter not installed")
class TestASTChunking:
    def test_python_chunks(self):
        chunks = _chunk_file_ast(Path("test.py"), PYTHON_CODE, "python")
        assert len(chunks) >= 3 # preamble + greet + Greeter + farewell
        types = [c.node_type for c in chunks]
        assert "function_definition" in types
        assert "class_definition" in types
        names = [c.name for c in chunks]
        assert "greet" in names
        assert "Greeter" in names

    def test_python_chunks_syntactically_complete(self):
        chunks = _chunk_file_ast(Path("test.py"), PYTHON_CODE, "python")
        for c in chunks:
            if c.node_type == "function_definition":
                assert c.content.startswith("def ")
            elif c.node_type == "class_definition":
                assert c.content.startswith("class ")

    def test_lua_chunks(self):
        chunks = _chunk_file_ast(Path("test.lua"), LUA_CODE, "lua")
        assert len(chunks) >= 2
        names = [c.name for c in chunks]
        assert "M.setup" in names or "helper" in names

    def test_javascript_chunks(self):
        chunks = _chunk_file_ast(Path("test.js"), JS_CODE, "javascript")
        assert len(chunks) >= 2
        names = [c.name for c in chunks]
        assert "greet" in names
        assert "Widget" in names

    def test_typescript_chunks(self):
        chunks = _chunk_file_ast(Path("test.ts"), TS_CODE, "typescript")
        assert len(chunks) >= 2
        types = [c.node_type for c in chunks]
        assert "interface_declaration" in types or "function_declaration" in types
        names = [c.name for c in chunks]
        assert "Config" in names

    def test_rust_chunks(self):
        chunks = _chunk_file_ast(Path("test.rs"), RUST_CODE, "rust")
        assert len(chunks) >= 3
        types = [c.node_type for c in chunks]
        assert "function_item" in types
        assert "struct_item" in types
        assert "impl_item" in types
        names = [c.name for c in chunks]
        assert "greet" in names
        assert "Config" in names

    def test_unsupported_language_returns_empty(self):
        chunks = _chunk_file_ast(Path("test.go"), "package main\nfunc main() {}", "go")
        assert chunks == []

    def test_empty_file_returns_empty(self):
        chunks = _chunk_file_ast(Path("empty.py"), "", "python")
        assert chunks == []

    def test_no_definitions_returns_empty(self):
        # file with only imports and assignments — no functions/classes
        code = "import os\nx = 1\ny = 2\n"
        chunks = _chunk_file_ast(Path("simple.py"), code, "python")
        assert chunks == [] # triggers fallback in indexer

    def test_preamble_included(self):
        chunks = _chunk_file_ast(Path("test.py"), PYTHON_CODE, "python")
        preambles = [c for c in chunks if c.node_type == "preamble"]
        assert len(preambles) == 1
        assert "import os" in preambles[0].content

    def test_chunk_line_numbers(self):
        chunks = _chunk_file_ast(Path("test.py"), PYTHON_CODE, "python")
        for c in chunks:
            assert c.start_line >= 0
            assert c.end_line >= c.start_line
            assert c.line_count >= 1


# ── large chunk splitting ─────────────────────────────────────────────

@pytest.mark.skipif(not TS_AVAILABLE, reason="tree-sitter not installed")
class TestLargeChunkSplitting:
    def _make_big_class(self, n_methods=60):
        methods = []
        for i in range(n_methods):
            methods.append(
                f"    def method_{i}(self):\n"
                + "\n".join(f"        x{j} = {j}" for j in range(8))
                + f"\n        return x0"
            )
        return "class BigClass:\n" + "\n".join(methods)

    def test_large_class_split(self):
        code = self._make_big_class(60)
        lines = code.count("\n") + 1
        assert lines > MAX_CHUNK_LINES
        chunks = _chunk_file_ast(Path("big.py"), code, "python")
        # should be split into header + individual methods
        assert len(chunks) > 1
        # no single chunk should exceed MAX_CHUNK_LINES (methods are small)
        for c in chunks:
            assert c.line_count <= MAX_CHUNK_LINES

    def test_small_class_not_split(self):
        code = "class Small:\n    def a(self): pass\n    def b(self): pass\n"
        chunks = _chunk_file_ast(Path("small.py"), code, "python")
        class_chunks = [c for c in chunks if c.node_type == "class_definition"]
        assert len(class_chunks) == 1 # not split


# ── description generation ────────────────────────────────────────────

@pytest.mark.skipif(not TS_AVAILABLE, reason="tree-sitter not installed")
class TestChunkDescriptions:
    def test_python_docstring_extracted(self):
        chunks = _chunk_file_ast(Path("test.py"), PYTHON_CODE, "python")
        greet = next(c for c in chunks if c.name == "greet")
        desc = _describe_chunk(greet)
        assert "Say hello" in desc

    def test_rust_doc_comment(self):
        chunks = _chunk_file_ast(Path("test.rs"), RUST_CODE, "rust")
        greet_chunks = [c for c in chunks if c.name == "greet"]
        if greet_chunks:
            desc = _describe_chunk(greet_chunks[0])
            assert "simple greeter" in desc.lower() or "greet" in desc.lower()

    def test_preamble_description(self):
        chunks = _chunk_file_ast(Path("test.py"), PYTHON_CODE, "python")
        preamble = next(c for c in chunks if c.node_type == "preamble")
        desc = _describe_chunk(preamble)
        assert "import" in desc.lower()

    def test_fallback_description(self):
        chunk = CodeChunk(
            filepath="test.py", start_line=10, end_line=20,
            content="def foo(): pass", node_type="function_definition",
            name="foo", language="python",
        )
        desc = _describe_chunk(chunk)
        assert "foo" in desc
        assert "test.py" in desc


# ── DB schema & indexer integration ───────────────────────────────────

@pytest.mark.skipif(not TS_AVAILABLE, reason="tree-sitter not installed")
class TestIndexerIntegration:
    def test_index_stores_ast_metadata(self, tmp_repo):
        idx = CodebaseIndexer(tmp_repo)
        stats = idx.index(force=True)
        assert stats.total_files >= 5
        assert stats.total_chunks > 0
        assert stats.ast_chunks > 0

    def test_search_returns_metadata(self, tmp_repo):
        idx = CodebaseIndexer(tmp_repo)
        idx.index(force=True)
        results = idx.search("greet")
        assert len(results) > 0
        r = results[0]
        assert r.node_type != "" # AST metadata present
        assert r.name != ""

    def test_search_result_to_dict(self, tmp_repo):
        idx = CodebaseIndexer(tmp_repo)
        idx.index(force=True)
        results = idx.search("greet")
        assert len(results) > 0
        d = results[0].to_dict()
        assert "nodeType" in d
        assert "name" in d
        assert "startLine" in d

    def test_incremental_reindex(self, tmp_repo):
        idx = CodebaseIndexer(tmp_repo)
        stats1 = idx.index(force=True)
        stats2 = idx.index(force=False) # no changes
        assert stats2.total_chunks == stats1.total_chunks
        # modify a file
        (tmp_repo / "main.py").write_text(PYTHON_CODE + "\ndef extra(): pass\n")
        stats3 = idx.index(force=False) # only main.py re-indexed
        assert stats3.total_chunks != stats1.total_chunks

    def test_fallback_for_non_ast_language(self, tmp_repo):
        idx = CodebaseIndexer(tmp_repo)
        idx.index(force=True)
        results = idx.search("key value")
        # data.json should be indexed via fallback chunking
        json_results = [r for r in results if "json" in r.file_path]
        if json_results:
            assert json_results[0].node_type == "" # no AST metadata

    def test_schema_migration(self, tmp_repo):
        # create an old-schema DB
        import sqlite3
        idx_dir = tmp_repo / ".poor-cli" / "index"
        idx_dir.mkdir(parents=True, exist_ok=True)
        db_path = idx_dir / "code.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
            conn.execute("CREATE TABLE files (file_path TEXT PRIMARY KEY)")
        # opening indexer should migrate
        idx = CodebaseIndexer(tmp_repo)
        stats = idx.index(force=True)
        assert stats.total_files >= 5

    def test_description_in_fts(self, tmp_repo):
        idx = CodebaseIndexer(tmp_repo)
        idx.index(force=True)
        # search by description text should work via FTS
        results = idx.search("Say hello to someone")
        assert len(results) > 0


# ── chunk type coverage ───────────────────────────────────────────────

class TestChunkTypes:
    def test_all_languages_have_chunk_types(self):
        for lang in ("python", "lua", "javascript", "typescript", "rust"):
            assert lang in CHUNK_TYPES
            assert len(CHUNK_TYPES[lang]) > 0

    def test_code_chunk_line_count(self):
        c = CodeChunk(
            filepath="x.py", start_line=5, end_line=15,
            content="...", node_type="function_definition",
            name="foo", language="python",
        )
        assert c.line_count == 11


# ── fallback chunking (non-AST) still works ──────────────────────────

class TestFallbackChunking:
    def test_regex_chunking(self):
        code = "def a():\n    pass\ndef b():\n    pass\n"
        chunks = _chunk_content(code)
        assert len(chunks) >= 1

    def test_size_chunking(self):
        long_text = "x" * 5000
        chunks = _chunk_content(long_text)
        assert len(chunks) > 1
