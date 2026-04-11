"""Tests for tiered context compaction."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from poor_cli.config import Config
from poor_cli.context_optimizer import TieredContextCompactor


class StubProvider:
    def __init__(self, history, *, max_context_tokens=1000, summary_text=""):
        self._history = [dict(message) for message in history]
        self._max_context_tokens = max_context_tokens
        self._summary_text = summary_text or (
            "## Session Summary (turns 1-3)\n"
            "- User asked: keep auth changes\n"
            "- Files modified/referenced: auth.py; tests/test_auth.py\n"
            "- Key decisions: kept jwt flow\n"
            "- Unresolved: add expired-token test"
        )
        self.summary_prompts = []

    async def clear_history(self):
        self._history = []

    def get_capabilities(self):
        return SimpleNamespace(max_context_tokens=self._max_context_tokens)

    def get_history(self):
        return [dict(message) for message in self._history]

    async def send_message(self, prompt):
        self.summary_prompts.append(prompt)
        return SimpleNamespace(content=self._summary_text)

    def set_history(self, messages):
        self._history = [dict(message) for message in messages]


class TestTieredContextCompactor(unittest.TestCase):
    def test_preserves_latest_turn_and_structured_summary(self):
        history = [
            {"role": "user", "content": "Refactor auth middleware in auth.py"},
            {"role": "assistant", "content": "I decided to keep jwt validation in middleware.py"},
            {"role": "tool", "name": "bash", "content": "Traceback\npermission denied\npermission denied\n"},
            {"role": "assistant", "content": "The bash attempt failed; switching to read-only inspection."},
            {"role": "user", "content": "Current request with file context\n--- file: auth.py\nTOKEN = 'x'"},
            {"role": "assistant", "content": "Latest response: auth.py updated, tests pending."},
        ]
        compactor = TieredContextCompactor()
        result = asyncio.run(
            compactor.compact(
                history,
                max_tokens=1000,
                mode="balanced",
                economy_preset="balanced",
                trigger="manual",
            )
        )
        self.assertTrue(result.summary.startswith("## Session Summary"))
        contents = [message["content"] for message in result.history]
        self.assertTrue(any("Current request with file context" in content for content in contents))
        self.assertTrue(any("Latest response: auth.py updated" in content for content in contents))
        self.assertTrue(any("Dropped noise lessons" in content for content in contents))
        self.assertFalse(any("permission denied\npermission denied" in content for content in contents[1:]))

    def test_frugal_compacts_more_than_quality(self):
        history = []
        for index in range(12):
            history.append({"role": "user", "content": f"User request {index} touching service_{index}.py"})
            history.append({"role": "assistant", "content": f"I decided to update service_{index}.py and tests/test_{index}.py"})
            history.append({"role": "tool", "name": "read_file", "content": "x" * 900})
        compactor = TieredContextCompactor()
        frugal = asyncio.run(
            compactor.compact(
                history,
                max_tokens=1600,
                mode="balanced",
                economy_preset="frugal",
                trigger="auto",
            )
        )
        quality = asyncio.run(
            compactor.compact(
                history,
                max_tokens=1600,
                mode="balanced",
                economy_preset="quality",
                trigger="manual",
            )
        )
        self.assertLessEqual(frugal.tokens_after, quality.tokens_after)
        self.assertLessEqual(frugal.messages_after, quality.messages_after)

    def test_fifty_turn_history_compacts_under_target(self):
        history = []
        for index in range(50):
            history.append({"role": "user", "content": f"Turn {index} request for feature_{index}.py with follow-up test_{index}.py"})
            history.append({"role": "assistant", "content": f"Implemented feature_{index}.py and updated tests/test_{index}.py"})
            history.append({"role": "tool", "name": "bash", "content": "build log\n" + ("x" * 1200)})
        compactor = TieredContextCompactor()
        result = asyncio.run(
            compactor.compact(
                history,
                max_tokens=2000,
                mode="aggressive",
                economy_preset="frugal",
                trigger="auto",
            )
        )
        self.assertLessEqual(result.tokens_after, 800)
        self.assertLess(result.messages_after, len(history))


class TestCoreCompactionIntegration(unittest.TestCase):
    def _make_core(self, history, *, preset="balanced", max_context_tokens=1000, summary_text=""):
        from poor_cli.core import PoorCLICore

        core = object.__new__(PoorCLICore)
        core._initialized = True
        core.config = Config()
        core.config.economy.preset = preset
        core.config.economy.auto_compress_pressure_pct = 70.0 if preset != "quality" else 0.0
        core.config.context_compression.enabled = True
        core.config.context_compression.auto_compact_threshold = 0.7
        core.config.context_compression.auto_compact_target = 0.4
        core.provider = StubProvider(history, max_context_tokens=max_context_tokens, summary_text=summary_text)
        core.history_adapter = MagicMock()
        core._tiered_compactor = TieredContextCompactor()
        core._last_compaction_status = {"state": "idle"}
        core._auto_history_compact_task = None
        core._system_instruction = ""
        core._save_transcript = MagicMock(return_value=None)
        return core

    def test_manual_compact_supports_gentle_and_aggressive(self):
        history = []
        for index in range(10):
            history.append({"role": "user", "content": f"Request {index} for auth_{index}.py"})
            history.append({"role": "assistant", "content": f"Updated auth_{index}.py and tests/test_auth_{index}.py"})
        gentle_core = self._make_core(history)
        gentle = asyncio.run(gentle_core.compact_context("gentle"))
        aggressive_core = self._make_core(history)
        aggressive = asyncio.run(aggressive_core.compact_context("aggressive"))
        self.assertEqual(gentle["mode"], "gentle")
        self.assertEqual(aggressive["mode"], "aggressive")
        self.assertIn("## Session Summary", gentle["summary"])
        self.assertLessEqual(aggressive["messages_after"], gentle["messages_after"])

    def test_auto_compaction_is_scheduled_in_background(self):
        history = []
        for index in range(8):
            history.append({"role": "user", "content": f"Context heavy request {index} for module_{index}.py " + ("x" * 200)})
            history.append({"role": "assistant", "content": f"Updated module_{index}.py and queued follow-up."})
        core = self._make_core(history, max_context_tokens=500)

        async def run():
            queued = core._schedule_auto_compaction()
            self.assertIsNotNone(queued)
            self.assertEqual(core.get_compaction_status()["state"], "queued")
            self.assertIsNotNone(core._auto_history_compact_task)
            await core._auto_history_compact_task
            return core.get_compaction_status()

        status = asyncio.run(run())
        self.assertEqual(status["state"], "done")
        self.assertEqual(status["trigger"], "auto")
        self.assertLess(status["messages_after"], status["messages_before"])
