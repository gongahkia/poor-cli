"""Tests for hierarchical memory loading and include directives."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.instructions import InstructionManager, MANAGED_MEMORY_ENV


class TestInstructionHierarchy(unittest.TestCase):
    def _base_env(self, home: str, managed_path: Path) -> dict[str, str]:
        return {
            **os.environ,
            "HOME": home,
            MANAGED_MEMORY_ENV: str(managed_path),
        }

    def test_hierarchy_order_managed_user_project_local(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed.md"
            managed.write_text("managed instructions", encoding="utf-8")

            user_dir = Path(home_tmp) / ".poor-cli"
            user_dir.mkdir(parents=True, exist_ok=True)
            (user_dir / "CLAUDE.md").write_text("user instructions", encoding="utf-8")

            (repo / "CLAUDE.md").write_text("project instructions", encoding="utf-8")
            (repo / "CLAUDE.local.md").write_text("local instructions", encoding="utf-8")

            with patch.dict(os.environ, self._base_env(home_tmp, managed)):
                snapshot = InstructionManager(repo).build_snapshot(
                    referenced_files=["src/api/main.py"]
                )

            ordered_text = "\n".join(source.content for source in snapshot.sources)
            self.assertLess(
                ordered_text.index("managed instructions"),
                ordered_text.index("user instructions"),
            )
            self.assertLess(
                ordered_text.index("user instructions"),
                ordered_text.index("project instructions"),
            )
            self.assertLess(
                ordered_text.index("project instructions"),
                ordered_text.index("local instructions"),
            )

    def test_include_directive_expands_relative_file(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed-missing.md"
            docs = repo / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            (docs / "arch.md").write_text("Architecture rule", encoding="utf-8")
            (repo / "CLAUDE.md").write_text(
                "@./docs/arch.md\nAlways run tests.",
                encoding="utf-8",
            )

            with patch.dict(os.environ, self._base_env(home_tmp, managed)):
                snapshot = InstructionManager(repo).build_snapshot()

            content = "\n".join(source.content for source in snapshot.sources)
            self.assertIn("Architecture rule", content)
            self.assertIn("Always run tests.", content)
            self.assertNotIn("@./docs/arch.md", content)

    def test_path_scoped_rule_matches_referenced_file_glob(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed-missing.md"
            rules_dir = repo / ".claude" / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)
            (rules_dir / "api.md").write_text(
                "---\npaths:\n  - \"src/api/**\"\n---\nUse strict API validation.",
                encoding="utf-8",
            )

            with patch.dict(os.environ, self._base_env(home_tmp, managed)):
                miss_snapshot = InstructionManager(repo).build_snapshot(
                    referenced_files=["src/web/app.ts"]
                )
                hit_snapshot = InstructionManager(repo).build_snapshot(
                    referenced_files=["src/api/users.py"]
                )

            miss_text = "\n".join(source.content for source in miss_snapshot.sources)
            hit_text = "\n".join(source.content for source in hit_snapshot.sources)
            self.assertNotIn("Use strict API validation.", miss_text)
            self.assertIn("Use strict API validation.", hit_text)
