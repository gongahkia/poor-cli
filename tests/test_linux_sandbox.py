"""tests for poor_cli.sandbox Linux sandbox functions."""

import unittest
from pathlib import Path
from unittest.mock import patch
from poor_cli.sandbox import (
    _build_firejail_args,
    _build_bwrap_args,
    _linux_sandbox_tool,
    sandboxed_command,
)


class TestBuildFirejailArgs(unittest.TestCase):
    def test_read_only(self):
        args = _build_firejail_args("read-only")
        joined = " ".join(args)
        self.assertIn("--read-only=/", joined)
        self.assertIn("--net=none", joined)

    def test_workspace_write(self):
        ws = Path("/tmp/ws")
        args = _build_firejail_args("workspace-write", workspace=ws)
        joined = " ".join(args)
        self.assertIn(f"--read-write={ws.resolve()}", joined)

    def test_full_access_empty(self):
        args = _build_firejail_args("full-access")
        self.assertEqual(args, [])


class TestBuildBwrapArgs(unittest.TestCase):
    def test_read_only(self):
        args = _build_bwrap_args("read-only")
        self.assertIn("--ro-bind", args)
        self.assertIn("--unshare-net", args)

    def test_workspace_write(self):
        ws = Path("/tmp/ws")
        args = _build_bwrap_args("workspace-write", workspace=ws)
        self.assertIn("--bind", args)
        self.assertIn(str(ws.resolve()), args)

    def test_full_access_empty(self):
        args = _build_bwrap_args("full-access")
        self.assertEqual(args, [])


class TestLinuxSandboxTool(unittest.TestCase):
    def test_returns_none_when_neither_available(self):
        with patch("poor_cli.sandbox.shutil.which", return_value=None):
            self.assertIsNone(_linux_sandbox_tool())


class TestSandboxedCommandLinux(unittest.TestCase):
    def test_linux_with_firejail(self):
        with patch("poor_cli.sandbox.platform.system", return_value="Linux"), \
             patch("poor_cli.sandbox.shutil.which", side_effect=lambda t: "/usr/bin/firejail" if t == "firejail" else None), \
             patch("poor_cli.sandbox.os_sandbox_available", return_value=True):
            argv = sandboxed_command("echo hi", "read-only")
            self.assertIn("firejail", argv[0])
            self.assertIn("bash", argv)


if __name__ == "__main__":
    unittest.main()
