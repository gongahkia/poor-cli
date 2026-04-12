"""Tests for PRD 004 — content-aware semantic cache key.

Verifies that `compute_context_hash` hashes file *contents* (not just paths
and mtimes) and folds in system-prompt / tool-schema / rules fingerprints,
so that edits invalidate cached answers.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.file_cache import content_fingerprint
from poor_cli.semantic_cache import compute_context_hash


class TestContentFingerprint(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.path = Path(self._tmpdir) / "sample.txt"
        self.path.write_text("hello")

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_fingerprint_is_stable(self):
        a = content_fingerprint(self.path)
        b = content_fingerprint(self.path)
        self.assertEqual(a, b)
        self.assertTrue(len(a) > 0)

    def test_fingerprint_changes_when_content_changes(self):
        before = content_fingerprint(self.path)
        time.sleep(0.01)
        self.path.write_text("hello world")
        after = content_fingerprint(self.path)
        self.assertNotEqual(before, after)

    def test_fingerprint_same_path_mtime_different_content(self):
        """Even if mtime is the same, different content must yield different hash.

        Simulates rare in-same-second rewrites by forcing mtime to a fixed value.
        """
        before = content_fingerprint(self.path)
        st = self.path.stat()
        self.path.write_text("goodbye")
        # Restore mtime+size-is-different case: pin mtime to pre-write time.
        os.utime(self.path, (st.st_atime, st.st_mtime))
        after = content_fingerprint(self.path)
        # Size differs ("hello" vs "goodbye"), so memo key must reflect that.
        self.assertNotEqual(before, after)

    def test_fingerprint_missing_file(self):
        missing = Path(self._tmpdir) / "does_not_exist.txt"
        h = content_fingerprint(missing)
        self.assertTrue(len(h) > 0)  # stable sentinel, no crash

    def test_fingerprint_cached_by_mtime(self):
        """Unchanged files should not be re-hashed on repeat calls."""
        content_fingerprint(self.path)  # warm cache
        with patch("poor_cli.file_cache._hash_file_bytes") as mock_hash:
            mock_hash.return_value = "SHOULD_NOT_BE_CALLED"
            content_fingerprint(self.path)
            content_fingerprint(self.path)
            self.assertEqual(mock_hash.call_count, 0)


class TestContextHashContentAware(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.file = Path(self._tmpdir) / "ctx.py"
        self.file.write_text("x = 1\n")

    def tearDown(self):
        if self.file.exists():
            self.file.unlink()

    def test_key_changes_when_file_content_changes(self):
        h1 = compute_context_hash(context_files=[str(self.file)])
        time.sleep(0.01)
        self.file.write_text("x = 2\n")
        h2 = compute_context_hash(context_files=[str(self.file)])
        self.assertNotEqual(h1, h2)

    def test_key_stable_when_nothing_changes(self):
        h1 = compute_context_hash(context_files=[str(self.file)])
        h2 = compute_context_hash(context_files=[str(self.file)])
        self.assertEqual(h1, h2)

    def test_key_changes_when_system_prompt_changes(self):
        h1 = compute_context_hash(
            context_files=[str(self.file)], system_prompt_hash="sp_v1"
        )
        h2 = compute_context_hash(
            context_files=[str(self.file)], system_prompt_hash="sp_v2"
        )
        self.assertNotEqual(h1, h2)

    def test_key_changes_when_tool_schema_changes(self):
        h1 = compute_context_hash(
            context_files=[str(self.file)], tool_schema_hash="ts_v1"
        )
        h2 = compute_context_hash(
            context_files=[str(self.file)], tool_schema_hash="ts_v2"
        )
        self.assertNotEqual(h1, h2)

    def test_key_changes_when_rules_change(self):
        h1 = compute_context_hash(
            context_files=[str(self.file)], rules_hash="rules_v1"
        )
        h2 = compute_context_hash(
            context_files=[str(self.file)], rules_hash="rules_v2"
        )
        self.assertNotEqual(h1, h2)

    def test_stale_cache_regression_from_readme_example(self):
        """Regression for LEARNING.md §2.1:
        user edits file, re-asks same question, must NOT get stale cached answer.
        The check here is at the key level: same paths, same model, different
        file contents → different keys → guaranteed miss.
        """
        h_before = compute_context_hash(
            context_files=[str(self.file)], model_name="mX"
        )
        time.sleep(0.01)
        self.file.write_text("# totally different content\nprint('hi')\n")
        h_after = compute_context_hash(
            context_files=[str(self.file)], model_name="mX"
        )
        self.assertNotEqual(h_before, h_after)


class TestSchemaMigration(unittest.TestCase):
    """PRD 004: old cache entries must be wiped when the key algorithm bumps."""

    def test_legacy_db_is_wiped_on_load(self):
        import sqlite3

        from poor_cli.semantic_cache import CACHE_SCHEMA_VERSION, SemanticCache

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "legacy.db"
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE semantic_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    query_hash TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    response TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    model_name TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    last_hit_at REAL,
                    hit_count INTEGER DEFAULT 0,
                    response_tokens_est INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                "INSERT INTO semantic_cache "
                "(query, query_hash, context_hash, response, embedding, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("old q", "qh", "path-only-hash", "stale", "[]", time.time()),
            )
            conn.commit()
            conn.close()

            cache = SemanticCache(db_path=db_path)
            try:
                conn = sqlite3.connect(str(db_path))
                count = conn.execute(
                    "SELECT COUNT(*) FROM semantic_cache"
                ).fetchone()[0]
                version_row = conn.execute(
                    "SELECT value FROM semantic_cache_meta WHERE key='schema_version'"
                ).fetchone()
                conn.close()
            finally:
                cache.close()
            self.assertEqual(count, 0)
            self.assertIsNotNone(version_row)
            self.assertEqual(int(version_row[0]), CACHE_SCHEMA_VERSION)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
