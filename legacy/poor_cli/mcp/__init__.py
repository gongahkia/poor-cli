"""MCP client package."""

from .http import StreamableHttpTransport
from .multi_server import (
    MCPClient,
    MCPHTTPClient,
    MCPManager,
    MCP_CONFIG_FILENAME,
    MCP_CONFIG_PATHS,
    McpServerSpec,
    MultiMcp,
    _convert_tool_declarations,
    _render_mcp_result,
    discover_mcp_config,
    load_mcp_server_specs,
    normalize_mcp_config,
    specs_from_config,
)
from .registry import McpRegistryClient
from .config_store import McpConfigStore
from .stdio import McpTransport, StdioTransport

__all__ = [
    "MCPClient",
    "MCPHTTPClient",
    "MCPManager",
    "MCP_CONFIG_FILENAME",
    "MCP_CONFIG_PATHS",
    "McpRegistryClient",
    "McpConfigStore",
    "McpServerSpec",
    "McpTransport",
    "MultiMcp",
    "StdioTransport",
    "StreamableHttpTransport",
    "_convert_tool_declarations",
    "_render_mcp_result",
    "discover_mcp_config",
    "load_mcp_server_specs",
    "normalize_mcp_config",
    "specs_from_config",
]
