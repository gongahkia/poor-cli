"""MCP multi-server orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from poor_cli.exceptions import setup_logger
from poor_cli.tool_output_filter import ToolOutputFilter, empty_filter_stats

from .http import MCP_PROTOCOL_VERSION, StreamableHttpTransport
from .registry import McpRegistryClient, registry_enabled_from_config
from .stdio import McpTransport, StdioTransport

logger = setup_logger(__name__)

MCP_CONFIG_FILENAME = "mcp.json"
MCP_CONFIG_PATHS = [
    ".poor-cli/mcp.json",
    ".claude/mcp.json",
]


@dataclass
class McpServerSpec:
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command: Optional[list[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    enabled: bool = True
    headers: Optional[Dict[str, str]] = None
    allow_tools: Optional[list[str]] = None
    deny_tools: Optional[list[str]] = None


def discover_mcp_config(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    root = (repo_root or Path.cwd()).resolve()
    candidates = [root / p for p in MCP_CONFIG_PATHS]
    candidates.append(Path.home() / ".poor-cli" / MCP_CONFIG_FILENAME)
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    logger.info("discovered MCP config at %s", path)
                    return normalize_mcp_config(data)
            except Exception as exc:
                logger.warning("failed to parse MCP config %s: %s", path, exc)
    return {}


def normalize_mcp_config(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    if "servers" in data and isinstance(data["servers"], list):
        return {
            "servers": {
                str(server.get("name", "")).strip(): _normalize_server_entry(server)
                for server in data["servers"]
                if isinstance(server, dict) and str(server.get("name", "")).strip()
            },
            "multi": bool(data.get("multi", True)),
            "registry_autodiscover": registry_enabled_from_config(data),
        }
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        return {"servers": {name: _normalize_server_entry({"name": name, **cfg}) for name, cfg in servers.items() if isinstance(cfg, dict)}, "multi": bool(data.get("multi", True)), "registry_autodiscover": registry_enabled_from_config(data)}
    if isinstance(data.get("servers"), dict):
        return {"servers": {name: _normalize_server_entry({"name": name, **cfg}) for name, cfg in data["servers"].items() if isinstance(cfg, dict)}, "multi": bool(data.get("multi", True)), "registry_autodiscover": registry_enabled_from_config(data)}
    return {"servers": {name: _normalize_server_entry({"name": name, **cfg}) for name, cfg in data.items() if isinstance(cfg, dict)}, "multi": True, "registry_autodiscover": False}


def load_mcp_server_specs(repo_root: Optional[Path] = None) -> list[McpServerSpec]:
    config = discover_mcp_config(repo_root=repo_root)
    return specs_from_config(config)


def specs_from_config(config: Dict[str, Any]) -> list[McpServerSpec]:
    servers = _servers_from_config(config)
    specs: list[McpServerSpec] = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        spec = _spec_from_mapping(name, cfg)
        if spec.enabled:
            specs.append(spec)
    return specs


def _servers_from_config(config: Any) -> Dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    if "servers" in config and isinstance(config["servers"], dict):
        return config["servers"]
    if "servers" in config and isinstance(config["servers"], list):
        return normalize_mcp_config(config).get("servers", {})
    if "mcpServers" in config and isinstance(config["mcpServers"], dict):
        return normalize_mcp_config(config).get("servers", {})
    return config


def _normalize_server_entry(server: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(server)
    command = cfg.get("command")
    args = cfg.get("args")
    if isinstance(command, list):
        cfg["command"] = [str(part) for part in command]
        cfg.pop("args", None)
    elif isinstance(command, str):
        if isinstance(args, list):
            cfg["command"] = [command, *[str(arg) for arg in args]]
            cfg.pop("args", None)
        else:
            cfg["command"] = [command]
    env = cfg.get("env")
    if isinstance(env, dict):
        cfg["env"] = {str(key): _expand_env_value(str(value)) for key, value in env.items()}
    transport = str(cfg.get("transport", "stdio")).lower()
    if transport == "streamable-http":
        transport = "http"
    cfg["transport"] = transport
    return cfg


def _spec_from_mapping(name: str, cfg: Dict[str, Any]) -> McpServerSpec:
    cfg = _normalize_server_entry({"name": name, **cfg})
    transport = str(cfg.get("transport", "stdio")).lower()
    if transport == "sse":
        raise ValueError(f"MCP SSE transport for '{name}' is deprecated; use transport='http'")
    if transport not in {"stdio", "http"}:
        raise ValueError(f"unsupported MCP transport for '{name}': {transport}")
    return McpServerSpec(
        name=name,
        transport=transport,  # type: ignore[arg-type]
        command=cfg.get("command"),
        url=cfg.get("url"),
        env=cfg.get("env") or {},
        enabled=bool(cfg.get("enabled", True)),
        headers=cfg.get("headers") or {},
        allow_tools=cfg.get("allow_tools") or [],
        deny_tools=cfg.get("deny_tools") or [],
    )


def _expand_env_value(value: str) -> str:
    return re.sub(r"\$\{([^}]+)\}", lambda match: os.environ.get(match.group(1), ""), value)


def _json_schema_type_to_gemini(type_name: str) -> str:
    mapping = {
        "string": "STRING",
        "number": "NUMBER",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }
    return mapping.get(type_name.lower(), "STRING")


def _render_mcp_result(result: Dict[str, Any]) -> str:
    content = result.get("content", [])
    if content and isinstance(content, list):
        first = content[0]
        if isinstance(first, dict):
            return str(first.get("text", ""))
    return json.dumps(result, ensure_ascii=False)


def _convert_tool_declarations(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    declarations: List[Dict[str, Any]] = []
    for tool in tools:
        name = tool.get("name", "")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        decl_props: Dict[str, Any] = {}
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")
            decl_props[prop_name] = {
                "type": _json_schema_type_to_gemini(prop_type),
                "description": prop_schema.get("description", ""),
            }
        declarations.append({
            "name": name,
            "description": description,
            "parameters": {"type": "OBJECT", "properties": decl_props, "required": required},
        })
    return declarations


class MCPClient:
    def __init__(
        self,
        name: str,
        command: str | list[str],
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        transport: Optional[McpTransport] = None,
    ):
        self.name = name
        command_list = command if isinstance(command, list) else [command, *(args or [])]
        self.transport = transport or StdioTransport([str(part) for part in command_list], env=env)
        self.capabilities: Dict[str, Any] = {}
        self._next_request_id = 3
        self._tools: List[Dict[str, Any]] = []

    @property
    def process(self) -> Any:
        return getattr(self.transport, "process", None)

    async def connect(self) -> None:
        await self.transport.connect()
        response = await self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "poor-cli"},
            },
            request_id=1,
        )
        self.capabilities = response.get("capabilities", {})

    async def _request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = None) -> Dict[str, Any]:
        rid = request_id if request_id is not None else self._next_request_id
        if request_id is None:
            self._next_request_id += 1
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        await self.transport.send(payload)
        response = await self.transport.recv()
        if "error" in response:
            raise RuntimeError(response["error"].get("message", response["error"]))
        return response.get("result", {})

    async def list_tools(self) -> List[Dict[str, Any]]:
        result = await self._request("tools/list", request_id=2)
        declarations = _convert_tool_declarations(result.get("tools", []))
        self._tools = declarations
        return declarations

    async def list_resources(self) -> List[Dict[str, Any]]:
        return (await self._request("resources/list")).get("resources", [])

    async def list_prompts(self) -> List[Dict[str, Any]]:
        return (await self._request("prompts/list")).get("prompts", [])

    async def call_tool_raw(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("tools/call", {"name": name, "arguments": arguments})

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        return _render_mcp_result(await self.call_tool_raw(name, arguments))

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(self._request("ping"), timeout=3)
            return True
        except Exception:
            if hasattr(self.transport, "is_alive"):
                return bool(self.transport.is_alive())
            return False

    async def disconnect(self) -> None:
        await self.transport.close()


class MCPHTTPClient(MCPClient):
    def __init__(self, name: str, url: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(name=name, command=[], transport=StreamableHttpTransport(url=url, headers=headers))


class MultiMcp:
    def __init__(
        self,
        servers_config: Dict[str, Any] | list[McpServerSpec],
        *,
        namespace_tools: bool = True,
        repo_root: Optional[Path] = None,
        registry_autodiscover: bool = False,
    ):
        normalized = servers_config if isinstance(servers_config, list) else normalize_mcp_config(servers_config)
        self.servers_config = _servers_from_config(normalized) if not isinstance(normalized, list) else {spec.name: spec for spec in normalized}
        multi_enabled = True if isinstance(normalized, list) else bool(normalized.get("multi", True))
        self.namespace_tools = bool(namespace_tools and multi_enabled)
        self.clients: Dict[str, Any] = {}
        self._declarations: List[Dict[str, Any]] = []
        self._tool_to_client: Dict[str, Any] = {}
        self._tool_name_map: Dict[str, str] = {}
        self._tool_declarations: Dict[str, Dict[str, Any]] = {}
        self._server_declarations: Dict[str, List[Dict[str, Any]]] = {}
        self._loaded_servers: set[str] = set()
        self._server_status: Dict[str, Dict[str, Any]] = {}
        self._resources: Dict[str, List[Dict[str, Any]]] = {}
        self._prompts: Dict[str, List[Dict[str, Any]]] = {}
        self._output_filter = ToolOutputFilter(repo_root=repo_root or Path.cwd())
        self._output_filter_stats = empty_filter_stats()
        enabled = registry_autodiscover or (isinstance(normalized, dict) and bool(normalized.get("registry_autodiscover", False)))
        self.registry = McpRegistryClient(enabled=enabled)

    async def start_all(self, specs: Optional[list[McpServerSpec]] = None) -> None:
        if specs is not None:
            self.servers_config = {spec.name: spec for spec in specs}
        await self.initialize()

    async def initialize(self) -> None:
        await asyncio.gather(*(self._initialize_server(server_name, cfg) for server_name, cfg in self.servers_config.items()))

    async def _initialize_server(self, server_name: str, cfg: Any) -> None:
        try:
            spec = cfg if isinstance(cfg, McpServerSpec) else _spec_from_mapping(server_name, cfg)
        except Exception as exc:
            self._server_status[server_name] = self._status_entry(False, "unknown", "", [], error=str(exc))
            return
        command = spec.command or []
        self._server_status[server_name] = self._status_entry(spec.enabled, spec.transport, command or spec.url or "", [], error=None)
        if not spec.enabled:
            self._server_status[server_name]["error"] = "disabled by config"
            return
        try:
            client = self._create_client(spec.name, spec, spec.transport)
            await client.connect()
            self.clients[server_name] = client
            self._server_status[server_name]["connected"] = True
            try:
                self._resources[server_name] = await client.list_resources()
                self._server_status[server_name]["resources"] = [
                    resource.get("uri", resource.get("name", "")) for resource in self._resources[server_name]
                ]
            except Exception:
                self._resources[server_name] = []
            try:
                self._prompts[server_name] = await client.list_prompts()
                self._server_status[server_name]["prompts"] = [prompt.get("name", "") for prompt in self._prompts[server_name]]
            except Exception:
                self._prompts[server_name] = []
        except Exception as exc:
            logger.warning("Failed to initialize MCP server '%s': %s", server_name, exc)
            self._server_status[server_name]["error"] = str(exc)

    @staticmethod
    def _status_entry(enabled: bool, transport: str, command: Any, args: list[Any], error: Optional[str]) -> Dict[str, Any]:
        return {
            "configured": True,
            "enabled": enabled,
            "connected": False,
            "transport": transport,
            "toolCount": 0,
            "tools": [],
            "registeredTools": [],
            "resources": [],
            "prompts": [],
            "schemasLoaded": False,
            "error": error,
            "command": command,
            "args": args,
        }

    @staticmethod
    def _create_client(server_name: str, cfg: Any, transport: str) -> Any:
        spec = cfg if isinstance(cfg, McpServerSpec) else _spec_from_mapping(server_name, cfg)
        if transport == "http":
            if not spec.url:
                raise ValueError(f"MCP HTTP server '{server_name}' missing url")
            return MCPHTTPClient(name=server_name, url=spec.url, headers=spec.headers or {})
        if not spec.command:
            raise ValueError(f"MCP stdio server '{server_name}' missing command")
        return MCPClient(name=server_name, command=spec.command, env=spec.env or {})

    def get_server_names(self) -> List[str]:
        return list(self.servers_config)

    async def tools(self) -> List[Dict[str, Any]]:
        return await self.load_all_tool_declarations()

    async def call_tool(self, namespaced_name: str, args: Dict[str, Any]) -> str:
        return await self.execute_tool(namespaced_name, args)

    async def health(self) -> Dict[str, bool]:
        return await self.health_check_all()

    def _server_allow_tools(self, server_name: str) -> set[str]:
        cfg = self.servers_config.get(server_name, {})
        values = cfg.allow_tools if isinstance(cfg, McpServerSpec) else cfg.get("allow_tools", [])
        return {str(tool_name).strip() for tool_name in values or [] if str(tool_name).strip()}

    def _server_deny_tools(self, server_name: str) -> set[str]:
        cfg = self.servers_config.get(server_name, {})
        values = cfg.deny_tools if isinstance(cfg, McpServerSpec) else cfg.get("deny_tools", [])
        return {str(tool_name).strip() for tool_name in values or [] if str(tool_name).strip()}

    def _loaded_declarations_for_server(self, server_name: str) -> List[Dict[str, Any]]:
        return list(self._server_declarations.get(server_name, []))

    async def load_server_tools(self, server_names: List[str]) -> List[Dict[str, Any]]:
        loaded: List[Dict[str, Any]] = []
        for server_name in server_names:
            name = str(server_name or "").strip()
            if name:
                loaded.extend(await self._ensure_server_tools_loaded(name))
        return loaded

    async def load_all_tool_declarations(self) -> List[Dict[str, Any]]:
        await self.load_server_tools([name for name, client in self.clients.items() if client])
        return self.get_tool_declarations()

    async def _ensure_server_tools_loaded(self, server_name: str) -> List[Dict[str, Any]]:
        name = str(server_name or "").strip()
        if not name:
            return []
        if name in self._loaded_servers:
            return self._loaded_declarations_for_server(name)
        client = self.clients.get(name)
        if client is None:
            return []
        declarations = await client.list_tools()
        allow_tools = self._server_allow_tools(name)
        deny_tools = self._server_deny_tools(name)
        filtered: List[Dict[str, Any]] = []
        for declaration in declarations:
            tool_name = str(declaration.get("name", "")).strip()
            if not tool_name:
                continue
            if allow_tools and tool_name not in allow_tools:
                continue
            if tool_name in deny_tools:
                continue
            filtered.append(declaration)
        namespaced_declarations: List[Dict[str, Any]] = []
        for declaration in filtered:
            original_name = declaration.get("name", "")
            if not original_name:
                continue
            namespaced = f"{name}:{original_name}" if self.namespace_tools else original_name
            namespaced_decl = {**declaration, "name": namespaced}
            self._tool_to_client[namespaced] = client
            self._tool_name_map[namespaced] = original_name
            self._tool_declarations[namespaced] = namespaced_decl
            self._declarations = [decl for decl in self._declarations if decl.get("name") != namespaced]
            self._declarations.append(namespaced_decl)
            namespaced_declarations.append(namespaced_decl)
        self._server_declarations[name] = namespaced_declarations
        self._loaded_servers.add(name)
        self._server_status[name]["toolCount"] = len(declarations)
        self._server_status[name]["tools"] = [decl.get("name", "") for decl in declarations if decl.get("name")]
        self._server_status[name]["registeredTools"] = [decl.get("name", "") for decl in filtered if decl.get("name")]
        self._server_status[name]["schemasLoaded"] = True
        return list(namespaced_declarations)

    async def ensure_tool_available(self, name: str) -> bool:
        tool_name = str(name or "").strip()
        if not tool_name:
            return False
        if tool_name in self._tool_to_client:
            return True
        if self.namespace_tools and ":" in tool_name:
            server_name = tool_name.split(":", 1)[0].strip()
            await self._ensure_server_tools_loaded(server_name)
            return tool_name in self._tool_to_client
        for server_name in self.clients:
            await self._ensure_server_tools_loaded(server_name)
            if tool_name in self._tool_to_client:
                return True
        return False

    async def health_check_all(self) -> Dict[str, bool]:
        pairs = await asyncio.gather(*(self._health_pair(name, client) for name, client in self.clients.items()))
        return dict(pairs)

    async def _health_pair(self, name: str, client: Any) -> tuple[str, bool]:
        try:
            return name, bool(await client.health_check())
        except Exception:
            return name, False

    def get_healthy_tool_declarations(self) -> List[Dict[str, Any]]:
        return list(self._declarations)

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        return list(self._declarations)

    def get_all_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self._resources)

    def get_all_prompts(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self._prompts)

    def get_output_filter_stats(self) -> Dict[str, int]:
        return dict(self._output_filter_stats)

    def status(self) -> Dict[str, Any]:
        return {
            "configuredServers": len(self.servers_config),
            "connectedServers": len(self.clients),
            "toolCount": len(self._declarations),
            "resourceCount": sum(len(resources) for resources in self._resources.values()),
            "promptCount": sum(len(prompts) for prompts in self._prompts.values()),
            "namespacingEnabled": self.namespace_tools,
            "registryAutodiscover": self.registry.enabled,
            "servers": self._server_status,
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._tool_to_client:
            await self.ensure_tool_available(name)
        client = self._tool_to_client.get(name)
        if not client:
            raise RuntimeError(f"MCP tool not found: {name}")
        original_name = self._tool_name_map.get(name, name)
        declaration = self._tool_declarations.get(name)
        request = self._output_filter.prepare_call(name, arguments, declaration)
        raw_result = await client.call_tool_raw(name=original_name, arguments=request.arguments)
        rendered = _render_mcp_result(raw_result)
        filtered = self._output_filter.filter(
            name,
            raw_result,
            projection=request.projection,
            max_tokens=request.max_tokens,
            original_text=rendered,
            explicit_projection=request.explicit_projection,
        )
        if filtered.applied:
            self._output_filter_stats["filtered_calls"] += 1
            if filtered.auto_filtered:
                self._output_filter_stats["auto_filtered_calls"] += 1
            if filtered.projection:
                self._output_filter_stats["projection_filtered_calls"] += 1
            self._output_filter_stats["tokens_saved"] += max(0, int(filtered.tokens_saved or 0))
            return filtered.output
        return rendered

    async def registry_search(self, query: str = "", limit: int = 20) -> Dict[str, Any]:
        return await self.registry.search(query=query, limit=limit)

    async def shutdown(self) -> None:
        for client in self.clients.values():
            try:
                await client.disconnect()
            except Exception as exc:
                logger.debug("MCP disconnect failed: %s", exc)
        for server_name in self._server_status:
            self._server_status[server_name]["connected"] = False
        self.clients.clear()
        self._tool_to_client.clear()
        self._tool_declarations.clear()
        self._server_declarations.clear()
        self._declarations.clear()
        self._loaded_servers.clear()


MCPManager = MultiMcp
