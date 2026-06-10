"""Tests for deterministic static prompt prefix blocks."""

from __future__ import annotations

import tempfile
import unittest
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
                ),
                InstructionSource(
                    kind="repo_graph",
                    label="Repo Structure",
                    content="core.py\nproviders/openai_provider.py",
                ),
            ],
        )

    def test_repo_map_precedes_instruction_stack(self) -> None:
        mgr = ContextContractManager(self.repo_root)
        snapshot = mgr.build_snapshot(instruction_snapshot=self._instruction_snapshot())
        repo_idx = snapshot.rendered_prompt_prefix.index("### Repo Structure")
        inst_idx = snapshot.rendered_prompt_prefix.index("### Repo Root AGENTS.md")
        self.assertLess(repo_idx, inst_idx)

    def test_prefix_excludes_dynamic_date(self) -> None:
        mgr = ContextContractManager(self.repo_root)
        snapshot = mgr.build_snapshot(instruction_snapshot=self._instruction_snapshot())
        self.assertNotIn("Today's date is", snapshot.rendered_prompt_prefix)
        self.assertNotIn("Current branch:", snapshot.rendered_prompt_prefix)

    def test_memoized_blocks_reuse_cache_key(self) -> None:
        mgr = ContextContractManager(self.repo_root)
        first = mgr.build_snapshot(instruction_snapshot=self._instruction_snapshot())
        first_key = mgr._cache_key

        second = mgr.build_snapshot(instruction_snapshot=self._instruction_snapshot())
        self.assertEqual(first.rendered_prompt_prefix, second.rendered_prompt_prefix)
        self.assertEqual(first_key, mgr._cache_key)
