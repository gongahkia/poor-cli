"""Tests for CB1 diff-of-diff cache wiring into ContextAssemblyOrchestrator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from poor_cli.context_assembly import ContextAssemblyOrchestrator
from poor_cli.config import Config


class _FakeFileCtx:
    def __init__(self, path: str, content: str):
        self.path = path
        self.content = content
        self.size = len(content)
        self.source = "auto"
        self.tokens_estimate = max(1, len(content) // 4)
        self.include_full_content = False


class _FakeContextResult:
    def __init__(self, files):
        self.files = files
        self.selected = files
        self.excluded = []
        self.total_tokens = sum(getattr(f, "tokens_estimate", 0) for f in files)
        self.message = ""
        self.truncated = False


class _FakeCore:
    def __init__(self, config):
        self.config = config
        self._economy_tracker = None


class DiffOfDiffOrchestratorTests(unittest.TestCase):
    def _orch(self, *, enabled: bool, min_chars: int = 100) -> ContextAssemblyOrchestrator:
        config = Config()
        config.context.diff_of_diff_cache = enabled
        config.context.diff_of_diff_min_chars = min_chars
        config.context.diff_of_diff_ttl_seconds = 60
        # isolate this test's cache from any sibling-test or cwd state
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        config.context.diff_of_diff_cache_path = str(Path(self._tmp.name) / "diff_cache.json")
        core = _FakeCore(config)
        orch = ContextAssemblyOrchestrator.__new__(ContextAssemblyOrchestrator)
        orch._core = core
        orch._last_invalidation_reason = ""
        return orch

    def _request(self, pinned=()):
        return SimpleNamespace(
            prompt="ok",
            pinned_context_files=tuple(pinned),
            context_files=(),
            context_budget_tokens=None,
            turn_id="t1",
            activate_tools=True,
        )

    def test_no_op_when_disabled(self):
        orch = self._orch(enabled=False)
        ctx = _FakeContextResult([_FakeFileCtx("/x.py", "x" * 5000)])
        original = ctx.files[0].content
        orch._apply_diff_of_diff_cache(ctx, self._request())
        self.assertEqual(ctx.files[0].content, original)
        self.assertFalse(hasattr(ctx.files[0], "diff_of_diff_mode"))

    def test_first_call_keeps_full_content(self):
        orch = self._orch(enabled=True)
        original = "line\n" * 200
        ctx = _FakeContextResult([_FakeFileCtx("/big.py", original)])
        orch._apply_diff_of_diff_cache(ctx, self._request())
        self.assertEqual(ctx.files[0].content, original)

    def test_repeat_call_with_minor_change_emits_diff(self):
        orch = self._orch(enabled=True, min_chars=100)
        original = "\n".join(f"line {i}" for i in range(80))
        modified = original.replace("line 40", "line 40 CHANGED")
        # first turn primes the cache
        ctx1 = _FakeContextResult([_FakeFileCtx("/big.py", original)])
        orch._apply_diff_of_diff_cache(ctx1, self._request())
        # second turn modifies same file — should trip diff mode
        ctx2 = _FakeContextResult([_FakeFileCtx("/big.py", modified)])
        orch._apply_diff_of_diff_cache(ctx2, self._request())
        f2 = ctx2.files[0]
        self.assertEqual(getattr(f2, "diff_of_diff_mode", "full"), "diff")
        self.assertIn("CHANGED", f2.content)
        self.assertIn("unchanged", f2.content)

    def test_small_file_skipped(self):
        orch = self._orch(enabled=True, min_chars=10000)
        ctx = _FakeContextResult([_FakeFileCtx("/tiny.py", "small")])
        orch._apply_diff_of_diff_cache(ctx, self._request())
        self.assertFalse(hasattr(ctx.files[0], "diff_of_diff_mode"))

    def test_edit_target_skipped(self):
        orch = self._orch(enabled=True)
        f = _FakeFileCtx("/edit.py", "x" * 5000)
        f.include_full_content = True
        ctx = _FakeContextResult([f])
        orch._apply_diff_of_diff_cache(ctx, self._request())
        self.assertFalse(hasattr(f, "diff_of_diff_mode"))

    def test_pinned_context_change_invalidates_cache(self):
        orch = self._orch(enabled=True)
        original = "\n".join(f"line {i}" for i in range(80))
        # warm cache under pinned set A
        ctx1 = _FakeContextResult([_FakeFileCtx("/big.py", original)])
        orch._apply_diff_of_diff_cache(ctx1, self._request(pinned=["a.py"]))
        # different pinned set -> different key -> still full mode
        ctx2 = _FakeContextResult([_FakeFileCtx("/big.py", original)])
        orch._apply_diff_of_diff_cache(ctx2, self._request(pinned=["b.py"]))
        self.assertNotEqual(getattr(ctx2.files[0], "diff_of_diff_mode", "full"), "diff")


if __name__ == "__main__":
    unittest.main()
