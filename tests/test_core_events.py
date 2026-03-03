"""
Tests for CoreEvent emission, auto-permission, and diff computation.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass


class TestCoreEvent:
    """Test CoreEvent factory methods."""

    def test_text_chunk(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.text_chunk("hello", "req-1")
        assert ev.type == "text_chunk"
        assert ev.data["chunk"] == "hello"
        assert ev.data["requestId"] == "req-1"

    def test_tool_call_start(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.tool_call_start("read_file", {"path": "x.py"}, "c1", 2, 10)
        assert ev.type == "tool_call_start"
        assert ev.data["toolName"] == "read_file"
        assert ev.data["toolArgs"] == {"path": "x.py"}
        assert ev.data["iterationIndex"] == 2
        assert ev.data["iterationCap"] == 10

    def test_tool_result(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.tool_result("edit_file", "ok", "c1", 1, 25, diff="@@ -1 +1 @@")
        assert ev.type == "tool_result"
        assert ev.data["toolResult"] == "ok"
        assert ev.data["diff"] == "@@ -1 +1 @@"

    def test_tool_result_no_diff(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.tool_result("read_file", "content", "c1")
        assert ev.data["diff"] == ""

    def test_permission_request(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.permission_request("bash", {"cmd": "ls"}, "p1")
        assert ev.type == "permission_request"
        assert ev.data["toolName"] == "bash"
        assert ev.data["promptId"] == "p1"

    def test_cost_update(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.cost_update(100, 50, 0.05)
        assert ev.type == "cost_update"
        assert ev.data["inputTokens"] == 100
        assert ev.data["outputTokens"] == 50
        assert ev.data["estimatedCost"] == 0.05

    def test_progress(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.progress("thinking", "analyzing code", 3, 25)
        assert ev.type == "progress"
        assert ev.data["phase"] == "thinking"
        assert ev.data["iterationIndex"] == 3

    def test_done(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.done("iteration_cap")
        assert ev.type == "done"
        assert ev.data["reason"] == "iteration_cap"

    def test_done_default_reason(self):
        from poor_cli.core import CoreEvent
        ev = CoreEvent.done()
        assert ev.data["reason"] == "complete"


class TestAutoPermission:
    """Test _check_auto_permission logic."""

    @pytest.fixture
    def core_with_config(self):
        from poor_cli.core import PoorCLICore
        core = PoorCLICore()
        config = MagicMock()
        config.agentic.auto_approve_tools = ["read_file", "glob_files"]
        config.agentic.deny_patterns = ["rm -rf", "sudo"]
        core.config = config
        return core

    def test_auto_approve(self, core_with_config):
        result = core_with_config._check_auto_permission("read_file", {"path": "x.py"})
        assert result is True

    def test_auto_deny_rm_rf(self, core_with_config):
        result = core_with_config._check_auto_permission("bash", {"cmd": "rm -rf /"})
        assert result is False

    def test_auto_deny_sudo(self, core_with_config):
        result = core_with_config._check_auto_permission("bash", {"cmd": "sudo apt install"})
        assert result is False

    def test_interactive_needed(self, core_with_config):
        result = core_with_config._check_auto_permission("write_file", {"path": "x.py"})
        assert result is None

    def test_no_config(self):
        from poor_cli.core import PoorCLICore
        core = PoorCLICore()
        core.config = None
        result = core._check_auto_permission("anything", {})
        assert result is None


class TestComputeEditDiff:
    """Test _compute_edit_diff."""

    @pytest.fixture
    def core(self):
        from poor_cli.core import PoorCLICore
        return PoorCLICore()

    def test_edit_file_diff(self, core):
        diff = core._compute_edit_diff("edit_file", {
            "file_path": "test.py",
            "old_text": "foo\nbar\n",
            "new_text": "foo\nbaz\n",
        })
        assert "---" in diff
        assert "+++" in diff
        assert "-bar" in diff
        assert "+baz" in diff

    def test_non_edit_tool_returns_empty(self, core):
        diff = core._compute_edit_diff("read_file", {"path": "x.py"})
        assert diff == ""

    def test_empty_texts_returns_empty(self, core):
        diff = core._compute_edit_diff("edit_file", {"file_path": "x.py"})
        assert diff == ""

    def test_diff_contains_file_path(self, core):
        diff = core._compute_edit_diff("edit_file", {
            "file_path": "src/main.py",
            "old_text": "a\n",
            "new_text": "b\n",
        })
        assert "a/src/main.py" in diff
        assert "b/src/main.py" in diff
