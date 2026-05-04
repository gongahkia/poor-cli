from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

from poor_cli.config import Config
from poor_cli.mcp.registry import McpRegistryClient
from poor_cli.server.handlers.mcp import McpHandlersMixin
from poor_cli.server.registry import REGISTRY
from poor_cli.tui.mcp_browser import McpMarketplaceState, normalize_marketplace_results


class _Core:
    def __init__(self, repo_root: Path, config: Config | None = None):
        self._repo_root = repo_root
        self.config = config or Config()
        self._mcp_manager = None


class _Ctx(McpHandlersMixin):
    def __init__(self, repo_root: Path, config: Config | None = None):
        self.core = _Core(repo_root, config)


def _marketplace_config() -> Config:
    config = Config()
    config.mcp.marketplace.enabled = True
    return config


def test_marketplace_rows_normalize_missing_fields():
    rows = normalize_marketplace_results(
        {"servers": [{"name": "github"}, {"id": "linear", "downloadCount": "7"}]},
        {"github": False},
    )

    assert [row.name for row in rows] == ["github", "linear"]
    assert rows[0].installed is True
    assert rows[0].enabled is False
    assert rows[1].downloads == 7


def test_marketplace_state_reports_missing_aiohttp_command():
    state = McpMarketplaceState.from_search_payload({"enabled": True, "error": "missing_aiohttp", "servers": []})

    assert "poor-cli[anthropic,mcp]" in state.message


def test_registry_install_writes_disabled_config_and_default_deny(tmp_path):
    result = asyncio.run(
        McpRegistryClient(enabled=False).install(
            "github",
            "1.2.3",
            repo_root=tmp_path,
            server={"command": ["npx", "@modelcontextprotocol/server-github"], "tools": ["github:list"]},
        )
    )

    assert result["server"]["enabled"] is False
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    row = next(server for server in data["servers"] if server["name"] == "github")
    assert row["command"] == ["npx", "@modelcontextprotocol/server-github"]

    permissions = yaml.safe_load((tmp_path / ".poor-cli" / "permissions.yml").read_text(encoding="utf-8"))
    assert permissions["rules"][0]["tool"] == "github:list"
    assert permissions["rules"][0]["deny"] is True
    assert permissions["rules"][0]["source"] == "mcp_marketplace"


def test_mcp_install_enable_disable_uninstall_round_trip(tmp_path):
    ctx = _Ctx(tmp_path, _marketplace_config())
    asyncio.run(
        REGISTRY["poor-cli/mcpInstall"](
            ctx,
            {
                "name": "github",
                "version": "1.0.0",
                "server": {"command": ["npx", "mcp-github"], "tools": ["github:list"]},
            },
        )
    )

    asyncio.run(REGISTRY["poor-cli/mcpEnable"](ctx, {"name": "github"}))
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    assert next(row for row in data["servers"] if row["name"] == "github")["enabled"] is True

    asyncio.run(REGISTRY["poor-cli/mcpDisable"](ctx, {"name": "github"}))
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    assert next(row for row in data["servers"] if row["name"] == "github")["enabled"] is False

    asyncio.run(REGISTRY["poor-cli/mcpUninstall"](ctx, {"name": "github", "confirmed": True}))
    data = json.loads((tmp_path / ".poor-cli" / "mcp.json").read_text(encoding="utf-8"))
    assert data["servers"] == []
    permissions = yaml.safe_load((tmp_path / ".poor-cli" / "permissions.yml").read_text(encoding="utf-8"))
    assert permissions["rules"] == []


def test_mcp_search_disabled_by_config_flag(tmp_path):
    result = asyncio.run(REGISTRY["poor-cli/mcpSearch"](_Ctx(tmp_path, Config()), {"query": "github"}))

    assert result["enabled"] is False
    assert result["rows"] == []
