from __future__ import annotations

import json
import importlib
from pathlib import Path

import haus.cli as cli
import haus.mcp_server as mcp_server


def test_resolve_view_environment_uses_packaged_web_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("HAUS_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setattr(cli, "_source_project_root", lambda: tmp_path / "not-a-checkout")

    env = cli._resolve_view_environment()

    assert env.static_dir == runtime_root / "web"
    assert env.layout_path == runtime_root / "viewer" / "mcp-layout.json"
    assert not env.source_checkout
    assert (env.static_dir / "index.html").exists()
    assert (runtime_root / "corpus" / "library" / "1.json").exists()
    assert json.loads(env.layout_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "items": [],
    }


def test_mcp_layout_path_can_come_from_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout_path = tmp_path / "custom-layout.json"
    monkeypatch.setenv("HAUS_LAYOUT_PATH", str(layout_path))

    reloaded = importlib.reload(mcp_server)
    assert reloaded.LAYOUT_PATH == layout_path


def test_cli_help_omits_retired_case_commands() -> None:
    help_text = cli._build_parser().format_help()
    assert "case-server" not in help_text
    assert "case demo" not in help_text
