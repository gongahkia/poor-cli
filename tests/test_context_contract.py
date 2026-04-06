"""Tests for deterministic system/user context contract blocks."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from poor_cli.context_contract import ContextContractManager
from poor_cli.instructions import InstructionSnapshot, InstructionSource


class TestContextContractManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _instruction_snapshot(self) -> InstructionSnapshot:
        return InstructionSnapshot(
            repo_root=str(self.repo_root),
            sources=[
                InstructionSource(
                    kind="repo_root",
                    label="Repo Root AGENTS.md",
                    content="Use concise answers.",
                    path=str(self.repo_root / "AGENTS.md"),
                )
            ],
        )

    def test_user_context_includes_current_date(self) -> None:
        mgr = ContextContractManager(self.repo_root)
        snapshot = mgr.build_snapshot(
            instruction_snapshot=self._instruction_snapshot(),
        )
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertIn(f"Today's date is {today}.", snapshot.user_context)
        self.assertIn("Resolved instruction stack:", snapshot.user_context)
        self.assertIn("Use concise answers.", snapshot.user_context)

    def test_system_context_always_reports_cwd(self) -> None:
        mgr = ContextContractManager(self.repo_root)
        snapshot = mgr.build_snapshot(
            instruction_snapshot=self._instruction_snapshot(),
        )
        self.assertIn("CWD: ", snapshot.system_context)
        self.assertIn(str(self.repo_root.resolve()), snapshot.system_context)

    def test_memoized_blocks_reuse_cache_keys(self) -> None:
        mgr = ContextContractManager(self.repo_root)
        first = mgr.build_snapshot(instruction_snapshot=self._instruction_snapshot())
        first_system_key = mgr._system_cache_key
        first_user_key = mgr._user_cache_key

        second = mgr.build_snapshot(instruction_snapshot=self._instruction_snapshot())
        self.assertEqual(first.system_context, second.system_context)
        self.assertEqual(first.user_context, second.user_context)
        self.assertEqual(first_system_key, mgr._system_cache_key)
        self.assertEqual(first_user_key, mgr._user_cache_key)
