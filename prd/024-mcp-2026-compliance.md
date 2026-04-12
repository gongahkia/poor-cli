# PRD 024: MCP 2026 compliance — streamable-HTTP, multi-server, registry

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** large (2w)
- **Blocks:** 035
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/mcp_client.py`
  - `poor_cli/mcp_scaffold.py`
- **New files it adds:**
  - `poor_cli/mcp/__init__.py`
  - `poor_cli/mcp/transport_stdio.py`
  - `poor_cli/mcp/transport_http.py`
  - `poor_cli/mcp/registry.py`
  - `poor_cli/mcp/multi_server.py`
  - `tests/test_mcp_transport.py`
  - `tests/test_mcp_multi_server.py`

## 1. Problem

`mcp_client.py` is ~200 lines, single-server, stdio-only. MCP 2026 spec deprecates SSE in favor of Streamable HTTP; supports an official server registry; multi-server is table-stakes. LEARNING.md §2.2 and §4 note this.

## 2. Current state

One MCP connection at a time, stdio transport, no registry knowledge.

## 3. Goal & non-goals

**Goal:**
- `poor_cli/mcp/` package with stdio and Streamable HTTP transports.
- Multi-server support with tool namespacing (`<server>:<tool>`).
- Discovery from `.poor-cli/mcp.json` (array of server specs).
- Optional pull from the official MCP registry (`https://registry.modelcontextprotocol.io/`), gated behind a config flag.

**Non-goals:**
- Do not implement SSE (deprecated).
- Do not ship a full MCP server of our own.
- Do not bundle registry pulls at startup (on-demand only).

## 4. Design

### 4.1 Transports

```python
class McpTransport(ABC):
    async def connect(self) -> None: ...
    async def send(self, msg: dict) -> None: ...
    async def recv(self) -> dict: ...
    async def close(self) -> None: ...

class StdioTransport(McpTransport): ...
class StreamableHttpTransport(McpTransport): ...
```

### 4.2 Multi-server

```python
@dataclass
class McpServerSpec:
    name: str
    transport: Literal["stdio","http"]
    command: list[str] | None   # for stdio
    url: str | None             # for http
    env: dict[str, str] | None
    enabled: bool

class MultiMcp:
    async def start_all(self, specs: list[McpServerSpec]) -> None: ...
    async def tools(self) -> list[dict]:
        """All tools from all servers, namespaced as '<server>:<tool>'."""
    async def call_tool(self, namespaced_name: str, args: dict) -> Any: ...
    async def health(self) -> dict[str, bool]: ...
```

### 4.3 Config file

`.poor-cli/mcp.json`:

```json
{
  "servers": [
    {"name": "github", "transport": "stdio", "command": ["npx", "-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}, "enabled": true},
    {"name": "fs",     "transport": "stdio", "command": ["mcp-fs"], "enabled": true}
  ],
  "registry_autodiscover": false
}
```

### 4.4 Tool-name conflicts

Namespacing prevents conflicts. Agent sees `github:create_issue`, `fs:read_file`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Extract current `mcp_client.py` into `mcp/transport_stdio.py`.
2. Implement `transport_http.py` per MCP 2026 Streamable HTTP.
3. Implement `multi_server.py` with health checks.
4. Config loader.
5. Namespacing in tool listing.
6. Registry client (optional, lazy).
7. Tests with mock transports.
8. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_stdio_transport_roundtrip`
- `test_http_transport_roundtrip_with_mocked_server`
- `test_multi_server_aggregates_tools_with_namespace`
- `test_health_reports_per_server`

**Done criterion**
- [ ] Both transports work.
- [ ] Multi-server loads from config.
- [ ] Namespacing prevents conflicts.

## 8. Rollback / risk

Medium. Legacy single-server code preserved behind a `multi: false` flag for the first release.

## 9. Out-of-scope & boundary

- 🚫 Do not implement SSE.
- 🚫 Do not ship our own MCP server.

## 10. Related PRDs & references

- PRD 035 (MCP Registry browser UI).
- MCP spec: https://modelcontextprotocol.io/
- Official registry: https://registry.modelcontextprotocol.io/
- LEARNING.md §2.2, §4.
