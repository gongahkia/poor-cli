"""Tests for file_watcher module."""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from poor_cli.file_watcher import (
    scan_file_for_instructions,
    scan_directory_for_instructions,
    FileWatcher,
    FileEvent,
    COMMENT_PATTERNS,
    DEFAULT_EXTENSIONS,
    SKIP_DIRS,
)


class TestScanFileForInstructions(unittest.TestCase):
    def test_python_comment(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n# poor-cli: add validation\ny = 2\n")
            f.flush()
            result = scan_file_for_instructions(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["instruction"], "add validation")
        self.assertEqual(result[0]["line"], 2)

    def test_js_comment(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write("// poor-cli: refactor this\n")
            f.flush()
            result = scan_file_for_instructions(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["instruction"], "refactor this")

    def test_sql_comment(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("-- poor-cli: add index\n")
            f.flush()
            result = scan_file_for_instructions(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["instruction"], "add index")

    def test_block_comment(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
            f.write("/* poor-cli: fix memory leak */\n")
            f.flush()
            result = scan_file_for_instructions(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["instruction"], "fix memory leak")

    def test_no_instructions_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n# just a comment\n")
            f.flush()
            result = scan_file_for_instructions(f.name)
        os.unlink(f.name)
        self.assertEqual(result, [])

    def test_nonexistent_file_returns_empty(self):
        result = scan_file_for_instructions("/nonexistent/path/file.py")
        self.assertEqual(result, [])


class TestScanDirectory(unittest.TestCase):
    def test_finds_instructions_in_tree(self):
        with tempfile.TemporaryDirectory() as td:
            sub = Path(td) / "src"
            sub.mkdir()
            (sub / "main.py").write_text("# poor-cli: add logging\n")
            result = scan_directory_for_instructions(root=td)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["instruction"], "add logging")

    def test_skips_excluded_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            skip = Path(td) / "node_modules"
            skip.mkdir()
            (skip / "index.js").write_text("// poor-cli: do not find\n")
            result = scan_directory_for_instructions(root=td)
            self.assertEqual(len(result), 0)

    def test_respects_extensions(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "data.txt").write_text("# poor-cli: should skip\n")
            result = scan_directory_for_instructions(root=td)
            self.assertEqual(len(result), 0) # .txt not in DEFAULT_EXTENSIONS


class TestFileWatcher(unittest.TestCase):
    def test_detect_changes_on_mtime_update(self):
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td).resolve() / "test.py"
            fp.write_text("x = 1\n")
            watcher = FileWatcher(root=str(Path(td).resolve()))
            watcher._snapshot_mtimes()
            time.sleep(0.05)
            fp.write_text("x = 2\n# poor-cli: update\n")
            changed = watcher._detect_changes()
            self.assertIn(str(fp), changed)

    def test_no_changes_detected_when_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "test.py"
            fp.write_text("x = 1\n")
            watcher = FileWatcher(root=td)
            watcher._snapshot_mtimes()
            changed = watcher._detect_changes()
            self.assertEqual(changed, [])

    def test_processed_set_prevents_reprocessing(self):
        watcher = FileWatcher()
        key = "test.py:1:do something"
        watcher._processed.add(key)
        self.assertIn(key, watcher._processed)


class TestFileWatcherCallbacks(unittest.TestCase):
    def test_callback_pattern_receives_events(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                fp = Path(td) / "test.py"
                fp.write_text("x = 1\n")
                events = []
                watcher = FileWatcher(root=td, debounce_ms=20)

                def cb(event: FileEvent):
                    events.append(event)
                    watcher.stop()

                watcher.on_change(cb)
                task = asyncio.create_task(watcher.start())
                await asyncio.sleep(0.05)
                fp.write_text("x = 2\n")
                await asyncio.wait_for(task, timeout=1)
                self.assertEqual(events[0].path, str(fp.resolve()))

        asyncio.run(run())

    def test_async_generator_pattern_receives_events(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                fp = Path(td) / "test.py"
                fp.write_text("x = 1\n")
                watcher = FileWatcher(root=td, debounce_ms=20)

                async def collect():
                    async for event in watcher:
                        watcher.stop()
                        return event
                    return None

                task = asyncio.create_task(collect())
                await asyncio.sleep(0.05)
                fp.write_text("x = 2\n")
                event = await asyncio.wait_for(task, timeout=1)
                self.assertIsNotNone(event)
                self.assertEqual(event.path, str(fp.resolve()))

        asyncio.run(run())

    def test_gitignore_respected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".gitignore").write_text("ignored.py\nignored_dir/\n")
            ignored = root / "ignored.py"
            watched = root / "watched.py"
            ignored_dir = root / "ignored_dir"
            ignored_dir.mkdir()
            ignored_nested = ignored_dir / "nested.py"
            ignored.write_text("x = 1\n")
            watched.write_text("x = 1\n")
            ignored_nested.write_text("x = 1\n")
            watcher = FileWatcher(root=td)
            watcher._snapshot_mtimes()
            time.sleep(0.05)
            ignored.write_text("x = 2\n")
            watched.write_text("x = 2\n")
            ignored_nested.write_text("x = 2\n")
            self.assertEqual(watcher._detect_changes(), [str(watched.resolve())])

    def test_stop_is_idempotent(self):
        watcher = FileWatcher()
        watcher.stop()
        watcher.stop()
        self.assertFalse(watcher._running)

    def test_debounce_coalesces_rapid_changes(self):
        async def run():
            with tempfile.TemporaryDirectory() as td:
                fp = Path(td) / "test.py"
                fp.write_text("x = 1\n")
                events = []
                watcher = FileWatcher(root=td, debounce_ms=50)

                def cb(event: FileEvent):
                    events.append(event)
                    watcher.stop()

                watcher.on_change(cb)
                task = asyncio.create_task(watcher.start())
                await asyncio.sleep(0.02)
                fp.write_text("x = 2\n")
                fp.write_text("x = 3\n")
                await asyncio.wait_for(task, timeout=1)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].paths, (str(fp.resolve()),))

        asyncio.run(run())

    def test_on_execute_stored(self):
        cb = AsyncMock()
        watcher = FileWatcher(on_execute=cb)
        self.assertIs(watcher._on_execute, cb)

    def test_on_instruction_stored(self):
        cb = AsyncMock()
        watcher = FileWatcher(on_instruction=cb)
        self.assertIs(watcher._on_instruction, cb)


class TestConstants(unittest.TestCase):
    def test_comment_patterns_count(self):
        self.assertEqual(len(COMMENT_PATTERNS), 4)

    def test_default_extensions_include_common(self):
        for ext in (".py", ".js", ".ts", ".rs", ".go"):
            self.assertIn(ext, DEFAULT_EXTENSIONS)

    def test_skip_dirs_include_git(self):
        self.assertIn(".git", SKIP_DIRS)
        self.assertIn("node_modules", SKIP_DIRS)
