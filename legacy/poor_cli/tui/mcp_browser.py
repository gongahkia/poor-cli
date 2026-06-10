"""State helpers for the MCP marketplace browser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class McpMarketplaceRow:
    name: str
    description: str = ""
    downloads: int = 0
    version: str = ""
    installed: bool = False
    enabled: bool = False
    tools: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "downloads": self.downloads,
            "version": self.version,
            "installed": self.installed,
            "enabled": self.enabled,
            "tools": list(self.tools),
            "raw": dict(self.raw),
        }


@dataclass
class McpMarketplaceState:
    query: str = ""
    rows: List[McpMarketplaceRow] = field(default_factory=list)
    selected_index: int = 0
    enabled: bool = False
    message: str = ""

    @property
    def selected(self) -> McpMarketplaceRow | None:
        if not self.rows:
            return None
        return self.rows[max(0, min(self.selected_index, len(self.rows) - 1))]

    @classmethod
    def from_search_payload(
        cls,
        payload: Dict[str, Any],
        *,
        installed_servers: List[Dict[str, Any]] | None = None,
        query: str = "",
    ) -> "McpMarketplaceState":
        installed = {
            str(server.get("name") or ""): bool(server.get("enabled", True))
            for server in (installed_servers or [])
            if isinstance(server, dict)
        }
        enabled = bool(payload.get("enabled", True))
        rows = normalize_marketplace_results(payload, installed)
        message = ""
        if not enabled:
            message = "MCP marketplace disabled. Enable mcp.marketplace.enabled first."
        elif payload.get("error") == "missing_aiohttp":
            message = "Install poor-cli[anthropic,mcp] for marketplace registry access."
        elif not rows:
            message = "No MCP registry servers found."
        return cls(query=query, rows=rows, enabled=enabled, message=message)


def normalize_marketplace_results(
    payload: Dict[str, Any],
    installed: Dict[str, bool] | None = None,
) -> List[McpMarketplaceRow]:
    installed = installed or {}
    raw_servers = payload.get("servers") or payload.get("results") or []
    if not isinstance(raw_servers, list):
        return []
    rows: List[McpMarketplaceRow] = []
    for raw in raw_servers:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("id") or raw.get("serverName") or "").strip()
        if not name:
            continue
        rows.append(
            McpMarketplaceRow(
                name=name,
                description=str(raw.get("description") or raw.get("summary") or ""),
                downloads=_int_value(raw.get("downloads") or raw.get("downloadCount") or 0),
                version=str(raw.get("version") or raw.get("latestVersion") or ""),
                installed=name in installed,
                enabled=bool(installed.get(name, False)),
                tools=_tool_names(raw),
                raw=raw,
            )
        )
    return rows


def _tool_names(raw: Dict[str, Any]) -> List[str]:
    tools = raw.get("tools") or raw.get("toolNames") or []
    if not isinstance(tools, list):
        return []
    names: List[str] = []
    for tool in tools:
        value = tool.get("name") if isinstance(tool, dict) else tool
        text = str(value or "").strip()
        if text:
            names.append(text)
    return names


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
