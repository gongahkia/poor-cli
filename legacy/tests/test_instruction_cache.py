"""Tests for InstructionManager snapshot memoization."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from poor_cli.instructions import InstructionManager


class TestInstructionCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = Path(self.tmpdir)
        state_dir = self.repo / ".poor-cli"
        state_dir.mkdir()
        (state_dir / "memory.md").write_text("test memory content", encoding="utf-8")

    def test_consecutive_calls_return_cached(self):
        mgr = InstructionManager(self.repo)
        snap1 = mgr.build_snapshot()
        snap2 = mgr.build_snapshot()
        self.assertIs(snap1, snap2)

    def test_mtime_change_triggers_rebuild(self):
        mgr = InstructionManager(self.repo)
        snap1 = mgr.build_snapshot()
        time.sleep(0.05)
        p = self.repo / ".poor-cli" / "memory.md"
        p.write_text("updated memory", encoding="utf-8")
        os.utime(p, (time.time(), time.time()))
        snap2 = mgr.build_snapshot()
        self.assertIsNot(snap1, snap2)

    def test_invalidate_forces_rebuild(self):
        mgr = InstructionManager(self.repo)
        snap1 = mgr.build_snapshot()
        mgr.invalidate_cache()
        snap2 = mgr.build_snapshot()
        self.assertIsNot(snap1, snap2)

    def test_referenced_files_bypass_cache(self):
        mgr = InstructionManager(self.repo)
        snap1 = mgr.build_snapshot()
        snap2 = mgr.build_snapshot(referenced_files=["some/file.py"])
        self.assertIsNot(snap1, snap2)

    def test_plan_mode_change_triggers_rebuild(self):
        mgr = InstructionManager(self.repo)
        snap1 = mgr.build_snapshot(plan_mode_enabled=False)
        snap2 = mgr.build_snapshot(plan_mode_enabled=True)
        self.assertIsNot(snap1, snap2)
