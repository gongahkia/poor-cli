from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

from poor_cli.cli import main
from poor_cli.mcp_client import PoorMcpServer, call_mcp_tool, list_mcp_tools, specs_from_config


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


def test_mcp_config_allowlist_and_timeout() -> None:
    specs = specs_from_config({"servers": {"echo": {"command": "python", "allow_tools": ["echo"], "timeout_seconds": 2}}})

    assert specs[0].allow_tools == ("echo",)
    assert specs[0].timeout_seconds == 2


def test_cli_mcp_list_and_call(tmp_path: Path, monkeypatch, capsys) -> None:
    server = _write_stdio_server(tmp_path)
    _write_config(tmp_path, server)
    monkeypatch.chdir(tmp_path)

    assert main(["mcp", "list"]) == 0
    assert "stdio:echo" in capsys.readouterr().out

    assert main(["mcp", "call", "stdio:echo", "--args", '{"text":"cli"}']) == 0
    assert capsys.readouterr().out.strip() == "stdio:cli"


def test_poor_mcp_server_exposes_safe_builtin_tools(tmp_path: Path, capsys) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    server = PoorMcpServer(tmp_path / "store", tmp_path)

    try:
        server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
        server.handle(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        server.handle(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "read_file", "arguments": {"path": "note.txt"}},
                }
            )
        )
        server.handle(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "write_file", "arguments": {"path": "x", "content": "bad"}},
                }
            )
        )
    finally:
        server.close()

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    listed = {tool["name"] for tool in lines[1]["result"]["tools"]}
    assert "read_file" in listed
    assert "write_file" not in listed
    assert json.loads(lines[2]["result"]["content"][0]["text"])["output"]["content"] == "hello"
    assert lines[3]["result"]["isError"] is True


def test_mcp_client_redacts_server_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_TOKEN", "secret-value")
    server = tmp_path / "bad_server.py"
    server.write_text(
        "import json, os, sys\n"
        "for line in sys.stdin:\n"
        " req=json.loads(line); sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':req.get('id'),"
        "'error':{'code':1,'message':os.environ['SECRET_TOKEN']}})+'\\n'); sys.stdout.flush()\n",
        encoding="utf-8",
    )
    (tmp_path / ".poor-cli").mkdir()
    (tmp_path / ".poor-cli" / "mcp.json").write_text(
        json.dumps({"servers": {"bad": {"command": [sys.executable, str(server)], "env": {"SECRET_TOKEN": "${SECRET_TOKEN}"}}}}),
        encoding="utf-8",
    )

    try:
        asyncio.run(call_mcp_tool(tmp_path, "bad:echo", {}))
    except Exception as exc:
        assert "secret-value" not in str(exc)
        assert "[redacted]" in str(exc)
    else:
        raise AssertionError("expected MCP error")


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
