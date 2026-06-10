"""Tests for selective failure amnesia."""

import asyncio
import unittest
from unittest.mock import AsyncMock

from poor_cli.failure_amnesia import (
    AMNESIA_MARKER,
    AmnesiaResult,
    FailureAmnesia,
    FailureDetector,
    FailureLesson,
    LessonExtractor,
    MIN_TRACE_TOKENS,
    TrackedFailure,
)


def _tool_msg(name: str, content: str, **extra) -> dict:
    msg = {"role": "tool", "name": name, "content": content}
    msg.update(extra)
    return msg


def _user_msg(content: str) -> dict:
    return {"role": "user", "content": content}


def _asst_msg(content: str) -> dict:
    return {"role": "assistant", "content": content}


def _big_trace(label: str = "error") -> str:
    """generate a failure trace large enough to pass MIN_TRACE_TOKENS threshold."""
    return f"Traceback (most recent call last):\n" + "\n".join(
        f'  File "module_{i}.py", line {i}, in func_{i}\n    raise RuntimeError("{label} {i}")'
        for i in range(30)
    ) + f"\nRuntimeError: {label} final"


class FailureDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = FailureDetector()

    def test_detects_traceback(self):
        msg = _tool_msg("bash", "Traceback (most recent call last):\n  File x\nRuntimeError: boom")
        self.assertTrue(self.detector.is_failure(msg))

    def test_detects_exit_code(self):
        msg = _tool_msg("bash", "command failed with exit code 1")
        self.assertTrue(self.detector.is_failure(msg))

    def test_ignores_exit_code_zero(self):
        msg = _tool_msg("bash", "exit code 0 — success")
        # exit code 0 won't match the non-zero branch, but "success" isn't a failure pattern
        # however _FAILURE_RE won't match "exit code 0" since it matches exit code [1-9]
        # but the general _FAILURE_RE won't match either since no failure keyword
        self.assertFalse(self.detector.is_failure(msg))

    def test_ignores_non_tool(self):
        msg = {"role": "user", "content": "Traceback error here"}
        self.assertFalse(self.detector.is_failure(msg))

    def test_detects_permission_denied(self):
        msg = _tool_msg("bash", "x " * 60 + "Permission denied: /root/secret")
        self.assertTrue(self.detector.is_failure(msg))

    def test_size_threshold(self):
        small = _tool_msg("bash", "error")
        big = _tool_msg("bash", _big_trace())
        self.assertFalse(self.detector.is_large_enough(small))
        self.assertTrue(self.detector.is_large_enough(big))

    def test_find_failures_returns_tracked(self):
        history = [
            _tool_msg("bash", _big_trace("fail1")),
            _tool_msg("bash", "ok"),
            _tool_msg("bash", _big_trace("fail2")),
        ]
        failures = self.detector.find_failures(history)
        self.assertEqual(len(failures), 2)
        self.assertEqual(failures[0].index, 0)
        self.assertEqual(failures[1].index, 2)


class LessonExtractorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = LessonExtractor()

    def test_prompt_under_100_tokens(self):
        prompt = self.extractor.build_prompt("x" * 500)
        # extraction prompt ~14 tokens + truncated input ~75 tokens = well under 100
        token_est = len(prompt) // 4
        self.assertLess(token_est, 100)

    def test_heuristic_fallback(self):
        failure = TrackedFailure(
            index=0, tool_name="bash",
            content="FileNotFoundError: /foo/bar.py not found\nmore details\nstack trace",
            token_count=100,
        )
        lesson = asyncio.run(
            self.extractor.extract(failure, callback=None)
        )
        self.assertIsInstance(lesson, FailureLesson)
        self.assertIn("FileNotFoundError", lesson.error_type)
        self.assertGreater(lesson.tokens_saved, 0)

    def test_callback_extraction(self):
        callback = AsyncMock(return_value="file was at /correct/path.py")
        failure = TrackedFailure(
            index=0, tool_name="read_file",
            content=_big_trace(),
            token_count=200,
        )
        lesson = asyncio.run(
            self.extractor.extract(failure, callback=callback)
        )
        callback.assert_called_once()
        self.assertIn("/correct/path.py", lesson.lesson)

    def test_callback_failure_uses_heuristic(self):
        callback = AsyncMock(side_effect=RuntimeError("API down"))
        failure = TrackedFailure(
            index=0, tool_name="bash",
            content="RuntimeError: something broke\nstack\ntrace",
            token_count=50,
        )
        lesson = asyncio.run(
            self.extractor.extract(failure, callback=callback)
        )
        self.assertIsInstance(lesson, FailureLesson)


class FailureAmnesiaTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_no_failures_passthrough(self):
        history = [_user_msg("hello"), _asst_msg("hi")]
        result = self._run(FailureAmnesia().process_history(history))
        self.assertEqual(result.failures_pruned, 0)
        self.assertEqual(len(result.history), 2)

    def test_resolved_failure_pruned(self):
        """failure followed by success from same tool -> pruned."""
        history = [
            _tool_msg("bash", _big_trace("attempt1")),
            _tool_msg("bash", "success output here"),
            _user_msg("looks good"),
            _asst_msg("done"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        self.assertEqual(result.failures_pruned, 1)
        self.assertIn(AMNESIA_MARKER, result.history[0]["content"])
        self.assertGreater(result.tokens_saved, 0)

    def test_unresolved_failure_preserved(self):
        """failure with no subsequent success -> not pruned."""
        history = [
            _tool_msg("bash", _big_trace()),
            _user_msg("what happened?"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        self.assertEqual(result.failures_pruned, 0)
        self.assertNotIn(AMNESIA_MARKER, result.history[0]["content"])

    def test_most_recent_unresolved_failure_never_pruned(self):
        """the last failure is kept if unresolved, even if older ones are pruned."""
        history = [
            _tool_msg("bash", _big_trace("old")),
            _tool_msg("bash", "ok"),
            _tool_msg("bash", _big_trace("recent_unresolved")),
            _user_msg("hmm"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        # first resolved -> pruned, second unresolved -> kept
        self.assertEqual(result.failures_pruned, 1)
        self.assertIn(AMNESIA_MARKER, result.history[0]["content"])
        self.assertNotIn(AMNESIA_MARKER, result.history[2]["content"])

    def test_user_referenced_failure_preserved(self):
        """failure user mentions -> not pruned."""
        history = [
            _tool_msg("bash", _big_trace()),
            _tool_msg("bash", "ok"),
            _user_msg("about that error earlier, can you explain?"),
            _asst_msg("sure"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        self.assertEqual(result.failures_pruned, 0)

    def test_acceptance_3_failures_1_success(self):
        """spec acceptance: 3 failed tool calls -> 1 success, 3 traces replaced."""
        history = [
            _tool_msg("bash", _big_trace("fail1")),
            _asst_msg("trying different approach"),
            _tool_msg("bash", _big_trace("fail2")),
            _asst_msg("one more try"),
            _tool_msg("bash", _big_trace("fail3")),
            _tool_msg("bash", "it works now! success"),
            _user_msg("great"),
            _asst_msg("fixed it"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        # all 3 failures resolved (same tool succeeded after) -> all 3 pruned
        self.assertEqual(result.failures_pruned, 3)
        self.assertIn(AMNESIA_MARKER, result.history[0]["content"])
        self.assertIn(AMNESIA_MARKER, result.history[2]["content"])
        self.assertIn(AMNESIA_MARKER, result.history[4]["content"])
        self.assertGreater(result.tokens_saved, 0)

    def test_tokens_saved_accumulates(self):
        amnesia = FailureAmnesia()
        history = [
            _tool_msg("bash", _big_trace()),
            _tool_msg("bash", "ok"),
            _user_msg("next task"),
        ]
        self._run(amnesia.process_history(history))
        self.assertGreater(amnesia.tokens_saved, 0)

    def test_lesson_marker_format(self):
        lesson = FailureLesson(
            failed_action="bash call",
            error_type="RuntimeError",
            lesson="file path was wrong",
            original_tokens=500,
            lesson_tokens=20,
        )
        marker = lesson.to_marker()
        self.assertTrue(marker.startswith(AMNESIA_MARKER))
        self.assertIn("RuntimeError", marker)
        self.assertIn("file path was wrong", marker)

    def test_small_failures_ignored(self):
        """failures below MIN_TRACE_TOKENS threshold are not worth amnesia-ing."""
        history = [
            _tool_msg("bash", "error"),  # too small
            _tool_msg("bash", "ok"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        self.assertEqual(result.failures_pruned, 0)

    def test_assistant_resolved_keyword(self):
        """assistant saying 'fixed' marks failure as resolved -> pruned."""
        history = [
            _tool_msg("bash", _big_trace()),
            _asst_msg("I fixed the issue by changing the path"),
            _user_msg("thanks"),
        ]
        result = self._run(FailureAmnesia().process_history(history))
        # resolved via assistant keyword -> pruned
        self.assertEqual(result.failures_pruned, 1)
        self.assertIn(AMNESIA_MARKER, result.history[0]["content"])


class EconomyIntegrationTests(unittest.TestCase):
    def test_failure_amnesia_tracking(self):
        from poor_cli.economy import EconomySavingsTracker
        tracker = EconomySavingsTracker()
        tracker.record_failure_amnesia(500)
        summary = tracker.get_summary()
        self.assertEqual(summary["tokens_saved_by_failure_amnesia"], 500)

    def test_failure_amnesia_in_money_saved(self):
        from poor_cli.economy import EconomySavingsTracker
        tracker = EconomySavingsTracker()
        tracker.record_failure_amnesia(1000)
        money = tracker.get_money_saved()
        self.assertGreater(money, 0)


if __name__ == "__main__":
    unittest.main()
