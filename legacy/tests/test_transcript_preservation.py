"""Tests for raw transcript preservation during compaction."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestTranscriptPreservation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.transcript_dir = Path(self.tmpdir) / ".poor-cli" / "transcripts"

    def _make_core(self, preserve=True):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = MagicMock()
        core.config.context_compression.preserve_transcripts = preserve
        core.config.context_compression.transcript_dir = str(self.transcript_dir)
        core._last_run_id = "test-run-123"
        return core

    def test_save_transcript_creates_json(self):
        core = self._make_core()
        history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            path = core._save_transcript(history)
        self.assertIsNotNone(path)
        data = json.loads(Path(path).read_text())
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["role"], "user")

    def test_preserve_false_skips(self):
        core = self._make_core(preserve=False)
        history = [{"role": "user", "content": "hello"}]
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            path = core._save_transcript(history)
        self.assertIsNone(path)
        self.assertFalse(self.transcript_dir.exists())

    def test_transcript_file_is_valid_json(self):
        core = self._make_core()
        history = [{"role": "user", "content": "test"}, {"role": "assistant", "content": "ok"}]
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            path = core._save_transcript(history)
        parsed = json.loads(Path(path).read_text())
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)

    def test_filename_contains_session_id(self):
        core = self._make_core()
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            path = core._save_transcript([{"role": "user", "content": "x"}])
        self.assertIn("test-run-123", Path(path).name)
