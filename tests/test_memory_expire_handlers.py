"""Tests for MH3 expire RPC + CLI."""

from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.server.handlers.memory import MemoryHandlersMixin


class _Ctx(MemoryHandlersMixin):
    pass


def _old(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class MemoryExpireRPCHandlersTests(unittest.TestCase):
    def _seed(self, base: Path) -> MemoryManager:
        mgr = MemoryManager(base / ".poor-cli")
        mgr.save(MemoryEntry(
            name="stale-ref", description="d", type="reference", content="x",
            created_at=_old(200), updated_at=_old(200), last_accessed_at=_old(200),
        ))
        mgr.save(MemoryEntry(
            name="fresh-feedback", description="d", type="feedback", content="x",
        ))
        return mgr

    def test_expiring_lists_stale_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                ctx = _Ctx()
                result = asyncio.run(ctx.handle_memory_expiring({}))
                names = {e["name"] for e in result["expiring"]}
                self.assertIn("stale-ref", names)
                self.assertNotIn("fresh-feedback", names)

    def test_expire_run_dry_does_not_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                ctx = _Ctx()
                summary = asyncio.run(ctx.handle_memory_expire_run({"dryRun": True}))
                self.assertIn("stale-ref.md", summary["archived"])
                # still on disk
                fresh_mgr = MemoryManager(Path(tmp) / ".poor-cli")
                fresh_mgr.load()
                self.assertIsNotNone(fresh_mgr.get("stale-ref", record_hit=False))

    def test_expire_run_writes_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                ctx = _Ctx()
                summary = asyncio.run(ctx.handle_memory_expire_run({}))
                self.assertEqual(len(summary["archived"]), 1)
                fresh_mgr = MemoryManager(Path(tmp) / ".poor-cli")
                fresh_mgr.load()
                self.assertIsNone(fresh_mgr.get("stale-ref", record_hit=False))


class MemoryExpireCLITests(unittest.TestCase):
    def _seed(self, base: Path) -> None:
        mgr = MemoryManager(base / ".poor-cli")
        mgr.save(MemoryEntry(
            name="stale-ref", description="d", type="reference", content="x",
            created_at=_old(200), updated_at=_old(200), last_accessed_at=_old(200),
        ))

    def test_cli_expire_lists_candidates(self):
        from poor_cli.cli.state_cmds import run_memory_mode
        with tempfile.TemporaryDirectory() as tmp:
            original_cwd = os.getcwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, original_cwd)
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                buf = io.StringIO()
                old = sys.stdout
                sys.stdout = buf
                try:
                    rc = run_memory_mode(["expire"])
                finally:
                    sys.stdout = old
                self.assertEqual(rc, 0)
                self.assertIn("stale-ref", buf.getvalue())
                self.assertIn("--archive", buf.getvalue())

    def test_cli_expire_archive_dry_run(self):
        from poor_cli.cli.state_cmds import run_memory_mode
        with tempfile.TemporaryDirectory() as tmp:
            original_cwd = os.getcwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, original_cwd)
            with patch.dict(os.environ, {"HOME": tmp}):
                self._seed(Path(tmp))
                buf = io.StringIO()
                old = sys.stdout
                sys.stdout = buf
                try:
                    rc = run_memory_mode(["expire", "--archive", "--dry-run"])
                finally:
                    sys.stdout = old
                self.assertEqual(rc, 0)
                self.assertIn("would archive", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
