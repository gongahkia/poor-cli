"""Tests for smart history pruning."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from poor_cli.config import Config
from poor_cli.context_optimizer import TieredContextCompactor
from poor_cli.history import HistoryManager
from poor_cli.history_pruning import HistoryPruner


class _ProviderStub:
    def __init__(self, history, *, max_context_tokens=1000):
        self._history = [dict(message) for message in history]
        self._max_context_tokens = max_context_tokens

    def get_capabilities(self):
        return SimpleNamespace(max_context_tokens=self._max_context_tokens)

    def get_history(self):
        return [dict(message) for message in self._history]

    def set_history(self, messages):
        self._history = [dict(message) for message in messages]


class HistoryPruningTests(unittest.TestCase):
    def test_failed_then_retried_tools_are_pruned_first(self):
        history = []
        for index in range(5):
            history.append({"role": "tool", "name": "bash", "content": f"Traceback\nfailed retry {index}"})
            history.append({"role": "tool", "name": "bash", "content": f"success retry {index}"})
        history.append({"role": "user", "content": "Current request for auth.py"})
        history.append({"role": "assistant", "content": "Working on auth.py now."})

        result = HistoryPruner().prune(history, target_tokens=0, mode="balanced", trigger="auto")

        self.assertEqual(len(result.pruned_turns), 5)
        self.assertTrue(all(turn.primary_reason == "failed_retry_succeeded" for turn in result.pruned_turns))
        kept = [message["content"] for message in result.history]
        self.assertTrue(any("success retry 0" in content for content in kept))
        self.assertTrue(result.notification.startswith("[auto-pruned]"))

    def test_never_prunes_current_turn_last_user_or_pinned_context(self):
        history = [
            {"role": "assistant", "content": "Exploration 1"},
            {"role": "assistant", "content": "Exploration 2"},
            {"role": "tool", "name": "read_file", "content": "old read", "metadata": {"file_path": "svc.py"}},
            {
                "role": "user",
                "content": "Pinned file context\n--- file: svc.py",
                "metadata": {"contextSource": "pinned_context"},
            },
            {"role": "user", "content": "Current request touches svc.py"},
            {"role": "assistant", "content": "Current turn response for svc.py"},
        ]

        result = HistoryPruner().prune(history, target_tokens=1, mode="aggressive", trigger="auto")
        kept = [message["content"] for message in result.history]

        self.assertIn("Pinned file context\n--- file: svc.py", kept)
        self.assertIn("Current request touches svc.py", kept)
        self.assertIn("Current turn response for svc.py", kept)

    def test_history_manager_scores_and_stores_pruning_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = HistoryManager(db_path=Path(tmpdir) / "history.db")
            manager.start_session("test-model")
            manager.add_message("user", "Refactor auth.py")
            manager.add_message("tool", "Traceback\nfailed read", metadata={"file_path": "auth.py"})

            scored = manager.score_messages_for_pruning(active_files=["auth.py"])

            self.assertEqual(len(scored), 2)
            first = manager.current_session.messages[0].get_pruning_metadata()
            second = manager.current_session.messages[1].get_pruning_metadata()
            self.assertIn("score", first)
            self.assertIn("components", second)
            self.assertTrue(first["protected"])

    def test_stale_file_reads_are_marked_superseded(self):
        history = [
            {"role": "tool", "name": "read_file", "content": "version 1", "metadata": {"file_path": "app.py"}},
            {"role": "assistant", "content": "Noted app.py"},
            {"role": "tool", "name": "read_file", "content": "version 2", "metadata": {"file_path": "app.py"}},
            {"role": "user", "content": "Current request for app.py"},
        ]

        result = HistoryPruner().prune(history, target_tokens=0, mode="balanced", trigger="auto")

        self.assertTrue(any(turn.primary_reason == "stale_file_read" for turn in result.pruned_turns))


class CorePruningIntegrationTests(unittest.TestCase):
    def _make_core(self, history, *, max_context_tokens=1000):
        from poor_cli.core import PoorCLICore

        core = object.__new__(PoorCLICore)
        core._initialized = True
        core.config = Config()
        core.provider = _ProviderStub(history, max_context_tokens=max_context_tokens)
        core.history_adapter = MagicMock()
        core._tiered_compactor = TieredContextCompactor()
        core._last_compaction_status = {"state": "idle"}
        core._auto_history_compact_task = None
        core._system_instruction = ""
        core._save_transcript = MagicMock(return_value=None)
        core._pending_events = []
        core._record_compaction_status = lambda payload: payload
        core._resolve_tiered_compaction_mode = lambda strategy: strategy if strategy in {"gentle", "balanced", "aggressive"} else "balanced"
        core._resolve_auto_compaction_settings = lambda: (0.7, 0.4)
        core._summarize_compaction_chunk = MagicMock()
        return core

    def test_compaction_records_pruning_sidecar_and_notification(self):
        history = []
        for index in range(5):
            history.append({"role": "tool", "name": "bash", "content": f"Traceback\nfailed retry {index}"})
            history.append({"role": "tool", "name": "bash", "content": f"success retry {index}"})
        history.append({"role": "user", "content": "Current request for auth.py"})
        history.append({"role": "assistant", "content": "Working on auth.py now."})

        core = self._make_core(history, max_context_tokens=200)
        with tempfile.TemporaryDirectory() as tmpdir, patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
            status = asyncio.run(
                core._compact_tiered_context(
                    history,
                    len(history),
                    strategy="aggressive",
                    trigger="auto",
                    allow_model_summary=False,
                )
            )

            self.assertGreater(status["pruned_turns"], 0)
            self.assertTrue(status["pruning_summary"].startswith("[auto-pruned]"))
            self.assertTrue(Path(status["pruning_sidecar_path"]).exists())
            payload = json.loads(Path(status["pruning_sidecar_path"]).read_text())
            self.assertEqual(len(payload["turns"]), status["pruned_turns"])
            self.assertTrue(any(event.data["phase"] == "history_pruning" for event in core._pending_events))


if __name__ == "__main__":
    unittest.main()
