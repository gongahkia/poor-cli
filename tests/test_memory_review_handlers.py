"""Tests for MH4 memoryReview RPC + CLI surface."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.memory_review import stage_pending_memories
from poor_cli.server.handlers.memory import MemoryHandlersMixin


class _Ctx(MemoryHandlersMixin):
    pass


class MemoryReviewRPCHandlersTests(unittest.TestCase):
    def _seed(self, base: Path) -> MemoryManager:
        mgr = MemoryManager(base / ".poor-cli")
        mgr.save(MemoryEntry(name="live", description="d", type="project", content="x"))
        stage_pending_memories(mgr, [
            MemoryEntry(name="cand a", description="d", type="feedback", content="prefer X", source_session_id="s1"),
            MemoryEntry(name="cand b", description="d", type="project", content="y", source_session_id="s1"),
        ])
        return mgr

    def test_review_list_returns_pending_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("poor_cli.server.handlers.memory.Path") as path_mock:
                # MemoryManager() with no arg uses ~/.poor-cli — point HOME at tmp
                pass
            # use HOME override since the handler default-constructs MemoryManager
            import os
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                ctx = _Ctx()
                result = asyncio.run(ctx.handle_memory_review_list({}))
            names = {e["name"] for e in result["pending"]}
            self.assertEqual(names, {"cand a", "cand b"})

    def test_review_accept_moves_to_live(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                mgr = self._seed(Path(tmp))
                pending = [e for e in mgr._entries.values()]  # noqa: F841 (load live)
                from poor_cli.memory_review import list_pending
                target = list_pending(mgr)[0]
                ctx = _Ctx()
                result = asyncio.run(ctx.handle_memory_review_accept({"filename": target.filename}))
                self.assertTrue(result["accepted"])
                # live store now has it
                live = MemoryManager(Path(tmp) / ".poor-cli")
                live.load()
                self.assertIsNotNone(live.get(target.name, record_hit=False))

    def test_review_reject_drops_pending(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                mgr = self._seed(Path(tmp))
                from poor_cli.memory_review import list_pending
                target = list_pending(mgr)[0]
                ctx = _Ctx()
                result = asyncio.run(ctx.handle_memory_review_reject({"filename": target.filename}))
                self.assertTrue(result["rejected"])

    def test_review_bulk_accept(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                ctx = _Ctx()
                result = asyncio.run(ctx.handle_memory_review_bulk({"action": "accept"}))
                self.assertEqual(set(result["accepted"]), {"cand a", "cand b"})

    def test_review_bulk_unknown_action(self):
        ctx = _Ctx()
        result = asyncio.run(ctx.handle_memory_review_bulk({"action": "noop"}))
        self.assertIn("error", result)


class MemoryReviewCLITests(unittest.TestCase):
    def test_cli_review_lists_pending(self):
        import io, os, sys
        from poor_cli.cli.state_cmds import run_memory_mode
        with tempfile.TemporaryDirectory() as tmp:
            original_cwd = os.getcwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, original_cwd)
            with patch.dict(os.environ, {"HOME": tmp}):
                mgr = MemoryManager(Path(tmp) / ".poor-cli", repo_root=Path(tmp), prefer_agent_rules=False)
                stage_pending_memories(mgr, [MemoryEntry(name="p1", description="d", type="feedback", content="x")])
                buf = io.StringIO()
                sys_stdout = sys.stdout
                sys.stdout = buf
                try:
                    rc = run_memory_mode(["review"])
                finally:
                    sys.stdout = sys_stdout
                self.assertEqual(rc, 0)
                self.assertIn("p1", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
