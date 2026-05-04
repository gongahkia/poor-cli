"""Lazy MCP registry client."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from poor_cli.permission_dsl import ensure_mcp_default_deny_rules

REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io"
SEARCH_CACHE_TTL_SECONDS = 300


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

    async def search_cached(
        self,
        query: str = "",
        limit: int = 20,
        offset: int = 0,
        *,
        repo_root: Path | None = None,
        ttl_seconds: int = SEARCH_CACHE_TTL_SECONDS,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"servers": [], "enabled": False}
        root = (repo_root or Path.cwd()).resolve()
        cache_path = root / ".poor-cli" / "cache" / "mcp_search.json"
        cache_key = json.dumps({"query": query, "limit": limit, "offset": offset}, sort_keys=True)
        cached = _read_search_cache(cache_path)
        if cached.get("key") == cache_key and time.time() - float(cached.get("ts", 0)) <= ttl_seconds:
            payload = cached.get("payload")
            if isinstance(payload, dict):
                return {**payload, "cache": "hit"}
        payload = await self.search(query=query, limit=limit, offset=offset)
        _write_search_cache(cache_path, {"key": cache_key, "ts": time.time(), "payload": payload})
        return {**payload, "cache": "miss"}

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

    async def install(
        self,
        server_name: str,
        version: str | None = None,
        *,
        repo_root: Path | None = None,
        server: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        name = str(server_name or "").strip()
        if not name:
            raise ValueError("MCP server name is required")
        metadata = dict(server or {})
        if not metadata and self.enabled:
            versions = await self.get_versions(name)
            metadata = _select_version_metadata(versions, version)
        spec = _install_spec_from_metadata(name, version, metadata)
        from .config_store import McpConfigStore

        store = McpConfigStore(repo_root)
        config = store.upsert_server(spec)
        permission = ensure_mcp_default_deny_rules(repo_root, name, _tool_names_from_metadata(metadata))
        return {"server": spec, "configPath": str(store.path), "config": config, "permission": permission}


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


def _read_search_cache(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_search_cache(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _select_version_metadata(versions: Dict[str, Any], requested: str | None) -> Dict[str, Any]:
    candidates = versions.get("versions", [])
    if not isinstance(candidates, list):
        return versions
    if requested:
        for candidate in candidates:
            if isinstance(candidate, dict) and str(candidate.get("version") or candidate.get("name") or "") == requested:
                return candidate
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return versions


def _install_spec_from_metadata(name: str, version: str | None, metadata: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("install", "config", "mcpConfig", "server", "spec"):
        candidate = metadata.get(key)
        if isinstance(candidate, dict):
            return _normalize_install_spec(name, version, candidate)
    packages = metadata.get("packages")
    if isinstance(packages, list):
        for package in packages:
            if isinstance(package, dict):
                return _normalize_install_spec(name, version, package)
    return _normalize_install_spec(name, version, metadata)


def _normalize_install_spec(name: str, version: str | None, raw: Dict[str, Any]) -> Dict[str, Any]:
    spec: Dict[str, Any] = {"name": name, "enabled": False}
    transport = str(raw.get("transport") or raw.get("type") or "").lower()
    url = raw.get("url") or raw.get("endpoint")
    command = raw.get("command") or raw.get("binary") or raw.get("package")
    args = raw.get("args") if isinstance(raw.get("args"), list) else []
    if url or transport in {"http", "streamable-http"}:
        spec.update({"transport": "http", "url": str(url or "")})
    elif isinstance(command, list):
        spec.update({"transport": "stdio", "command": [str(part) for part in command]})
    elif isinstance(command, str) and command:
        spec.update({"transport": "stdio", "command": [command, *[str(arg) for arg in args]]})
    else:
        spec.update({"transport": "stdio", "command": [name]})
    if isinstance(raw.get("env"), dict):
        spec["env"] = {str(key): str(value) for key, value in raw["env"].items()}
    if isinstance(raw.get("headers"), dict):
        spec["headers"] = {str(key): str(value) for key, value in raw["headers"].items()}
    tools = _tool_names_from_metadata(raw)
    if tools:
        spec["tools"] = tools
    if version:
        spec["version"] = version
    return spec


def _tool_names_from_metadata(metadata: Dict[str, Any]) -> list[str]:
    tools = metadata.get("tools") or metadata.get("toolNames") or []
    if not isinstance(tools, list):
        return []
    names = []
    for tool in tools:
        if isinstance(tool, dict):
            value = tool.get("name")
        else:
            value = tool
        if str(value or "").strip():
            names.append(str(value).strip())
    return names
