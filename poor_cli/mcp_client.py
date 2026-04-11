"""
MCP (Model Context Protocol) client/manager integration.

Supports:
- Stdio transport (subprocess with JSON-RPC over stdin/stdout)
- SSE transport (HTTP Server-Sent Events)
- Tool namespacing (server_name:tool_name)
- Config discovery from .poor-cli/mcp.json
- Resource and prompt protocol stubs
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger
from .tool_output_filter import ToolOutputFilter, empty_filter_stats

logger = setup_logger(__name__)

MCP_CONFIG_FILENAME = "mcp.json"
MCP_CONFIG_PATHS = [
    ".poor-cli/mcp.json",
    ".claude/mcp.json",
]


def discover_mcp_config(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Discover MCP server config from repo-local or user-global paths."""
    root = (repo_root or Path.cwd()).resolve()
    candidates = [root / p for p in MCP_CONFIG_PATHS]
    candidates.append(Path.home() / ".poor-cli" / MCP_CONFIG_FILENAME)
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    logger.info("discovered MCP config at %s", path)
                    return data.get("mcpServers", data.get("servers", data))
            except Exception as e:
                logger.warning("failed to parse MCP config %s: %s", path, e)
    return {}


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


class MCPClient:
    """Single MCP server client process."""

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process: Optional[asyncio.subprocess.Process] = None
        self.capabilities: Dict[str, Any] = {}
        self._next_request_id = 3
        self._tools: List[Dict[str, Any]] = []

    async def _send(self, payload: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process is not connected")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def _read_response(self) -> Dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise RuntimeError("MCP process is not connected")
        raw = await self.process.stdout.readline()
        if not raw:
            raise RuntimeError("MCP server closed stream")
        return json.loads(raw.decode("utf-8", errors="replace"))

    async def connect(self) -> None:
        merged_env = dict(os.environ)
        merged_env.update(self.env)
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "poor-cli"},
            },
        }
        await self._send(init_payload)
        response = await self._read_response()
        self.capabilities = response.get("result", {}).get("capabilities", {})

    async def list_tools(self) -> List[Dict[str, Any]]:
        await self._send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        response = await self._read_response()
        tools = response.get("result", {}).get("tools", [])
        declarations = _convert_tool_declarations(tools)
        self._tools = declarations
        return declarations

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources (MCP resources protocol)."""
        await self._send({"jsonrpc": "2.0", "id": self._next_request_id, "method": "resources/list"})
        self._next_request_id += 1
        response = await self._read_response()
        return response.get("result", {}).get("resources", [])

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts (MCP prompts protocol)."""
        await self._send({"jsonrpc": "2.0", "id": self._next_request_id, "method": "prompts/list"})
        self._next_request_id += 1
        response = await self._read_response()
        return response.get("result", {}).get("prompts", [])

    async def call_tool_raw(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        await self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        response = await self._read_response()
        return response.get("result", {})

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        result = await self.call_tool_raw(name=name, arguments=arguments)
        return _render_mcp_result(result)

    async def health_check(self) -> bool:
        """Ping the MCP server process to check if it's still alive."""
        if self.process is None or self.process.returncode is not None:
            return False
        try:
            await self._send({
                "jsonrpc": "2.0",
                "id": self._next_request_id,
                "method": "ping",
            })
            self._next_request_id += 1
            await asyncio.wait_for(self._read_response(), timeout=3)
            return True
        except Exception:
            return self.process.returncode is None # fallback: process alive check

    async def disconnect(self) -> None:
        if not self.process:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        self.process = None


class MCPSSEClient:
    """MCP client using HTTP SSE transport."""

    def __init__(self, name: str, url: str, headers: Optional[Dict[str, str]] = None):
        self.name = name
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.capabilities: Dict[str, Any] = {}
        self._tools: List[Dict[str, Any]] = []
        self._session_id: Optional[str] = None

    async def connect(self) -> None:
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError("aiohttp required for SSE transport: pip install aiohttp")
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "poor-cli"},
                },
            }
            async with session.post(
                f"{self.url}/message", json=payload, headers=self.headers,
            ) as resp:
                data = await resp.json()
                self.capabilities = data.get("result", {}).get("capabilities", {})
                self._session_id = resp.headers.get("Mcp-Session-Id")

    async def list_tools(self) -> List[Dict[str, Any]]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            headers = {**self.headers}
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id
            async with session.post(
                f"{self.url}/message", json=payload, headers=headers,
            ) as resp:
                data = await resp.json()
                tools = data.get("result", {}).get("tools", [])
        declarations = _convert_tool_declarations(tools)
        self._tools = declarations
        return declarations

    async def call_tool_raw(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0", "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
            headers = {**self.headers}
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id
            async with session.post(
                f"{self.url}/message", json=payload, headers=headers,
            ) as resp:
                data = await resp.json()
                return data.get("result", {})

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        result = await self.call_tool_raw(name=name, arguments=arguments)
        return _render_mcp_result(result)

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources (MCP resources protocol)."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {"jsonrpc": "2.0", "id": 4, "method": "resources/list"}
            headers = {**self.headers}
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id
            async with session.post(
                f"{self.url}/message", json=payload, headers=headers,
            ) as resp:
                data = await resp.json()
                return data.get("result", {}).get("resources", [])

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts (MCP prompts protocol)."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {"jsonrpc": "2.0", "id": 5, "method": "prompts/list"}
            headers = {**self.headers}
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id
            async with session.post(
                f"{self.url}/message", json=payload, headers=headers,
            ) as resp:
                data = await resp.json()
                return data.get("result", {}).get("prompts", [])

    async def health_check(self) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/health", headers=self.headers, timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def disconnect(self) -> None:
        pass # SSE clients are stateless per-request; nothing to clean up


def _convert_tool_declarations(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert MCP tool schemas to Gemini-compatible declarations."""
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
            "name": name, "description": description,
            "parameters": {"type": "OBJECT", "properties": decl_props, "required": required},
        })
    return declarations


class MCPManager:
    """Manage multiple MCP server clients (stdio + SSE) and tool routing."""

    def __init__(
        self,
        servers_config: Dict[str, Any],
        *,
        namespace_tools: bool = True,
        repo_root: Optional[Path] = None,
    ):
        self.servers_config = servers_config
        self.namespace_tools = namespace_tools
        self.clients: Dict[str, Any] = {} # MCPClient | MCPSSEClient
        self._declarations: List[Dict[str, Any]] = []
        self._tool_to_client: Dict[str, Any] = {} # namespaced_name -> client
        self._tool_name_map: Dict[str, str] = {} # namespaced_name -> original_name
        self._tool_declarations: Dict[str, Dict[str, Any]] = {}
        self._server_declarations: Dict[str, List[Dict[str, Any]]] = {}
        self._loaded_servers: set[str] = set()
        self._server_status: Dict[str, Dict[str, Any]] = {}
        self._resources: Dict[str, List[Dict[str, Any]]] = {} # server -> resources
        self._prompts: Dict[str, List[Dict[str, Any]]] = {} # server -> prompts
        self._output_filter = ToolOutputFilter(repo_root=repo_root or Path.cwd())
        self._output_filter_stats = empty_filter_stats()

    async def initialize(self) -> None:
        for server_name, cfg in self.servers_config.items():
            enabled = bool(cfg.get("enabled", True))
            transport = str(cfg.get("transport", "stdio")).lower()
            self._server_status[server_name] = {
                "configured": True, "enabled": enabled, "connected": False,
                "transport": transport, "toolCount": 0, "tools": [],
                "registeredTools": [], "resources": [], "prompts": [],
                "schemasLoaded": False,
                "error": None, "command": cfg.get("command", cfg.get("url", "")),
                "args": cfg.get("args", []),
            }
            if not enabled:
                self._server_status[server_name]["error"] = "disabled by config"
                continue
            try:
                client = self._create_client(server_name, cfg, transport)
                await client.connect()
                self.clients[server_name] = client
                self._server_status[server_name]["connected"] = True
                # discover resources and prompts (best-effort)
                try:
                    self._resources[server_name] = await client.list_resources()
                    self._server_status[server_name]["resources"] = [
                        r.get("uri", r.get("name", "")) for r in self._resources[server_name]
                    ]
                except Exception:
                    self._resources[server_name] = []
                try:
                    self._prompts[server_name] = await client.list_prompts()
                    self._server_status[server_name]["prompts"] = [
                        p.get("name", "") for p in self._prompts[server_name]
                    ]
                except Exception:
                    self._prompts[server_name] = []
            except Exception as e:
                logger.warning("Failed to initialize MCP server '%s': %s", server_name, e)
                self._server_status[server_name]["error"] = str(e)

    def get_server_names(self) -> List[str]:
        return [server_name for server_name in self.servers_config]

    def _server_allow_tools(self, server_name: str) -> set[str]:
        cfg = self.servers_config.get(server_name, {})
        return {
            str(tool_name).strip()
            for tool_name in cfg.get("allow_tools", []) or []
            if str(tool_name).strip()
        }

    def _server_deny_tools(self, server_name: str) -> set[str]:
        cfg = self.servers_config.get(server_name, {})
        return {
            str(tool_name).strip()
            for tool_name in cfg.get("deny_tools", []) or []
            if str(tool_name).strip()
        }

    def _loaded_declarations_for_server(self, server_name: str) -> List[Dict[str, Any]]:
        return list(self._server_declarations.get(server_name, []))

    async def load_server_tools(self, server_names: List[str]) -> List[Dict[str, Any]]:
        loaded: List[Dict[str, Any]] = []
        for server_name in server_names:
            name = str(server_name or "").strip()
            if not name:
                continue
            loaded.extend(await self._ensure_server_tools_loaded(name))
        return loaded

    async def load_all_tool_declarations(self) -> List[Dict[str, Any]]:
        server_names = [name for name, client in self.clients.items() if client]
        await self.load_server_tools(server_names)
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

    @staticmethod
    def _create_client(server_name: str, cfg: Dict[str, Any], transport: str) -> Any:
        """Create an MCP client based on transport type."""
        if transport == "sse":
            url = cfg.get("url")
            if not url:
                raise ValueError(f"MCP SSE server '{server_name}' missing url")
            return MCPSSEClient(name=server_name, url=url, headers=cfg.get("headers", {}))
        # default: stdio
        command = cfg.get("command")
        if not command:
            raise ValueError(f"MCP stdio server '{server_name}' missing command")
        return MCPClient(
            name=server_name, command=command,
            args=cfg.get("args", []), env=cfg.get("env", {}),
        )

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all registered MCP servers. Returns {name: alive}."""
        results: Dict[str, bool] = {}
        for name, client in self.clients.items():
            results[name] = await client.health_check()
        return results

    def get_healthy_tool_declarations(self) -> List[Dict[str, Any]]:
        """Return tool declarations only from healthy servers."""
        healthy: List[Dict[str, Any]] = []
        for decl in self._declarations:
            tool_name = decl.get("name", "")
            client = self._tool_to_client.get(tool_name)
            if not client:
                continue
            if isinstance(client, MCPSSEClient):
                healthy.append(decl) # SSE clients are stateless, assume healthy
            elif hasattr(client, "process") and client.process is not None and client.process.returncode is None:
                healthy.append(decl)
        return healthy

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        return list(self._declarations)

    def get_all_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return discovered resources grouped by server."""
        return dict(self._resources)

    def get_all_prompts(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return discovered prompts grouped by server."""
        return dict(self._prompts)

    def get_output_filter_stats(self) -> Dict[str, int]:
        return dict(self._output_filter_stats)

    def status(self) -> Dict[str, Any]:
        return {
            "configuredServers": len(self.servers_config),
            "connectedServers": len(self.clients),
            "toolCount": len(self._declarations),
            "resourceCount": sum(len(r) for r in self._resources.values()),
            "promptCount": sum(len(p) for p in self._prompts.values()),
            "namespacingEnabled": self.namespace_tools,
            "servers": self._server_status,
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._tool_to_client:
            await self.ensure_tool_available(name)
        client = self._tool_to_client.get(name)
        if not client:
            raise RuntimeError(f"MCP tool not found: {name}")
        original_name = self._tool_name_map.get(name, name) # resolve namespace
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

    async def shutdown(self) -> None:
        for client in self.clients.values():
            try:
                await client.disconnect()
            except Exception as e:
                logger.debug(f"MCP disconnect failed: {e}")
        for server_name in self._server_status:
            self._server_status[server_name]["connected"] = False
        self.clients.clear()
        self._tool_to_client.clear()
        self._tool_declarations.clear()
        self._server_declarations.clear()
        self._declarations.clear()
        self._loaded_servers.clear()
