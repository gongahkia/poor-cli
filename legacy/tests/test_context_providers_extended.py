"""Extended tests for @-mention context providers."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
from pathlib import Path

from poor_cli.context_providers import resolve_mentions, _MENTION_RE, _PROVIDERS, _TOKEN_MENTION_RE


class TestMentionRegex(unittest.TestCase):
    def test_single_diff(self):
        matches = _MENTION_RE.findall("show me @diff")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "diff")

    def test_codebase_with_query(self):
        matches = _MENTION_RE.findall("@codebase authentication handler")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "codebase")
        self.assertIn("authentication handler", matches[0][1])

    def test_web_with_query(self):
        matches = _MENTION_RE.findall("@web python asyncio tutorial")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "web")

    def test_terminal_mention(self):
        matches = _MENTION_RE.findall("check @terminal output")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "terminal")

    def test_docs_mention(self):
        matches = _MENTION_RE.findall("@docs setup guide")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], "docs")

    def test_multiple_mentions(self):
        matches = _MENTION_RE.findall("@diff and @codebase search")
        self.assertEqual(len(matches), 2)

    def test_no_mentions(self):
        matches = _MENTION_RE.findall("plain text no mentions")
        self.assertEqual(len(matches), 0)

    def test_file_path_not_captured(self):
        matches = _MENTION_RE.findall("@src/main.py")
        # file paths should NOT match typed providers
        provider_names = {m[0] for m in matches}
        self.assertNotIn("src/main.py", provider_names)

    def test_case_insensitive(self):
        matches = _MENTION_RE.findall("@DIFF please")
        self.assertEqual(len(matches), 1)


class TestProviderRegistry(unittest.TestCase):
    def test_six_providers_registered(self):
        self.assertEqual(len(_PROVIDERS), 6)

    def test_expected_providers(self):
        expected = {"codebase", "diff", "terminal", "docs", "web", "symbol"}
        self.assertEqual(set(_PROVIDERS.keys()), expected)

    def test_all_providers_callable(self):
        import inspect
        for name, fn in _PROVIDERS.items():
            self.assertTrue(inspect.iscoroutinefunction(fn), f"{name} should be async")


class TestResolveMentions(unittest.TestCase):
    def test_no_mentions_passthrough(self):
        core = MagicMock()
        cleaned, blocks = asyncio.run(resolve_mentions("hello world", core))
        self.assertEqual(cleaned, "hello world")
        self.assertEqual(blocks, [])

    def test_diff_resolved(self):
        core = MagicMock()
        with patch("poor_cli.context_providers.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="diff output here")
            cleaned, blocks = asyncio.run(resolve_mentions("show @diff", core))
        self.assertTrue(len(blocks) > 0)

    def test_mention_stripped_from_message(self):
        core = MagicMock()
        with patch("poor_cli.context_providers.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="")
            cleaned, blocks = asyncio.run(resolve_mentions("show @diff please", core))
        self.assertNotIn("@diff", cleaned)

    def test_docs_searches_md_files(self):
        core = MagicMock()
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "README.md").write_text("Installation guide for the project")
            import os
            old_cwd = os.getcwd()
            os.chdir(d)
            try:
                cleaned, blocks = asyncio.run(resolve_mentions("@docs installation", core))
                self.assertTrue(any("installation" in b.lower() or "Installation" in b for b in blocks) or len(blocks) > 0)
            finally:
                os.chdir(old_cwd)

    def test_terminal_no_output(self):
        core = MagicMock(spec=[])
        cleaned, blocks = asyncio.run(resolve_mentions("@terminal", core))
        self.assertTrue(any("no recent" in b.lower() for b in blocks))

    def test_web_no_registry(self):
        core = MagicMock()
        core.tool_registry = None
        cleaned, blocks = asyncio.run(resolve_mentions("@web python tutorial", core))
        self.assertTrue(len(blocks) > 0)

    def test_file_token_resolved(self):
        core = MagicMock()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            core._repo_root = root
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('a')\nprint('b')\n", encoding="utf-8")
            cleaned, blocks = asyncio.run(resolve_mentions("read @file:src/main.py:2", core))
        self.assertEqual(cleaned, "read")
        self.assertEqual(len(blocks), 1)
        self.assertIn("[file: src/main.py:2]", blocks[0])
        self.assertIn("print('b')", blocks[0])
        self.assertNotIn("print('a')", blocks[0])

    def test_buffer_token_resolved(self):
        core = MagicMock()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            core._repo_root = root
            (root / "README.md").write_text("# hi\n", encoding="utf-8")
            cleaned, blocks = asyncio.run(resolve_mentions("inspect @buffer:README.md", core))
        self.assertEqual(cleaned, "inspect")
        self.assertIn("[buffer: README.md]", blocks[0])
        self.assertIn("# hi", blocks[0])

    def test_lsp_token_resolved(self):
        core = MagicMock()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            core._repo_root = root
            (root / "bad.lua").write_text("local a\nlocal b\n", encoding="utf-8")
            cleaned, blocks = asyncio.run(resolve_mentions("fix @lsp:bad.lua:2", core))
        self.assertEqual(cleaned, "fix")
        self.assertIn("[lsp: bad.lua:2]", blocks[0])
        self.assertIn("local b", blocks[0])
        self.assertNotIn("local a", blocks[0])

    def test_token_rejects_outside_workspace(self):
        core = MagicMock()
        with tempfile.TemporaryDirectory() as d:
            core._repo_root = Path(d).resolve()
            cleaned, blocks = asyncio.run(resolve_mentions("read @file:../secret.txt", core))
        self.assertEqual(cleaned, "read")
        self.assertIn("path outside workspace", blocks[0])

    def test_token_regex_accepts_sources(self):
        self.assertEqual(_TOKEN_MENTION_RE.findall("@file:a.py @buffer:b.lua @lsp:c.ts:3"), [
            ("file", "a.py"),
            ("buffer", "b.lua"),
            ("lsp", "c.ts:3"),
        ])


if __name__ == "__main__":
    unittest.main()
