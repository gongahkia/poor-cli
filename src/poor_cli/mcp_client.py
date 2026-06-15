from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import RunStore
from .tools import ToolDispatcher
from .tools.dispatcher import load_tool_schemas

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_CONFIG_PATHS = (".poor-cli/mcp.json", ".claude/mcp.json")
DEFAULT_EXPOSED_TOOLS = {"read_file", "glob", "grep", "replay_emit", "review", "web_search", "web_fetch"}


class McpError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpServerSpec:
    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    allow_tools: tuple[str, ...] = ()
    timeout_seconds: int = 30


class MCPClient:
    def __init__(self, spec: McpServerSpec):
        if not spec.command:
            raise McpError(f"MCP server {spec.name} missing command")
        self.spec = spec
        self.process: asyncio.subprocess.Process | None = None
        self._next_id = 2

    async def connect(self) -> None:
        env = dict(os.environ)
        env.update(self.spec.env)
        self.process = await asyncio.create_subprocess_exec(
            *self.spec.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "poor-cli"},
            },
            request_id=1,
        )

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list")
        tools = result.get("tools", [])
        rows = tools if isinstance(tools, list) else []
        if not self.spec.allow_tools:
            return rows
        allowed = set(self.spec.allow_tools)
        return [tool for tool in rows if isinstance(tool, dict) and str(tool.get("name") or "") in allowed]

    async def call_tool_raw(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._request("tools/call", {"name": name, "arguments": arguments})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return _render_mcp_result(await self.call_tool_raw(name, arguments))

    async def disconnect(self) -> None:
        if self.process is None:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def _request(self, method: str, params: dict[str, Any] | None = None, request_id: int | None = None) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise McpError("MCP stdio process is not connected")
        rid = request_id if request_id is not None else self._next_id
        if request_id is None:
            self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await self.process.stdin.drain()
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise McpError(f"MCP server {self.spec.name} closed stdout")
            response = json.loads(line.decode(errors="replace"))
            if response.get("id") != rid:
                continue
            if "error" in response:
                error = response["error"]
                raise McpError(str(error.get("message") if isinstance(error, dict) else error))
            result = response.get("result", {})
            return result if isinstance(result, dict) else {"value": result}


def discover_mcp_config(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or Path.cwd()).resolve()
    for path in [*(root / item for item in MCP_CONFIG_PATHS), Path.home() / ".poor-cli" / "mcp.json"]:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    return {}


def load_mcp_server_specs(repo_root: Path | None = None) -> list[McpServerSpec]:
    return specs_from_config(discover_mcp_config(repo_root))


def specs_from_config(config: dict[str, Any]) -> list[McpServerSpec]:
    specs = []
    for name, raw in _server_items(config):
        if not isinstance(raw, dict):
            continue
        spec = _spec_from_mapping(name, raw)
        if spec.enabled:
            specs.append(spec)
    return specs


async def list_mcp_tools(repo_root: Path | None = None) -> list[dict[str, Any]]:
    rows = []
    for spec in load_mcp_server_specs(repo_root):
        client = MCPClient(spec)
        await client.connect()
        try:
            for tool in await client.list_tools():
                if not isinstance(tool, dict):
                    continue
                name = str(tool.get("name") or "")
                if name:
                    rows.append({"server": spec.name, **tool, "tool": name, "name": f"{spec.name}:{name}"})
        finally:
            await client.disconnect()
    return rows


async def call_mcp_tool(repo_root: Path | None, qualified_name: str, arguments: dict[str, Any]) -> str:
    server_name, _, tool_name = qualified_name.partition(":")
    if not server_name or not tool_name:
        raise McpError("MCP tool must be qualified as server:tool")
    specs = {spec.name: spec for spec in load_mcp_server_specs(repo_root)}
    if server_name not in specs:
        raise McpError(f"unknown MCP server: {server_name}")
    if specs[server_name].allow_tools and tool_name not in set(specs[server_name].allow_tools):
        raise McpError(f"MCP tool not allowlisted: {qualified_name}")
    client = MCPClient(specs[server_name])
    try:
        await client.connect()
        return await asyncio.wait_for(client.call_tool(tool_name, arguments), timeout=specs[server_name].timeout_seconds)
    except McpError as exc:
        raise McpError(_redact(str(exc), specs[server_name].env)) from exc
    finally:
        await client.disconnect()


def serve_mcp_stdio(root: Path, repo_root: Path | None = None) -> int:
    server = PoorMcpServer(root, repo_root or Path.cwd())
    try:
        for line in sys.stdin:
            server.handle(line)
    finally:
        server.close()
    return 0


class PoorMcpServer:
    def __init__(self, root: Path, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.store = RunStore(root)
        self.run_id = self.store.create_run(
            user_goal="mcp stdio tool server",
            repo_path=self.repo_root,
            git_commit_start=None,
            mode="mcp",
            budget={},
        )
        self.exposed = _exposed_tools(self.repo_root)

    def close(self) -> None:
        self.store.set_run_status(self.run_id, "completed", "mcp server closed")
        self.store.close()

    def handle(self, line: str) -> None:
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("request must be an object")
            req_id = req.get("id")
            method = str(req.get("method") or "")
            if method == "initialize":
                self._send(req_id, {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}}})
            elif method == "tools/list":
                self._send(req_id, {"tools": self._tools()})
            elif method == "tools/call":
                params = req.get("params")
                self._send(req_id, self._call_tool(params if isinstance(params, dict) else {}))
            else:
                self._send_error(req_id, -32601, f"method not found: {method}")
        except Exception as exc:
            self._send_error(None, -32603, _redact(f"{type(exc).__name__}: {exc}", {}))

    def _tools(self) -> list[dict[str, Any]]:
        schemas = load_tool_schemas(self.repo_root)
        return [
            {"name": name, "description": schema.description, "inputSchema": schema.parameters}
            for name, schema in sorted(schemas.items())
            if name in self.exposed
        ]

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if name not in self.exposed:
            return {"content": [{"type": "text", "text": f"tool not allowed: {name}"}], "isError": True}
        dispatcher = ToolDispatcher(self.store, self.run_id, workdir=self.repo_root)
        result = dispatcher.call(name, arguments)
        text = json.dumps({"ok": result.ok, "output": result.output, "error": result.error}, sort_keys=True)
        return {"content": [{"type": "text", "text": text}], "isError": not result.ok}

    def _send(self, req_id: Any, result: dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "id": req_id, "result": result}
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
        sys.stdout.flush()

    def _send_error(self, req_id: Any, code: int, message: str) -> None:
        payload = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
        sys.stdout.flush()


def _server_items(config: dict[str, Any]) -> list[tuple[str, Any]]:
    servers = config.get("servers")
    if isinstance(servers, list):
        return [(str(item.get("name") or ""), item) for item in servers if isinstance(item, dict) and item.get("name")]
    if isinstance(servers, dict):
        return [(str(name), raw) for name, raw in servers.items()]
    mcp_servers = config.get("mcpServers")
    if isinstance(mcp_servers, dict):
        return [(str(name), raw) for name, raw in mcp_servers.items()]
    return [(str(name), raw) for name, raw in config.items() if isinstance(raw, dict)]


def _spec_from_mapping(name: str, raw: dict[str, Any]) -> McpServerSpec:
    transport = str(raw.get("transport") or "stdio").lower()
    if transport != "stdio":
        raise McpError(f"unsupported MCP transport for {name}: {transport}")
    command = _command(raw)
    env_raw = raw.get("env")
    env = env_raw if isinstance(env_raw, dict) else {}
    return McpServerSpec(
        name=name,
        command=command,
        env={str(key): _expand_env(str(value)) for key, value in env.items()},
        enabled=bool(raw.get("enabled", True)),
        allow_tools=tuple(str(item) for item in raw.get("allow_tools") or []),
        timeout_seconds=max(1, int(raw.get("timeout_seconds") or 30)),
    )


def _command(raw: dict[str, Any]) -> list[str]:
    command = raw.get("command")
    args = raw.get("args")
    if isinstance(command, list):
        return [str(part) for part in command]
    if isinstance(command, str):
        return [command, *[str(arg) for arg in args]] if isinstance(args, list) else [command]
    return []


def _expand_env(value: str) -> str:
    return re.sub(r"\$\{([^}]+)\}", lambda match: os.environ.get(match.group(1), ""), value)


def _render_mcp_result(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        if parts:
            return "".join(parts)
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def _exposed_tools(repo_root: Path) -> set[str]:
    config = discover_mcp_config(repo_root)
    raw = config.get("expose_tools")
    exposed = {str(item) for item in raw} if isinstance(raw, list) else set(DEFAULT_EXPOSED_TOOLS)
    graph_names = {"find_symbol", "definition_of", "imports_of", "callers_of", "subgraph"}
    return exposed | {name for name in load_tool_schemas(repo_root) if name in graph_names}


def _redact(text: str, env: dict[str, str]) -> str:
    values = [value for value in env.values() if value]
    values.extend(value for key, value in os.environ.items() if any(part in key.upper() for part in ("TOKEN", "SECRET", "KEY")))
    out = text
    for value in sorted(set(values), key=len, reverse=True):
        if len(value) >= 4:
            out = out.replace(value, "[redacted]")
    return out
