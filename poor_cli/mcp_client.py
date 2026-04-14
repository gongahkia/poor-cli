"""Compatibility shim for MCP integration."""

from .mcp import (
    MCPClient,
    MCPHTTPClient,
    MCPManager,
    MCP_CONFIG_FILENAME,
    MCP_CONFIG_PATHS,
    McpRegistryClient,
    McpServerSpec,
    MultiMcp,
    StreamableHttpTransport,
    _convert_tool_declarations,
    _render_mcp_result,
    discover_mcp_config,
    load_mcp_server_specs,
    normalize_mcp_config,
    specs_from_config,
)

MCPSSEClient = MCPHTTPClient

__all__ = [
    "MCPClient",
    "MCPHTTPClient",
    "MCPManager",
    "MCP_CONFIG_FILENAME",
    "MCP_CONFIG_PATHS",
    "MCPSSEClient",
    "McpRegistryClient",
    "McpServerSpec",
    "MultiMcp",
    "StreamableHttpTransport",
    "_convert_tool_declarations",
    "_render_mcp_result",
    "discover_mcp_config",
    "load_mcp_server_specs",
    "normalize_mcp_config",
    "specs_from_config",
]
