from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

from poor_cli.cli import main
from poor_cli.mcp_client import call_mcp_tool, list_mcp_tools, specs_from_config


def test_mcp_stdio_list_and_call(tmp_path: Path) -> None:
    server = _write_stdio_server(tmp_path)
    _write_config(tmp_path, server)

    tools = asyncio.run(list_mcp_tools(tmp_path))
    result = asyncio.run(call_mcp_tool(tmp_path, "stdio:echo", {"text": "ok"}))

    assert tools[0]["name"] == "stdio:echo"
    assert result == "stdio:ok"


def test_mcp_config_accepts_claude_shape() -> None:
    specs = specs_from_config({"mcpServers": {"echo": {"command": "python", "args": ["server.py"], "env": {"TOKEN": "${HOME}"}}}})

    assert specs[0].name == "echo"
    assert specs[0].command == ["python", "server.py"]
    assert specs[0].env["TOKEN"]


def test_cli_mcp_list_and_call(tmp_path: Path, monkeypatch, capsys) -> None:
    server = _write_stdio_server(tmp_path)
    _write_config(tmp_path, server)
    monkeypatch.chdir(tmp_path)

    assert main(["mcp", "list"]) == 0
    assert "stdio:echo" in capsys.readouterr().out

    assert main(["mcp", "call", "stdio:echo", "--args", '{"text":"cli"}']) == 0
    assert capsys.readouterr().out.strip() == "stdio:cli"


def _write_config(root: Path, server: Path) -> None:
    path = root / ".poor-cli" / "mcp.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps({"servers": [{"name": "stdio", "transport": "stdio", "command": [sys.executable, str(server)], "enabled": True}]}),
        encoding="utf-8",
    )


def _write_stdio_server(root: Path) -> Path:
    path = root / "mcp_server.py"
    path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            tools = [{"name": "echo", "description": "echo", "inputSchema": {"type": "object"}}]

            for line in sys.stdin:
                request = json.loads(line)
                method = request.get("method")
                req_id = request.get("id")
                if method == "initialize":
                    result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "stdio"}}
                elif method == "tools/list":
                    result = {"tools": tools}
                elif method == "tools/call":
                    text = request.get("params", {}).get("arguments", {}).get("text", "")
                    result = {"content": [{"type": "text", "text": f"stdio:{text}"}]}
                else:
                    result = {}
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\\n")
                sys.stdout.flush()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path
