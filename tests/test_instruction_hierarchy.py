"""Tests for hierarchical memory loading and include directives."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.instructions import (
    ALLOW_EXTERNAL_INCLUDES_ENV,
    DISABLE_MEMORY_ENV,
    InstructionManager,
    MANAGED_MEMORY_ENV,
    MAX_MEMORY_CHARACTER_COUNT,
)


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

    def test_disable_memory_loading_via_env(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed-missing.md"
            hidden_memory = repo / ".claude" / "CLAUDE.md"
            hidden_memory.parent.mkdir(parents=True, exist_ok=True)
            hidden_memory.write_text("hidden memory", encoding="utf-8")

            env = self._base_env(home_tmp, managed)
            env[DISABLE_MEMORY_ENV] = "1"
            with patch.dict(os.environ, env):
                snapshot = InstructionManager(repo).build_snapshot()

            rendered = "\n".join(source.content for source in snapshot.sources)
            self.assertNotIn("hidden memory", rendered)

    def test_memory_excludes_from_settings(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed-missing.md"
            memory_file = repo / ".claude" / "CLAUDE.md"
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            memory_file.write_text("excluded memory content", encoding="utf-8")

            settings_path = repo / ".poor-cli" / "settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                '{"claudeMdExcludes":[".claude/CLAUDE.md"]}',
                encoding="utf-8",
            )

            with patch.dict(os.environ, self._base_env(home_tmp, managed)):
                snapshot = InstructionManager(repo).build_snapshot()

            rendered = "\n".join(source.content for source in snapshot.sources)
            self.assertNotIn("excluded memory content", rendered)

    def test_large_memory_file_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed-missing.md"
            memory_file = repo / ".claude" / "CLAUDE.md"
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            oversized = "A" * (MAX_MEMORY_CHARACTER_COUNT + 2500)
            memory_file.write_text(oversized, encoding="utf-8")

            with patch.dict(os.environ, self._base_env(home_tmp, managed)):
                snapshot = InstructionManager(repo).build_snapshot()

            target = next((source for source in snapshot.sources if source.path == ".claude/CLAUDE.md"), None)
            self.assertIsNotNone(target)
            self.assertTrue(bool(target.metadata.get("truncated", False)))
            self.assertIn("memory truncated", target.content)

    def test_external_include_blocked_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            managed = repo / "managed-missing.md"
            external = Path(home_tmp) / "outside.md"
            external.write_text("outside include", encoding="utf-8")

            memory_file = repo / ".claude" / "CLAUDE.md"
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            memory_file.write_text(f"@{external}\nlocal text", encoding="utf-8")

            with patch.dict(os.environ, self._base_env(home_tmp, managed)):
                blocked = InstructionManager(repo).build_snapshot()

            blocked_text = "\n".join(source.content for source in blocked.sources)
            self.assertIn("local text", blocked_text)
            self.assertNotIn("outside include", blocked_text)

            env = self._base_env(home_tmp, managed)
            env[ALLOW_EXTERNAL_INCLUDES_ENV] = "1"
            with patch.dict(os.environ, env):
                allowed = InstructionManager(repo).build_snapshot()
            allowed_text = "\n".join(source.content for source in allowed.sources)
            self.assertIn("outside include", allowed_text)
