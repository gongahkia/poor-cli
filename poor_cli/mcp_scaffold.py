"""MCP server scaffolding — generate minimal MCP server templates."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

_PYTHON_TEMPLATE = '''"""MCP server: {name}"""
import json
import sys

def handle_request(request):
    method = request.get("method", "")
    req_id = request.get("id")
    if method == "initialize":
        return {{"jsonrpc": "2.0", "id": req_id, "result": {{"protocolVersion": "2025-06-18", "capabilities": {{"tools": {{}}}}, "serverInfo": {{"name": "{name}", "version": "0.1.0"}}}}}}
    if method == "tools/list":
        return {{"jsonrpc": "2.0", "id": req_id, "result": {{"tools": [
            {{"name": "hello", "description": "Say hello", "inputSchema": {{"type": "object", "properties": {{"name": {{"type": "string", "description": "Name to greet"}}}}, "required": ["name"]}}}}
        ]}}}}
    if method == "tools/call":
        name = request.get("params", {{}}).get("name", "")
        args = request.get("params", {{}}).get("arguments", {{}})
        if name == "hello":
            return {{"jsonrpc": "2.0", "id": req_id, "result": {{"content": [{{"type": "text", "text": f"Hello, {{args.get('name', 'world')}}!"}}]}}}}
        return {{"jsonrpc": "2.0", "id": req_id, "error": {{"code": -32601, "message": f"Unknown tool: {{name}}"}}}}
    return {{"jsonrpc": "2.0", "id": req_id, "error": {{"code": -32601, "message": f"Unknown method: {{method}}"}}}}

if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        response = handle_request(request)
        sys.stdout.write(json.dumps(response) + "\\n")
        sys.stdout.flush()
'''

_NODE_TEMPLATE = '''// MCP server: {name}
const readline = require("readline");

const tools = [
  {{
    name: "hello",
    description: "Say hello",
    inputSchema: {{ type: "object", properties: {{ name: {{ type: "string", description: "Name to greet" }} }}, required: ["name"] }},
  }},
];

function handleRequest(request) {{
  const {{ method, id, params }} = request;
  if (method === "initialize") {{
    return {{ jsonrpc: "2.0", id, result: {{ protocolVersion: "2025-06-18", capabilities: {{ tools: {{}} }}, serverInfo: {{ name: "{name}", version: "0.1.0" }} }} }};
  }}
  if (method === "tools/list") {{
    return {{ jsonrpc: "2.0", id, result: {{ tools }} }};
  }}
  if (method === "tools/call") {{
    const toolName = params?.name;
    const args = params?.arguments || {{}};
    if (toolName === "hello") {{
      return {{ jsonrpc: "2.0", id, result: {{ content: [{{ type: "text", text: `Hello, ${{args.name || "world"}}!` }}] }} }};
    }}
    return {{ jsonrpc: "2.0", id, error: {{ code: -32601, message: `Unknown tool: ${{toolName}}` }} }};
  }}
  return {{ jsonrpc: "2.0", id, error: {{ code: -32601, message: `Unknown method: ${{method}}` }} }};
}}

const rl = readline.createInterface({{ input: process.stdin }});
rl.on("line", (line) => {{
  const request = JSON.parse(line.trim());
  const response = handleRequest(request);
  process.stdout.write(JSON.stringify(response) + "\\n");
}});
'''

_README_TEMPLATE = '''# {name}

MCP server scaffolded by poor-cli.

## Usage

Add to `.poor-cli/mcp.json`:

```json
{{
  "multi": true,
  "registry_autodiscover": false,
  "servers": [
    {{"name": "{name}", "transport": "stdio", "command": {command_json}, "enabled": true}}
  ]
}}
```

## Tools

- `hello` — Say hello (example tool, replace with your own)

## Protocol

Communicates via JSON-RPC 2.0 over stdin/stdout (MCP protocol version 2025-06-18).
'''


def scaffold_mcp_server(
    name: str,
    language: str = "python",
    output_dir: Optional[str] = None,
) -> str:
    """Generate a minimal MCP server from template. Returns path to generated server."""
    lang = language.lower()
    if lang not in ("python", "node", "javascript", "js"):
        return f"error: unsupported language '{language}'; use 'python' or 'node'"
    is_python = lang == "python"
    base_dir = Path(output_dir or os.getcwd()) / "mcp_servers" / name
    base_dir.mkdir(parents=True, exist_ok=True)
    if is_python:
        server_file = base_dir / "server.py"
        server_file.write_text(_PYTHON_TEMPLATE.format(name=name), encoding="utf-8")
        command = f"python {server_file}"
        command_json = f'["python", "{server_file}"]'
    else:
        server_file = base_dir / "server.js"
        server_file.write_text(_NODE_TEMPLATE.format(name=name), encoding="utf-8")
        command = f"node {server_file}"
        command_json = f'["node", "{server_file}"]'
    readme = base_dir / "README.md"
    readme.write_text(_README_TEMPLATE.format(name=name, command=command, command_json=command_json), encoding="utf-8")
    logger.info("scaffolded MCP server: %s (%s)", name, lang)
    return f"MCP server '{name}' created at {base_dir}\n\nFiles:\n  {server_file}\n  {readme}\n\nAdd to .poor-cli/mcp.json:\n  {{\"name\": \"{name}\", \"transport\": \"stdio\", \"command\": [\"{command.split()[0]}\", \"{server_file}\"], \"enabled\": true}}"
