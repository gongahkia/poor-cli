from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.agent_rules import load_rules, merge
from poor_cli.file_watcher import FileEvent, FileWatcher
from poor_cli.instructions import InstructionManager, MANAGED_MEMORY_ENV
from poor_cli.memory import MemoryEntry, MemoryManager


class TestAgentRulesLoader(unittest.TestCase):
    def _env(self, home: str, managed: Path) -> dict[str, str]:
        return {**os.environ, "HOME": home, MANAGED_MEMORY_ENV: str(managed)}

    def test_agents_md_hierarchy_closest_wins(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            nested = repo / "apps" / "api"
            nested.mkdir(parents=True)
            (repo / "AGENTS.md").write_text("root rule", encoding="utf-8")
            (nested / "AGENTS.md").write_text("nested rule", encoding="utf-8")

            with patch.dict(os.environ, self._env(home_tmp, repo / "managed-missing.md")):
                sources = load_rules(nested, repo_root=repo)
                snapshot = InstructionManager(repo).build_snapshot(referenced_files=["apps/api/main.py"])

            self.assertEqual(
                [source.path for source in sources],
                [(nested / "AGENTS.md").resolve(), (repo / "AGENTS.md").resolve()],
            )
            rendered = "\n".join(source.content for source in snapshot.sources if source.kind == "agents_md")
            self.assertLess(rendered.index("nested rule"), rendered.index("root rule"))

    def test_claude_md_read_when_agents_md_absent(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            (repo / "CLAUDE.md").write_text("legacy rule", encoding="utf-8")

            with patch.dict(os.environ, self._env(home_tmp, repo / "managed-missing.md")):
                sources = load_rules(repo, repo_root=repo)
                snapshot = InstructionManager(repo).build_snapshot()

            self.assertEqual([source.kind for source in sources], ["claude_md"])
            self.assertIn("legacy rule", snapshot.render_prompt_prefix())

    def test_claude_md_deduped_when_agents_md_same_directory(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            (repo / "AGENTS.md").write_text("canonical rule", encoding="utf-8")
            (repo / "CLAUDE.md").write_text("legacy rule", encoding="utf-8")

            with patch.dict(os.environ, self._env(home_tmp, repo / "managed-missing.md")):
                sources = load_rules(repo, repo_root=repo)

            self.assertEqual([source.kind for source in sources], ["agents_md"])
            self.assertEqual(merge(sources), "canonical rule")

    def test_frontmatter_apply_to_globs_respected(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            (repo / "AGENTS.md").write_text(
                "---\napply_to:\n  - \"src/**\"\n  - \"!src/generated/**\"\n---\nPython rule",
                encoding="utf-8",
            )

            with patch.dict(os.environ, self._env(home_tmp, repo / "managed-missing.md")):
                hit = load_rules(repo, repo_root=repo, referenced_files=["src/app.py"])
                miss = load_rules(repo, repo_root=repo, referenced_files=["tests/test_app.py"])
                negated = load_rules(repo, repo_root=repo, referenced_files=["src/generated/app.py"])

            self.assertEqual([source.content for source in hit], ["Python rule"])
            self.assertEqual(miss, [])
            self.assertEqual(negated, [])

    def test_memory_write_prefers_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            agents = repo / "AGENTS.md"
            agents.write_text("# rules\n", encoding="utf-8")
            mgr = MemoryManager(
                Path(home_tmp) / ".poor-cli",
                repo_root=repo,
                prefer_agent_rules=True,
            )
            entry = MemoryEntry(name="Build note", type="project", description="compile", content="Run make test.")

            mgr.save(entry)

            text = agents.read_text(encoding="utf-8")
            self.assertIn("## Memory: Build note", text)
            self.assertIn("Run make test.", text)
            self.assertFalse((Path(home_tmp) / ".poor-cli" / "memory" / entry.filename).exists())

    def test_agents_md_watcher_invalidates_instruction_cache(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
                repo = Path(repo_tmp)
                agents = repo / "AGENTS.md"
                agents.write_text("first rule", encoding="utf-8")
                with patch.dict(os.environ, self._env(home_tmp, repo / "managed-missing.md")):
                    mgr = InstructionManager(repo)
                    snap1 = mgr.build_snapshot()
                    watcher = FileWatcher(root=repo)

                    mgr.attach_rule_watcher(watcher)
                    watcher._snapshot_mtimes()
                    time.sleep(0.05)
                    agents.write_text("second rule", encoding="utf-8")
                    changed = watcher._detect_changes()
                    await watcher._events.put(FileEvent(tuple(changed)))
                    await watcher._dispatch_pending_events()
                    snap2 = mgr.build_snapshot()

                self.assertIsNot(snap1, snap2)
                self.assertIn("second rule", snap2.render_prompt_prefix())

        asyncio.run(run())
