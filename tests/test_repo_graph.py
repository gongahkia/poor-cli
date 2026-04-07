"""Tests for repo graph symbol/import extraction and language detection."""
import re
import unittest
from pathlib import Path

from poor_cli.repo_graph import (
    _SYMBOL_PATTERNS,
    _IMPORT_PATTERNS,
    _LANG_MAP,
    _SKIP_DIRS,
)


class TestLanguageDetection(unittest.TestCase):
    def test_python_extensions(self):
        self.assertEqual(_LANG_MAP[".py"], "python")

    def test_js_extensions(self):
        self.assertEqual(_LANG_MAP[".js"], "javascript")
        self.assertEqual(_LANG_MAP[".jsx"], "javascript")

    def test_ts_extensions(self):
        self.assertEqual(_LANG_MAP[".ts"], "typescript")
        self.assertEqual(_LANG_MAP[".tsx"], "typescript")

    def test_go_extension(self):
        self.assertEqual(_LANG_MAP[".go"], "go")

    def test_rust_extension(self):
        self.assertEqual(_LANG_MAP[".rs"], "rust")

    def test_java_extension(self):
        self.assertEqual(_LANG_MAP[".java"], "java")

    def test_c_extensions(self):
        self.assertEqual(_LANG_MAP[".c"], "c")
        self.assertEqual(_LANG_MAP[".h"], "c")

    def test_unknown_extension_not_in_map(self):
        self.assertNotIn(".xyz", _LANG_MAP)


class TestSkipDirs(unittest.TestCase):
    def test_git_skipped(self):
        self.assertIn(".git", _SKIP_DIRS)

    def test_node_modules_skipped(self):
        self.assertIn("node_modules", _SKIP_DIRS)

    def test_pycache_skipped(self):
        self.assertIn("__pycache__", _SKIP_DIRS)

    def test_poor_cli_dir_skipped(self):
        self.assertIn(".poor-cli", _SKIP_DIRS)


class TestPythonSymbolRegex(unittest.TestCase):
    def _extract(self, line):
        results = []
        for pattern, kind in _SYMBOL_PATTERNS.get("python", []):
            m = re.search(pattern, line)
            if m:
                results.append((m.group(1), kind))
        return results

    def test_function_def(self):
        r = self._extract("def hello_world():")
        self.assertIn(("hello_world", "function"), r)

    def test_async_function_def(self):
        r = self._extract("async def fetch_data():")
        self.assertIn(("fetch_data", "function"), r)

    def test_class_def(self):
        r = self._extract("class MyClass:")
        self.assertIn(("MyClass", "class"), r)

    def test_indented_def(self):
        r = self._extract("    def method(self):")
        self.assertIn(("method", "function"), r)


class TestJavaScriptSymbolRegex(unittest.TestCase):
    def _extract(self, line):
        results = []
        for pattern, kind in _SYMBOL_PATTERNS.get("javascript", []):
            m = re.search(pattern, line)
            if m:
                results.append((m.group(1), kind))
        return results

    def test_function_declaration(self):
        r = self._extract("function handleClick() {")
        self.assertIn(("handleClick", "function"), r)

    def test_export_function(self):
        r = self._extract("export function getData() {")
        self.assertIn(("getData", "function"), r)

    def test_class_declaration(self):
        r = self._extract("class EventEmitter {")
        self.assertIn(("EventEmitter", "class"), r)

    def test_const_arrow(self):
        r = self._extract("const handler = async (req, res) => {")
        self.assertIn(("handler", "function"), r)


class TestGoSymbolRegex(unittest.TestCase):
    def _extract(self, line):
        results = []
        for pattern, kind in _SYMBOL_PATTERNS.get("go", []):
            m = re.search(pattern, line)
            if m:
                results.append((m.group(1), kind))
        return results

    def test_function(self):
        r = self._extract("func main() {")
        self.assertIn(("main", "function"), r)

    def test_method(self):
        r = self._extract("func (s *Server) Start() error {")
        self.assertIn(("Start", "function"), r)

    def test_struct(self):
        r = self._extract("type Config struct {")
        self.assertIn(("Config", "class"), r)

    def test_interface(self):
        r = self._extract("type Handler interface {")
        self.assertIn(("Handler", "type"), r)


class TestRustSymbolRegex(unittest.TestCase):
    def _extract(self, line):
        results = []
        for pattern, kind in _SYMBOL_PATTERNS.get("rust", []):
            m = re.search(pattern, line)
            if m:
                results.append((m.group(1), kind))
        return results

    def test_pub_fn(self):
        r = self._extract("pub fn new() -> Self {")
        self.assertIn(("new", "function"), r)

    def test_async_fn(self):
        r = self._extract("pub async fn fetch() -> Result<()> {")
        self.assertIn(("fetch", "function"), r)

    def test_struct(self):
        r = self._extract("pub struct AppState {")
        self.assertIn(("AppState", "class"), r)

    def test_enum(self):
        r = self._extract("pub enum Status {")
        self.assertIn(("Status", "type"), r)

    def test_trait(self):
        r = self._extract("pub trait Handler {")
        self.assertIn(("Handler", "type"), r)

    def test_impl(self):
        r = self._extract("impl AppState {")
        self.assertIn(("AppState", "class"), r)


class TestImportPatterns(unittest.TestCase):
    def _match(self, lang, line):
        results = []
        for pattern in _IMPORT_PATTERNS.get(lang, []):
            for m in re.finditer(pattern, line):
                results.append(m.group(1))
        return results

    def test_python_import(self):
        r = self._match("python", "import asyncio")
        self.assertIn("asyncio", r)

    def test_python_from_import(self):
        r = self._match("python", "from pathlib import Path")
        self.assertIn("pathlib", r)

    def test_js_import(self):
        r = self._match("javascript", 'import React from "react"')
        self.assertIn("react", r)

    def test_js_require(self):
        r = self._match("javascript", "const fs = require('fs')")
        self.assertIn("fs", r)

    def test_go_import(self):
        r = self._match("go", 'import "fmt"')
        self.assertIn("fmt", r)

    def test_rust_use(self):
        r = self._match("rust", "use std::path::Path;")
        self.assertIn("std::path::Path", r)

    def test_java_import(self):
        r = self._match("java", "import java.util.List;")
        self.assertIn("java.util.List", r)

    def test_c_include(self):
        r = self._match("c", '#include <stdio.h>')
        self.assertIn("stdio.h", r)


class TestTreeSitterFallback(unittest.TestCase):
    def test_treesitter_returns_none_when_unavailable(self):
        """Tree-sitter extraction should return None gracefully when not installed."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            from poor_cli.repo_graph import RepoGraph
            rg = RepoGraph(Path(tmpdir))
            result = rg._extract_symbols_treesitter("/fake.py", "def foo(): pass", "python")
            # may return None (not installed) or a list (installed) — both are valid
            self.assertTrue(result is None or isinstance(result, list))


if __name__ == "__main__":
    unittest.main()
