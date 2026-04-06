"""Tests for permission rule evaluation."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.permission_rules import PermissionRuleEngine


class TestPermissionRuleEngine(unittest.TestCase):
    def _env(self, home: str) -> dict[str, str]:
        return {**os.environ, "HOME": home}

    def test_compound_bash_prefers_deny(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            engine = PermissionRuleEngine(Path(repo_tmp))
            engine.add_session_rule("bash", "allow", "git *")
            engine.add_session_rule("bash", "deny", "rm *")
            match = engine.evaluate("bash", {"command": "git status && rm -rf /tmp/x"})
            self.assertIsNotNone(match)
            self.assertEqual(match.behavior, "deny")

    def test_partial_allow_becomes_ask(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            engine = PermissionRuleEngine(Path(repo_tmp))
            engine.add_session_rule("bash", "allow", "git *")
            match = engine.evaluate("bash", {"command": "git status && echo hi"})
            self.assertIsNotNone(match)
            self.assertEqual(match.behavior, "ask")

    def test_persistent_rule_roundtrip_local_scope(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as home_tmp:
            repo = Path(repo_tmp)
            with patch.dict(os.environ, self._env(home_tmp)):
                engine = PermissionRuleEngine(repo)
                engine.add_persistent_rule(
                    scope="local",
                    tool_name="bash",
                    behavior="allow",
                    rule_content="git *",
                )
                rules = engine.list_rules()
            self.assertEqual(len(rules["local"]), 1)
            self.assertEqual(rules["local"][0]["toolName"], "bash")
            self.assertEqual(rules["local"][0]["behavior"], "allow")
            self.assertEqual(rules["local"][0]["ruleContent"], "git *")

    def test_non_bash_rule_matches_tool_payload(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            engine = PermissionRuleEngine(Path(repo_tmp))
            engine.add_session_rule("write_file", "deny", "*secret*")
            match = engine.evaluate("write_file", {"file_path": "/tmp/secret.txt"})
            self.assertIsNotNone(match)
            self.assertEqual(match.behavior, "deny")

    def test_blanket_denied_tools_returns_first_blanket_rule(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            engine = PermissionRuleEngine(Path(repo_tmp))
            engine.add_session_rule("bash", "allow", "*")
            engine.add_session_rule("bash", "deny", "*")
            engine.add_session_rule("read_file", "deny", "")
            hidden = engine.blanket_denied_tools()
            self.assertIn("bash", hidden)
            self.assertIn("read_file", hidden)

    def test_blanket_denied_tools_ignores_scoped_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmp:
            engine = PermissionRuleEngine(Path(repo_tmp))
            engine.add_session_rule("write_file", "deny", "*secret*")
            hidden = engine.blanket_denied_tools()
            self.assertNotIn("write_file", hidden)
