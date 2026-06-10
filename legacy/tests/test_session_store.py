"""Tests for canonical session snapshot persistence."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from poor_cli.__main__ import _build_resume_prefix
from poor_cli.session_store import SessionStore


class TestSessionStore(unittest.TestCase):
    def test_save_list_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            repo = Path(repo_tmp)
            store = SessionStore(repo)
            entry = store.save(
                "sess-1",
                {
                    "provider": "openai",
                    "model": "gpt-5.1",
                    "history": [{"role": "user", "content": "hello"}],
                },
            )

            self.assertEqual(entry["sessionId"], "sess-1")
            self.assertEqual(entry["messageCount"], 1)
            self.assertTrue(Path(entry["path"]).is_file())

            sessions = store.list(limit=5)
            self.assertEqual(len(sessions), 1)
            loaded = store.load("sess-1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["provider"], "openai")
            self.assertEqual(loaded["model"], "gpt-5.1")
            self.assertEqual(len(loaded["history"]), 1)

    def test_load_latest_reads_latest_snapshot_file(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            repo = Path(repo_tmp)
            store = SessionStore(repo)
            first = store.save(
                "sess-a",
                {
                    "provider": "openai",
                    "model": "gpt-5.1",
                    "history": [{"role": "user", "content": "first"}],
                },
            )
            second = store.save(
                "sess-b",
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                    "history": [{"role": "user", "content": "second"}],
                },
            )

            latest = store.load_latest()
            self.assertIsNotNone(latest)
            self.assertEqual(latest["session_id"], second["sessionId"])
            self.assertEqual(latest["model"], "claude-sonnet-4-20250514")
            self.assertNotEqual(first["path"], second["path"])

    def test_resume_prefix_prefers_canonical_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            repo = Path(repo_tmp)
            store = SessionStore(repo)
            store.save(
                "sess-xyz",
                {
                    "provider": "openai",
                    "model": "gpt-5.1",
                    "history": [
                        {"role": "user", "content": "Question"},
                        {"role": "model", "content": "Answer"},
                    ],
                },
            )

            original_cwd = Path.cwd()
            os.chdir(repo)
            try:
                prefix = _build_resume_prefix()
            finally:
                os.chdir(original_cwd)

            self.assertIn("[Recent saved session context]", prefix)
            self.assertIn("Session: sess-xyz", prefix)
            self.assertIn("user: Question", prefix)
            self.assertIn("assistant: Answer", prefix)

