"""Proposal F.3 tests: auto-checkpoint + optional rollback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import ToolResult
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tools import _registry


def _run(coro):
    return asyncio.run(coro)


class _FakeCheckpoint:
    def __init__(self, checkpoint_id: str) -> None:
        self.checkpoint_id = checkpoint_id


class _FakeCheckpointManager:
    def __init__(self) -> None:
        self.created = []
        self.restored = []
        self._next = 0

    def create_checkpoint(self, file_paths, description, operation_type="manual"):
        self._next += 1
        checkpoint_id = f"cp_{self._next}"
        self.created.append((list(file_paths), description, operation_type, checkpoint_id))
        return _FakeCheckpoint(checkpoint_id)

    def restore_checkpoint(self, checkpoint_id):
        self.restored.append(checkpoint_id)
        return 1


def _ctx(cwd: Path, manager: _FakeCheckpointManager, *, config=None):
    payload = {
        "cwd": str(cwd),
        "has_plugin": lambda _n: False,
        "notify_client": lambda *a, **k: None,
        "checkpoint_manager": manager,
    }
    if config is not None:
        payload["config"] = config
    return SimpleNamespace(**payload)


def _register(name: str, handler, **kwargs):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=handler,
        exclusive=True,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _snapshot_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def test_checkpoint_created_before_exclusive_tool(tmp_path: Path):
    manager = _FakeCheckpointManager()
    ctx = _ctx(tmp_path, manager)
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")

    async def handler(*, ctx, args):
        return ToolResult.text("ok")

    _register("cp.create", handler)
    result, _ = _run(dispatch_one("cp.create", {"path": "a.txt"}, ctx=ctx))
    assert result.is_error is False
    assert len(manager.created) == 1
    created_paths, description, operation_type, checkpoint_id = manager.created[0]
    assert created_paths == [str(path.resolve())]
    assert description == "auto before cp.create"
    assert operation_type == "auto"
    assert result.metadata["auto_checkpoint_id"] == checkpoint_id


def test_rollback_on_error_when_auto_rollback_true(tmp_path: Path):
    manager = _FakeCheckpointManager()
    ctx = _ctx(tmp_path, manager)
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")

    async def handler(*, ctx, args):
        return ToolResult.error("boom")

    _register("cp.rollback", handler, auto_rollback=True)
    result, _ = _run(dispatch_one("cp.rollback", {"path": "b.txt"}, ctx=ctx))
    assert result.is_error
    assert len(manager.created) == 1
    assert manager.restored == [manager.created[0][3]]
    assert result.metadata["rolled_back"] is True


def test_no_rollback_when_auto_rollback_false(tmp_path: Path):
    manager = _FakeCheckpointManager()
    ctx = _ctx(tmp_path, manager)
    (tmp_path / "c.txt").write_text("x", encoding="utf-8")

    async def handler(*, ctx, args):
        return ToolResult.error("boom")

    _register("cp.no_rollback", handler, auto_rollback=False)
    result, _ = _run(dispatch_one("cp.no_rollback", {"path": "c.txt"}, ctx=ctx))
    assert result.is_error
    assert len(manager.created) == 1
    assert manager.restored == []
    assert result.metadata.get("rolled_back") is None


def test_disabled_when_checkpointing_false(tmp_path: Path):
    manager = _FakeCheckpointManager()
    cfg = SimpleNamespace(
        checkpoint=SimpleNamespace(enabled=False),
        tools=SimpleNamespace(auto_checkpoint=True),
    )
    ctx = _ctx(tmp_path, manager, config=cfg)
    (tmp_path / "d.txt").write_text("x", encoding="utf-8")

    async def handler(*, ctx, args):
        return ToolResult.text("ok")

    _register("cp.disabled", handler)
    result, _ = _run(dispatch_one("cp.disabled", {"path": "d.txt"}, ctx=ctx))
    assert result.is_error is False
    assert manager.created == []
