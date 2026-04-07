"""tests for poor_cli.docker_sandbox module."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from poor_cli.docker_sandbox import (
    is_inside_docker,
    docker_sandbox_enabled,
    docker_sandboxed_command,
    docker_sandbox_status,
)


class TestIsInsideDocker(unittest.TestCase):
    def test_returns_bool(self):
        result = is_inside_docker()
        self.assertIsInstance(result, bool)

    def test_false_on_normal_system(self):
        # /.dockerenv should not exist on host
        if not Path("/.dockerenv").exists():
            self.assertFalse(is_inside_docker())


class TestDockerSandboxEnabled(unittest.TestCase):
    def test_false_without_env_var(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(docker_sandbox_enabled())


class TestDockerSandboxedCommandReadOnly(unittest.TestCase):
    def test_read_only_flags(self):
        argv = docker_sandboxed_command("ls", "read-only", workspace=Path("/tmp/ws"))
        joined = " ".join(argv)
        self.assertIn("--read-only", joined)
        self.assertIn(":ro", joined)
        self.assertIn("--network=none", joined)


class TestDockerSandboxedCommandWorkspaceWrite(unittest.TestCase):
    def test_workspace_write_flags(self):
        ws = Path("/tmp/ws")
        argv = docker_sandboxed_command("echo hi", "workspace-write", workspace=ws)
        joined = " ".join(argv)
        self.assertIn(str(ws.resolve()), joined)
        self.assertIn("--network=none", joined)
        self.assertNotIn("--read-only", joined)


class TestDockerSandboxedCommandFullAccess(unittest.TestCase):
    def test_full_access_no_restrictions(self):
        argv = docker_sandboxed_command("echo hi", "full-access", workspace=Path("/tmp/ws"))
        joined = " ".join(argv)
        self.assertNotIn("--read-only", joined)
        self.assertNotIn("--network=none", joined)


class TestDockerNestedPrevention(unittest.TestCase):
    @patch("poor_cli.docker_sandbox.is_inside_docker", return_value=True)
    def test_nested_docker_returns_plain_sh(self, mock_inside):
        argv = docker_sandboxed_command("ls", "read-only", workspace=Path("/tmp/ws"))
        self.assertEqual(argv, ["sh", "-c", "ls"])


class TestResourceLimits(unittest.TestCase):
    @patch("poor_cli.docker_sandbox.is_inside_docker", return_value=False)
    def test_read_only_has_memory_limit(self, _):
        argv = docker_sandboxed_command("ls", "read-only", workspace=Path("/tmp/ws"))
        self.assertIn("--memory", argv)
        self.assertIn("--cpus", argv)
        self.assertIn("--pids-limit", argv)

    @patch("poor_cli.docker_sandbox.is_inside_docker", return_value=False)
    def test_workspace_write_has_limits(self, _):
        argv = docker_sandboxed_command("echo hi", "workspace-write", workspace=Path("/tmp/ws"))
        self.assertIn("--memory", argv)

    @patch("poor_cli.docker_sandbox.is_inside_docker", return_value=False)
    def test_full_access_has_limits(self, _):
        argv = docker_sandboxed_command("echo hi", "full-access", workspace=Path("/tmp/ws"))
        self.assertIn("--memory", argv)


class TestDockerSandboxStatus(unittest.TestCase):
    def test_status_keys_present(self):
        s = docker_sandbox_status()
        for key in ("enabled", "available", "insideDocker", "image", "memLimit", "cpuLimit", "pidsLimit"):
            self.assertIn(key, s)

    @patch.dict(os.environ, {"POOR_CLI_DOCKER_MEM_LIMIT": "1g"})
    def test_status_reflects_env_vars(self):
        # re-import to pick up env var changes
        import importlib
        import poor_cli.docker_sandbox as ds
        importlib.reload(ds)
        s = ds.docker_sandbox_status()
        self.assertEqual(s["memLimit"], "1g")


if __name__ == "__main__":
    unittest.main()
