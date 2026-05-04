"""Tests for policy_hooks module."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from poor_cli.policy_hooks import (
    HookDefinition, HookExecutionResult, PolicyHookManager,
    HOOK_EVENTS, HOOK_PAYLOAD_SCHEMAS, SUPPORTED_SCHEMA_VERSIONS,
)


class TestHookDefinition(unittest.TestCase):
    def test_default_priority_is_100(self):
        h = HookDefinition(event="pre_tool_use", command="echo")
        self.assertEqual(h.priority, 100)

    def test_to_dict_includes_priority(self):
        h = HookDefinition(event="pre_tool_use", command="echo", priority=50)
        d = h.to_dict()
        self.assertEqual(d["priority"], 50)
        self.assertIn("priority", d)

    def test_to_dict_all_keys(self):
        h = HookDefinition(event="session_start", command="true")
        d = h.to_dict()
        for key in ("event", "command", "args", "cwd", "timeoutSec", "env", "name", "sourcePath", "schemaVersion", "priority"):
            self.assertIn(key, d)


class TestHookExecutionResult(unittest.TestCase):
    def test_blocked_only_on_pre_tool_use_nonzero(self):
        hook = HookDefinition(event="pre_tool_use", command="false")
        r = HookExecutionResult(hook=hook, return_code=1, stdout="", stderr="denied", duration_ms=10)
        self.assertTrue(r.blocked)

    def test_not_blocked_on_zero_exit(self):
        hook = HookDefinition(event="pre_tool_use", command="true")
        r = HookExecutionResult(hook=hook, return_code=0, stdout="", stderr="", duration_ms=5)
        self.assertFalse(r.blocked)

    def test_not_blocked_on_other_events(self):
        hook = HookDefinition(event="post_tool_use", command="false")
        r = HookExecutionResult(hook=hook, return_code=1, stdout="", stderr="", duration_ms=5)
        self.assertFalse(r.blocked)

    def test_to_dict_round_trip(self):
        hook = HookDefinition(event="pre_tool_use", command="test", priority=10)
        r = HookExecutionResult(hook=hook, return_code=0, stdout="ok", stderr="", duration_ms=42)
        d = r.to_dict()
        self.assertEqual(d["returnCode"], 0)
        self.assertEqual(d["durationMs"], 42)
        self.assertFalse(d["blocked"])
        self.assertEqual(d["hook"]["priority"], 10)


class TestHookEvents(unittest.TestCase):
    def test_session_end_in_events(self):
        self.assertIn("session_end", HOOK_EVENTS)

    def test_all_expected_events_present(self):
        expected = {
            "session_start", "user_prompt_submitted", "permission_decision",
            "pre_tool_use", "post_tool_use", "tool_failure",
            "task_started", "task_finished", "automation_started",
            "automation_finished", "checkpoint_restored",
            "session_end", "notification", "subagent_stop",
            "subagent_start", "pre_compact", "post_compact",
            "pre_prune", "post_prune", "pre_checkpoint",
            "post_checkpoint", "pre_edit", "post_edit",
            "pre_provider_call", "post_provider_call", "budget_breach",
        }
        self.assertEqual(expected, set(HOOK_EVENTS))

    def test_event_count(self):
        self.assertEqual(len(HOOK_EVENTS), 26)

    def test_new_events_document_payload_shape(self):
        for event in HOOK_EVENTS[12:]:
            self.assertIn(event, HOOK_PAYLOAD_SCHEMAS)


class TestPolicyHookManager(unittest.TestCase):
    def test_reload_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            mgr = PolicyHookManager(repo_root=Path(td))
            self.assertEqual(mgr.status()["totalHooks"], 0)

    def test_reload_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            hook = {"hooks": {"pre_tool_use": [{"command": "echo ok", "priority": 10}]}}
            (hooks_dir / "test.json").write_text(json.dumps(hook))
            mgr = PolicyHookManager(repo_root=Path(td))
            self.assertEqual(mgr.status()["totalHooks"], 1)

    def test_reload_invalid_json_records_error(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            (hooks_dir / "bad.json").write_text("not json{{{")
            mgr = PolicyHookManager(repo_root=Path(td))
            self.assertTrue(len(mgr.status()["validationErrors"]) > 0)

    def test_status_returns_complete_dict(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = PolicyHookManager(repo_root=Path(td))
            s = mgr.status()
            for key in ("hooksDir", "totalHooks", "supportedSchemaVersions", "validationErrors", "events"):
                self.assertIn(key, s)


class TestHookOrdering(unittest.TestCase):
    def test_hooks_sorted_by_priority(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            hook = {"hooks": {"pre_tool_use": [
                {"command": "echo low", "priority": 200, "name": "low"},
                {"command": "echo high", "priority": 10, "name": "high"},
                {"command": "echo mid", "priority": 50, "name": "mid"},
            ]}}
            (hooks_dir / "ordered.json").write_text(json.dumps(hook))
            mgr = PolicyHookManager(repo_root=Path(td))
            hooks = sorted(mgr._hooks_by_event.get("pre_tool_use", []), key=lambda h: h.priority)
            names = [h.name for h in hooks]
            self.assertEqual(names, ["high", "mid", "low"])

    def test_equal_priority_preserves_order(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            hook = {"hooks": {"post_tool_use": [
                {"command": "echo a", "name": "a", "priority": 100},
                {"command": "echo b", "name": "b", "priority": 100},
            ]}}
            (hooks_dir / "equal.json").write_text(json.dumps(hook))
            mgr = PolicyHookManager(repo_root=Path(td))
            hooks = sorted(mgr._hooks_by_event.get("post_tool_use", []), key=lambda h: h.priority)
            names = [h.name for h in hooks]
            self.assertEqual(names, ["a", "b"])


class TestHookRun(unittest.TestCase):
    def test_run_returns_empty_for_no_hooks(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = PolicyHookManager(repo_root=Path(td))
            results = asyncio.run(mgr.run("session_start", {}))
            self.assertEqual(results, [])

    def test_run_passes_payload_on_stdin(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            hook = {"hooks": {"session_start": [{"command": "cat"}]}}
            (hooks_dir / "cat.json").write_text(json.dumps(hook))
            mgr = PolicyHookManager(repo_root=Path(td))
            payload = {"test": True}
            results = asyncio.run(mgr.run("session_start", payload))
            self.assertEqual(len(results), 1)
            self.assertIn('"test"', results[0].stdout)
            self.assertIn('"event": "session_start"', results[0].stdout)

    def test_new_events_load_and_receive_payload(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            hook = {
                "hooks": {
                    event: [{"command": "cat"}]
                    for event in HOOK_EVENTS[12:]
                }
            }
            (hooks_dir / "new-events.json").write_text(json.dumps(hook))
            mgr = PolicyHookManager(repo_root=Path(td))
            self.assertEqual(mgr.status()["totalHooks"], len(HOOK_EVENTS[12:]))
            for event in HOOK_EVENTS[12:]:
                results = asyncio.run(mgr.run(event, {"sessionId": "s1"}))
                self.assertEqual(len(results), 1)
                self.assertIn(f'"event": "{event}"', results[0].stdout)
                self.assertIn('"sessionId": "s1"', results[0].stdout)

    def test_blocked_hook_stops_chain(self):
        with tempfile.TemporaryDirectory() as td:
            hooks_dir = Path(td) / ".poor-cli" / "hooks"
            hooks_dir.mkdir(parents=True)
            hook = {"hooks": {"pre_tool_use": [
                {"command": "false", "name": "blocker"},
                {"command": "echo should-not-run", "name": "after"},
            ]}}
            (hooks_dir / "block.json").write_text(json.dumps(hook))
            mgr = PolicyHookManager(repo_root=Path(td))
            results = asyncio.run(mgr.run("pre_tool_use", {}))
            self.assertEqual(len(results), 1) # second hook never ran
            self.assertTrue(results[0].blocked)
