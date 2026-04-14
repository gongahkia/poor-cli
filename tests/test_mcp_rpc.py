from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import poor_cli.server.handlers as server_handlers
from poor_cli.server.handlers.mcp import McpHandlersMixin
from poor_cli.server.registry import REGISTRY


class _Core:
    def __init__(self, repo_root: Path, manager=None):
        self._repo_root = repo_root
        self._mcp_manager = manager


class _Ctx(McpHandlersMixin):
    def __init__(self, repo_root: Path, manager=None):
        self.core = _Core(repo_root, manager)


class _Manager:
    def status(self):
        return {
            "servers": {
                "github": {"connected": True, "toolCount": 2, "registeredTools": ["search", "issue"]},
                "bad": {"connected": False, "toolCount": 0, "error": "boom"},
            }
        }

    async def health_check_all(self):
        return {"github": True, "bad": False}

    async def call_tool(self, tool, args):
        return f"{tool}:{args['text']}"


def _write_config(root: Path) -> None:
    path = root / ".poor-cli" / "mcp.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "registry_autodiscover": False,
                "servers": [
                    {"name": "github", "transport": "stdio", "command": ["npx", "server"], "enabled": True},
                    {"name": "bad", "transport": "stdio", "command": ["missing"], "enabled": True},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_mcp_rpc_list_merges_config_with_status(tmp_path):
    assert server_handlers.HandlerMixin is not None
    _write_config(tmp_path)
    result = asyncio.run(REGISTRY["mcp.list"](_Ctx(tmp_path, _Manager()), {}))
    rows = {row["name"]: row for row in result["servers"]}
    assert rows["github"]["status"] == "healthy"
    assert rows["github"]["toolCount"] == 2
    assert rows["bad"]["status"] == "error"
    assert rows["bad"]["lastError"] == "boom"


def test_mcp_rpc_toggle_edit_remove_round_trips_config(tmp_path):
    _write_config(tmp_path)
    ctx = _Ctx(tmp_path)
    asyncio.run(REGISTRY["mcp.toggle"](ctx, {"name": "github"}))
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    assert next(row for row in data["servers"] if row["name"] == "github")["enabled"] is False

    asyncio.run(
        REGISTRY["mcp.edit"](
            ctx,
            {"server": {"name": "linear", "transport": "http", "url": "http://127.0.0.1/mcp", "enabled": False}},
        )
    )
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    assert next(row for row in data["servers"] if row["name"] == "linear")["url"] == "http://127.0.0.1/mcp"

    with pytest.raises(Exception):
        asyncio.run(REGISTRY["mcp.remove"](ctx, {"name": "linear"}))
    asyncio.run(REGISTRY["mcp.remove"](ctx, {"name": "linear", "confirmed": True}))
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    assert "linear" not in {row["name"] for row in data["servers"]}


def test_mcp_rpc_health_and_test_surface(tmp_path):
    _write_config(tmp_path)
    ctx = _Ctx(tmp_path, _Manager())
    health = asyncio.run(REGISTRY["mcp.health"](ctx, {"name": "github"}))
    assert health == {"servers": [{"name": "github", "healthy": True}]}
    called = asyncio.run(REGISTRY["mcp.test"](ctx, {"tool": "github:echo", "arguments": {"text": "ok"}}))
    assert called == {"tool": "github:echo", "result": "github:echo:ok"}


def test_mcp_registry_search_respects_disabled_gate(tmp_path):
    _write_config(tmp_path)
    result = asyncio.run(REGISTRY["mcp.registry.search"](_Ctx(tmp_path), {"query": "github"}))
    assert result["enabled"] is False
    assert result["servers"] == []
