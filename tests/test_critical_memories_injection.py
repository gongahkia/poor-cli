"""Tests for MH5 critical-memories injection into the instruction stack."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.instructions import InstructionManager, MANAGED_MEMORY_ENV
from poor_cli.memory import MemoryEntry, MemoryManager


class CriticalMemoryInjectionTests(unittest.TestCase):
    def _env(self, home: str, managed: Path) -> dict:
        return {**os.environ, "HOME": home, MANAGED_MEMORY_ENV: str(managed)}

    def test_short_feedback_memory_injected_into_prefix(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            repo_path = Path(repo)
            mgr = MemoryManager(Path(home) / ".poor-cli")
            mgr.save(MemoryEntry(name="go style", description="prefer Go", type="feedback", content="Use Go for backend services."))
            with patch.dict(os.environ, self._env(home, repo_path / "managed-missing.md")):
                snap = InstructionManager(repo_path).build_snapshot()
            text = snap.render_prompt_prefix()
            self.assertIn("Critical Memories", text)
            self.assertIn("go style", text)
            self.assertIn("Use Go", text)

    def test_long_memory_not_injected(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            repo_path = Path(repo)
            mgr = MemoryManager(Path(home) / ".poor-cli")
            long_content = "\n".join(f"line {i}" for i in range(50))
            mgr.save(MemoryEntry(name="long doc", description="big", type="feedback", content=long_content))
            with patch.dict(os.environ, self._env(home, repo_path / "managed-missing.md")):
                snap = InstructionManager(repo_path).build_snapshot()
            text = snap.render_prompt_prefix()
            self.assertNotIn("long doc", text)

    def test_project_type_not_injected_into_prefix(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            repo_path = Path(repo)
            mgr = MemoryManager(Path(home) / ".poor-cli")
            mgr.save(MemoryEntry(name="project note", description="x", type="project", content="short fact"))
            with patch.dict(os.environ, self._env(home, repo_path / "managed-missing.md")):
                snap = InstructionManager(repo_path).build_snapshot()
            text = snap.render_prompt_prefix()
            self.assertNotIn("project note", text)

    def test_no_memories_no_section(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            repo_path = Path(repo)
            with patch.dict(os.environ, self._env(home, repo_path / "managed-missing.md")):
                snap = InstructionManager(repo_path).build_snapshot()
            text = snap.render_prompt_prefix()
            self.assertNotIn("Critical Memories", text)


if __name__ == "__main__":
    unittest.main()
