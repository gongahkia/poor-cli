"""Tests for path-scoped permission approval."""

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


class TestPathScopedApproval(unittest.TestCase):
    def _make_core(self, path_scoped=True):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = MagicMock()
        core.config.agentic.path_scoped_approval = path_scoped
        core._approved_write_paths = set()
        core._permission_callback = AsyncMock(return_value={"allowed": True, "approvedPaths": [], "approvedChunks": []})
        core._hook_manager = None
        core.tool_registry = MagicMock()
        core.tool_registry.inspect_mutation_targets.return_value = ["/tmp/foo.py"]
        return core

    def test_approved_path_auto_approves(self):
        core = self._make_core()
        core._approved_write_paths.add(str(Path("/tmp/foo.py").resolve()))
        result = asyncio.run(
            core._request_permission("write_file", {"path": "/tmp/foo.py"})
        )
        self.assertTrue(result["allowed"])
        core._permission_callback.assert_not_called()

    def test_unapproved_path_prompts(self):
        core = self._make_core()
        result = asyncio.run(
            core._request_permission("write_file", {"path": "/tmp/foo.py"})
        )
        self.assertTrue(result["allowed"])
        core._permission_callback.assert_called_once()

    def test_approval_recorded_after_grant(self):
        core = self._make_core()
        asyncio.run(
            core._request_permission("write_file", {"path": "/tmp/foo.py"})
        )
        self.assertIn(str(Path("/tmp/foo.py").resolve()), core._approved_write_paths)

    def test_clear_resets(self):
        core = self._make_core()
        core._approved_write_paths.add("/tmp/foo.py")
        core.clear_approved_paths()
        self.assertEqual(len(core._approved_write_paths), 0)

    def test_disabled_skips_cache(self):
        core = self._make_core(path_scoped=False)
        core._approved_write_paths.add(str(Path("/tmp/foo.py").resolve()))
        asyncio.run(
            core._request_permission("write_file", {"path": "/tmp/foo.py"})
        )
        core._permission_callback.assert_called_once()
