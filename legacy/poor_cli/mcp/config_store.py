"""Read/write helpers for .poor-cli/mcp.json."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .multi_server import normalize_mcp_config
from .registry import registry_enabled_from_config


def default_config() -> dict[str, Any]:
    return {"servers": [], "registry_autodiscover": False}


class McpConfigStore:
    def __init__(self, repo_root: Path | None = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.path = self.repo_root / ".poor-cli" / "mcp.json"

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return default_config()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default_config()

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return data

    def list_servers(self) -> list[dict[str, Any]]:
        data = self.load()
        servers = normalize_mcp_config(data).get("servers", {})
        return [
            {"name": name, **deepcopy(cfg)}
            for name, cfg in sorted(servers.items())
            if isinstance(cfg, dict)
        ]

    def registry_enabled(self) -> bool:
        return registry_enabled_from_config(self.load())

    def upsert_server(self, spec: dict[str, Any]) -> dict[str, Any]:
        name = str(spec.get("name", "")).strip()
        if not name:
            raise ValueError("MCP server name is required")
        data = self.load()
        servers = normalize_mcp_config(data).get("servers", {})
        servers[name] = {key: deepcopy(value) for key, value in spec.items() if key != "name"}
        return self.save(self._with_servers(data, servers))

    def toggle_server(self, name: str, enabled: bool | None = None) -> dict[str, Any]:
        server_name = str(name or "").strip()
        data = self.load()
        servers = normalize_mcp_config(data).get("servers", {})
        if server_name not in servers:
            raise KeyError(f"MCP server not found: {server_name}")
        current = bool(servers[server_name].get("enabled", True))
        servers[server_name]["enabled"] = (not current) if enabled is None else bool(enabled)
        return self.save(self._with_servers(data, servers))

    def remove_server(self, name: str) -> dict[str, Any]:
        server_name = str(name or "").strip()
        data = self.load()
        servers = normalize_mcp_config(data).get("servers", {})
        if server_name not in servers:
            raise KeyError(f"MCP server not found: {server_name}")
        servers.pop(server_name, None)
        return self.save(self._with_servers(data, servers))

    def _with_servers(self, data: dict[str, Any], servers: dict[str, dict[str, Any]]) -> dict[str, Any]:
        updated = deepcopy(data)
        if isinstance(updated.get("servers"), dict):
            updated["servers"] = {name: deepcopy(cfg) for name, cfg in sorted(servers.items())}
        elif isinstance(updated.get("mcpServers"), dict):
            updated["mcpServers"] = {name: deepcopy(cfg) for name, cfg in sorted(servers.items())}
        else:
            updated["servers"] = [
                {"name": name, **deepcopy(cfg)}
                for name, cfg in sorted(servers.items())
            ]
        if "registry_autodiscover" not in updated:
            updated["registry_autodiscover"] = False
        return updated
