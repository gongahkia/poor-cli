"""Tests for async-only permission callback contract (PRD 002)."""

import asyncio
import unittest
from unittest.mock import MagicMock

from poor_cli.permission_engine import (
    PermissionCallback,
    _as_async,
)


def _make_core(callback=None):
    from poor_cli.core import PoorCLICore
    core = object.__new__(PoorCLICore)
    core.config = MagicMock()
    core.config.agentic.path_scoped_approval = False
    core._approved_write_paths = set()
    core._permission_callback = None
    core._hook_manager = None
    core.tool_registry = None
    if callback is not None:
        core.permission_callback = callback
    return core


class TestPermissionCallbackAsync(unittest.TestCase):
    def test_async_callback_awaited(self):
        calls = []

        async def cb(tool, args, preview=None):
            calls.append((tool, args, preview))
            return {"allowed": True, "approvedPaths": [], "approvedChunks": []}

        core = _make_core(cb)
        result = asyncio.run(core._request_permission("write_file", {"path": "/tmp/x"}))
        self.assertTrue(result["allowed"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "write_file")

    def test_sync_callback_wrapped_via_as_async(self):
        calls = []

        def sync_cb(tool, args, preview=None):
            calls.append((tool, args, preview))
            return {"allowed": True}

        wrapped = _as_async(sync_cb)
        core = _make_core(wrapped)
        result = asyncio.run(core._request_permission("write_file", {"path": "/tmp/x"}))
        self.assertTrue(result["allowed"])
        self.assertEqual(len(calls), 1)

    def test_raw_sync_callback_rejected_at_registration(self):
        def sync_cb(tool, args, preview=None):
            return {"allowed": True}

        core = _make_core()
        with self.assertRaises(TypeError):
            core.permission_callback = sync_cb

    def test_unrelated_typeerror_propagates(self):
        async def bad_cb(tool, args, preview=None):
            val = None
            return val["missing"]

        core = _make_core(bad_cb)
        with self.assertRaises(TypeError):
            asyncio.run(core._request_permission("write_file", {"path": "/tmp/x"}))

    def test_permission_decision_shape_unchanged(self):
        async def cb(tool, args, preview=None):
            return {"allowed": True, "approvedPaths": ["/tmp/x"], "approvedChunks": []}

        core = _make_core(cb)
        result = asyncio.run(core._request_permission("write_file", {"path": "/tmp/x"}))
        self.assertEqual(set(result.keys()), {"allowed", "approvedPaths", "approvedChunks"})
        self.assertTrue(result["allowed"])
        self.assertEqual(result["approvedPaths"], ["/tmp/x"])
        self.assertEqual(result["approvedChunks"], [])

    def test_as_async_passes_through_async_callback(self):
        async def cb(tool, args, preview=None):
            return {"allowed": True}

        self.assertIs(_as_async(cb), cb)

    def test_as_async_wraps_two_arg_sync_callback(self):
        def legacy(tool, args):
            return {"allowed": True, "got_args": args}

        wrapped = _as_async(legacy)
        result = asyncio.run(wrapped("t", {"a": 1}, {"paths": ["/x"]}))
        self.assertTrue(result["allowed"])
        self.assertEqual(result["got_args"], {"a": 1})

    def test_permission_callback_type_alias_exists(self):
        self.assertIsNotNone(PermissionCallback)


if __name__ == "__main__":
    unittest.main()
