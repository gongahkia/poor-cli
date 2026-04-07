"""tests for poor_cli.tools_async.ToolRegistryAsync._maybe_auto_commit."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from poor_cli.tools_async import ToolRegistryAsync


def _make_registry(auto_commit=True):
    """Build a minimal ToolRegistryAsync with stubbed config."""
    reg = ToolRegistryAsync.__new__(ToolRegistryAsync)
    reg.config = SimpleNamespace(agentic=SimpleNamespace(auto_commit=auto_commit))
    return reg


class TestMaybeAutoCommit(unittest.TestCase):
    @patch("subprocess.run")
    def test_calls_git_add_and_commit(self, mock_run):
        def side_effect(cmd, **kwargs):
            m = MagicMock()
            if "check-ignore" in cmd:
                m.returncode = 1 # not ignored
            else:
                m.returncode = 0
            return m
        mock_run.side_effect = side_effect
        reg = _make_registry(auto_commit=True)
        reg._maybe_auto_commit("/tmp/foo.py", "write_file")
        cmds = [c[0][0] for c in mock_run.call_args_list]
        self.assertTrue(any("rev-parse" in str(c) for c in cmds))
        self.assertTrue(any("add" in str(c) for c in cmds))

    @patch("subprocess.run")
    def test_skipped_when_disabled(self, mock_run):
        reg = _make_registry(auto_commit=False)
        reg._maybe_auto_commit("/tmp/foo.py", "write_file")
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_skipped_when_not_in_git_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128)
        reg = _make_registry(auto_commit=True)
        reg._maybe_auto_commit("/tmp/foo.py", "write_file")
        self.assertEqual(mock_run.call_count, 1) # only rev-parse

    @patch("subprocess.run")
    def test_skipped_for_gitignored_files(self, mock_run):
        def side_effect(cmd, **kwargs):
            m = MagicMock()
            if "rev-parse" in cmd:
                m.returncode = 0
            elif "check-ignore" in cmd:
                m.returncode = 0 # file is ignored
            else:
                m.returncode = 0
            return m
        mock_run.side_effect = side_effect
        reg = _make_registry(auto_commit=True)
        reg._maybe_auto_commit("/tmp/foo.py", "write_file")
        self.assertEqual(mock_run.call_count, 2) # rev-parse + check-ignore


if __name__ == "__main__":
    unittest.main()
