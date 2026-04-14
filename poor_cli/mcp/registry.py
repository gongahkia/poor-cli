"""Lazy MCP registry client."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlencode

REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io"


class McpRegistryClient:
    def __init__(self, enabled: bool = False, base_url: str = REGISTRY_BASE_URL):
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str = "", limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        if not self.enabled:
            return {"servers": [], "enabled": False}
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("aiohttp required for MCP registry access") from exc
        params = {"limit": str(limit), "offset": str(offset)}
        if query:
            params["search"] = query
        url = f"{self.base_url}/v0.1/servers?{urlencode(params)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_versions(self, server_name: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"versions": [], "enabled": False}
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("aiohttp required for MCP registry access") from exc
        url = f"{self.base_url}/v0.1/servers/{server_name}/versions"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()


def registry_enabled_from_config(config: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(config, dict):
        return False
    if bool(config.get("registry_autodiscover", False)):
        return True
    mcp = config.get("mcp")
    if not isinstance(mcp, dict):
        return False
    registry = mcp.get("registry")
    return isinstance(registry, dict) and bool(registry.get("enabled", False))
