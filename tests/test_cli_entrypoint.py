import sys
from pathlib import Path

import pytest

from poor_cli import __main__ as cli_main


def test_root_help_does_not_launch_tui(monkeypatch, capsys):
    def _fail(argv):
        raise AssertionError(f"TUI launcher should not run for help: {argv}")

    monkeypatch.setattr(cli_main, "_launch_tui", _fail)
    monkeypatch.setattr(sys, "argv", ["poor-cli", "--help"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "usage: poor-cli [subcommand] [options]" in output
    assert "poor-cli exec" in output
    assert "poor-cli server" in output
    assert "poor-cli install-info" in output


def test_root_version_does_not_launch_tui(monkeypatch, capsys):
    def _fail(argv):
        raise AssertionError(f"TUI launcher should not run for version: {argv}")

    monkeypatch.setattr(cli_main, "_launch_tui", _fail)
    monkeypatch.setattr(sys, "argv", ["poor-cli", "--version"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == cli_main.__version__


def test_server_alias_routes_to_server_main(monkeypatch):
    captured = {}

    def _fake_run_server_mode(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(cli_main, "_run_server_mode", _fake_run_server_mode)
    monkeypatch.setattr(sys, "argv", ["poor-cli", "server", "--stdio"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    assert captured["argv"] == ["--stdio"]


def test_launch_tui_error_mentions_headless_surfaces(monkeypatch):
    monkeypatch.setattr(cli_main, "_run_tui_binary", lambda argv: 1)
    monkeypatch.setattr(cli_main, "_run_tui_from_repo", lambda argv: 1)

    with pytest.raises(SystemExit) as exc:
        cli_main._launch_tui([])

    message = str(exc.value)
    assert "poor-cli exec --help" in message
    assert "poor-cli server --help" in message
    assert "poor-cli help" in message
    assert "poor-cli install-info" in message


def test_resolve_tui_binary_prefers_env_override(monkeypatch, tmp_path: Path):
    env_binary = tmp_path / cli_main._tui_executable_name()
    env_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    env_binary.chmod(0o755)

    monkeypatch.setenv("POOR_CLI_TUI_BIN", str(env_binary))
    monkeypatch.setattr(cli_main, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_resolve_packaged_tui_binary", lambda: None)
    monkeypatch.setattr(cli_main, "_resolve_path_tui_binary", lambda: None)

    resolved, source = cli_main._resolve_tui_binary()

    assert resolved == env_binary.resolve()
    assert source == "env"


def test_install_info_json_reports_selected_launcher(monkeypatch, capsys):
    selected_path = Path("/tmp/poor-cli-tui")
    monkeypatch.setattr(
        cli_main,
        "_inspect_tui_installation",
        lambda: {
            "version": cli_main.__version__,
            "platform": "darwin",
            "machine": "arm64",
            "tuiExecutableName": "poor-cli-tui",
            "selectedLauncher": {"source": "package", "path": str(selected_path)},
            "envOverride": {"configured": False, "path": None, "usable": False},
            "repoBinary": {"path": "/repo/bin", "exists": False, "usable": False, "fresh": False},
            "packagedCandidates": [{"path": str(selected_path), "exists": True, "usable": True}],
            "pathBinary": {"path": None, "usable": False},
            "repoLauncherScript": {"path": "/repo/run_tui.sh", "exists": False},
        },
    )
    monkeypatch.setattr(sys, "argv", ["poor-cli", "install-info", "--json"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert '"source": "package"' in output
    assert str(selected_path) in output
