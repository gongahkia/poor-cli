from __future__ import annotations

import json
import importlib
from pathlib import Path

import haus.cli as cli
import haus.mcp_server as mcp_server


def test_resolve_view_environment_uses_packaged_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("HAUS_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setattr(cli, "_source_project_root", lambda: tmp_path / "not-a-checkout")

    env = cli._resolve_view_environment()

    assert env.serve_root == runtime_root
    assert env.viewer_dir == runtime_root / "viewer"
    assert not env.source_checkout
    assert (env.viewer_dir / "editor.html").exists()
    assert (env.viewer_dir / "js" / "main.js").exists()
    assert (runtime_root / "corpus" / "library" / "1.json").exists()
    assert json.loads((env.viewer_dir / "mcp-layout.json").read_text(encoding="utf-8")) == {
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
