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


def test_case_demo_cli_runs_http_lifecycle(tmp_path: Path, capsys) -> None:
    out = tmp_path / "case-demo.json"
    rc = cli.main(
        [
            "case",
            "demo",
            "--fixture",
            "corpus/library/3.json",
            "--pinned",
            "demo_3room_remove_wall_28",
            "--proposals-dir",
            "tests/fixtures/proposals",
            "--vendor-cache-dir",
            "tests/fixtures/vendors",
            "--handoff-root",
            str(tmp_path / "handoffs"),
            "--max-revise-attempts",
            "1",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    stdout = capsys.readouterr().out
    assert "create: status=designing" in stdout
    assert "compliance#2: status=awaiting_human_approval" in stdout
    assert "approval: status=approved" in stdout
    assert "handoff: status=handoff_complete" in stdout
    assert out.exists()
    case = json.loads(out.read_text(encoding="utf-8"))
    assert case["design_status"] == "handoff_complete"
    assert case["_baseline_items"]
    assert case["vendor_handoff"]["packet_uri"]
