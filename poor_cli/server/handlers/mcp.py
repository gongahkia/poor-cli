from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from poor_cli.mcp.config_store import McpConfigStore
from poor_cli.mcp.registry import McpRegistryClient
from poor_cli.permission_dsl import remove_mcp_default_deny_rules
from poor_cli.server.registry import register
from poor_cli.server.types import InvalidParamsError
from poor_cli.tui.mcp_browser import McpMarketplaceState


def _repo_root(ctx: Any) -> Path:
    try:
        core = ctx.core
    except Exception:
        core = None
    return Path(getattr(core, "_repo_root", Path.cwd())).resolve()


def _store(ctx: Any) -> McpConfigStore:
    return McpConfigStore(_repo_root(ctx))


def _marketplace_enabled(ctx: Any) -> bool:
    try:
        marketplace = getattr(getattr(ctx.core.config, "mcp", None), "marketplace", None)
    except Exception:
        marketplace = None
    if marketplace is not None:
        return bool(getattr(marketplace, "enabled", False))
    return _store(ctx).registry_enabled()


def _manager(ctx: Any) -> Any:
    try:
        return getattr(ctx.core, "_mcp_manager", None)
    except Exception:
        return None


async def _ensure_manager_ready(ctx: Any) -> None:
    try:
        ensure_mcp = getattr(ctx.core, "_ensure_mcp_manager_initialized", None)
    except Exception:
        ensure_mcp = None
    if callable(ensure_mcp):
        await ensure_mcp()


def _status_by_name(ctx: Any) -> dict[str, dict[str, Any]]:
    manager = _manager(ctx)
    if manager is None:
        return {}
    try:
        status = manager.status()
    except Exception:
        return {}
    servers = status.get("servers", {}) if isinstance(status, dict) else {}
    return servers if isinstance(servers, dict) else {}


def _merge_servers(configured: list[dict[str, Any]], statuses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for server in configured:
        name = str(server.get("name", ""))
        status = statuses.get(name, {})
        error = status.get("error") or server.get("lastError") or server.get("error")
        connected = bool(status.get("connected", False))
        enabled = bool(server.get("enabled", True))
        rows.append({
            **server,
            "status": "disabled" if not enabled else ("error" if error else ("healthy" if connected else "unknown")),
            "connected": connected,
            "toolCount": status.get("toolCount", status.get("tools_count", server.get("toolCount", 0))),
            "tools": status.get("registeredTools", status.get("tools", server.get("tools", []))),
            "lastError": error or "",
        })
    return rows


class McpHandlersMixin:
    async def handle_mcp_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        store = _store(self)
        return {
            "configPath": str(store.path),
            "registryAutodiscover": store.registry_enabled(),
            "servers": _merge_servers(store.list_servers(), _status_by_name(self)),
        }

    async def handle_mcp_toggle(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("name is required")
        try:
            _store(self).toggle_server(name, params.get("enabled") if "enabled" in params else None)
        except KeyError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return await self.handle_mcp_list({})

    async def handle_mcp_edit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        spec = params.get("server") or params.get("spec") or {}
        if not isinstance(spec, dict):
            raise InvalidParamsError("server must be an object")
        try:
            _store(self).upsert_server(spec)
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return await self.handle_mcp_list({})

    async def handle_mcp_remove(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if params.get("confirmed") is not True:
            raise InvalidParamsError("confirmed=true is required")
        name = str(params.get("name", "")).strip()
        if not name:
            raise InvalidParamsError("name is required")
        try:
            _store(self).remove_server(name)
        except KeyError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return await self.handle_mcp_list({})

    async def handle_mcp_health(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name", "")).strip()
        await _ensure_manager_ready(self)
        manager = _manager(self)
        if manager is None:
            return {"servers": [], "error": "No MCP servers configured"}
        results = await manager.health_check_all()
        rows = [{"name": key, "healthy": bool(value)} for key, value in sorted(results.items())]
        if name:
            rows = [row for row in rows if row["name"] == name]
        return {"servers": rows}

    async def handle_mcp_test(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = str(params.get("tool") or params.get("toolName") or "").strip()
        if not tool:
            raise InvalidParamsError("tool is required")
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            raise InvalidParamsError("arguments must be an object")
        await _ensure_manager_ready(self)
        manager = _manager(self)
        if manager is None:
            raise InvalidParamsError("No MCP servers configured")
        result = await manager.call_tool(tool, args)
        return {"tool": tool, "result": result}

    async def handle_mcp_registry_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        store = _store(self)
        enabled = store.registry_enabled()
        if not enabled:
            return {"enabled": False, "servers": [], "page": int(params.get("page", 0) or 0)}
        query = str(params.get("query", "") or "")
        limit = int(params.get("limit", 20) or 20)
        offset = int(params.get("offset", 0) or 0)
        client = McpRegistryClient(enabled=True)
        result = await client.search(query=query, limit=limit, offset=offset)
        result["enabled"] = True
        result["limit"] = limit
        result["offset"] = offset
        result["page"] = int(offset / limit) if limit > 0 else 0
        return result

    async def handle_mcp_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        store = _store(self)
        query = str(params.get("query", "") or "")
        limit = int(params.get("limit", 20) or 20)
        offset = int(params.get("offset", 0) or 0)
        enabled = _marketplace_enabled(self)
        if not enabled:
            payload = {"enabled": False, "servers": [], "page": int(params.get("page", 0) or 0)}
        else:
            try:
                client = McpRegistryClient(enabled=True)
                payload = await client.search_cached(query=query, limit=limit, offset=offset, repo_root=_repo_root(self))
            except RuntimeError as exc:
                if "aiohttp required" not in str(exc):
                    raise
                payload = {"enabled": True, "servers": [], "error": "missing_aiohttp"}
            payload["enabled"] = True
            payload["limit"] = limit
            payload["offset"] = offset
            payload["page"] = int(offset / limit) if limit > 0 else 0
        state = McpMarketplaceState.from_search_payload(
            payload,
            installed_servers=store.list_servers(),
            query=query,
        )
        return {
            **payload,
            "rows": [row.to_dict() for row in state.rows],
            "message": state.message,
            "configPath": str(store.path),
        }

    async def handle_mcp_install(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not _marketplace_enabled(self):
            return {"enabled": False, "installed": False, "error": "MCP marketplace disabled"}
        name = str(params.get("name") or params.get("serverName") or "").strip()
        if not name:
            raise InvalidParamsError("name is required")
        version = params.get("version")
        server = params.get("server") if isinstance(params.get("server"), dict) else None
        try:
            install = await McpRegistryClient(enabled=True).install(
                name,
                str(version) if version else None,
                repo_root=_repo_root(self),
                server=server,
            )
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return {"enabled": True, "installed": True, **install}

    async def handle_mcp_uninstall(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if params.get("confirmed") is not True:
            raise InvalidParamsError("confirmed=true is required")
        name = str(params.get("name") or params.get("serverName") or "").strip()
        if not name:
            raise InvalidParamsError("name is required")
        try:
            _store(self).remove_server(name)
        except KeyError as exc:
            raise InvalidParamsError(str(exc)) from exc
        permission = remove_mcp_default_deny_rules(_repo_root(self), name)
        return {"uninstalled": True, "permission": permission, **await self.handle_mcp_list({})}

    async def handle_mcp_enable(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name") or params.get("serverName") or "").strip()
        if not name:
            raise InvalidParamsError("name is required")
        try:
            _store(self).toggle_server(name, True)
        except KeyError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return await self.handle_mcp_list({})

    async def handle_mcp_disable(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = str(params.get("name") or params.get("serverName") or "").strip()
        if not name:
            raise InvalidParamsError("name is required")
        try:
            _store(self).toggle_server(name, False)
        except KeyError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return await self.handle_mcp_list({})


@register("mcp.list")
@register("poor-cli/mcpList")
async def _rpc_mcp_list(ctx, params):
    return await ctx.handle_mcp_list(params)


@register("mcp.toggle")
@register("poor-cli/mcpToggle")
async def _rpc_mcp_toggle(ctx, params):
    return await ctx.handle_mcp_toggle(params)


@register("mcp.edit")
@register("poor-cli/mcpEdit")
async def _rpc_mcp_edit(ctx, params):
    return await ctx.handle_mcp_edit(params)


@register("mcp.remove")
@register("poor-cli/mcpRemove")
async def _rpc_mcp_remove(ctx, params):
    return await ctx.handle_mcp_remove(params)


@register("mcp.health")
@register("poor-cli/mcpHealth")
async def _rpc_mcp_health(ctx, params):
    return await ctx.handle_mcp_health(params)


@register("mcp.test")
@register("poor-cli/mcpTest")
async def _rpc_mcp_test(ctx, params):
    return await ctx.handle_mcp_test(params)


@register("mcp.registry.search")
@register("registrySearch")
@register("poor-cli/registrySearch")
async def _rpc_mcp_registry_search(ctx, params):
    return await ctx.handle_mcp_registry_search(params)


@register("poor-cli/mcpSearch")
async def _rpc_mcp_search(ctx, params):
    return await ctx.handle_mcp_search(params)


@register("poor-cli/mcpInstall")
async def _rpc_mcp_install(ctx, params):
    return await ctx.handle_mcp_install(params)


@register("poor-cli/mcpUninstall")
async def _rpc_mcp_uninstall(ctx, params):
    return await ctx.handle_mcp_uninstall(params)


@register("poor-cli/mcpEnable")
async def _rpc_mcp_enable(ctx, params):
    return await ctx.handle_mcp_enable(params)


@register("poor-cli/mcpDisable")
async def _rpc_mcp_disable(ctx, params):
    return await ctx.handle_mcp_disable(params)
