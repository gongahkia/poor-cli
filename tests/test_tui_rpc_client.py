from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

from poor_cli.tui.rpc_client import BackendConfiguration, frame_message, read_framed_message


def test_frame_and_read_message_round_trip():
    payload = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "ping",
        "params": {"ok": True},
    }
    framed = frame_message(payload)
    decoded = read_framed_message(BytesIO(framed))
    assert decoded == payload


def test_read_message_rejects_missing_content_length():
    stream = BytesIO(b"Content-Type: application/json\r\n\r\n{}")
    try:
        read_framed_message(stream)
    except ValueError as exc:
        assert "Content-Length" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_backend_configuration_detected_prefers_repo_venv_python(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    venv_python = repo_root / ".venv" / "bin"
    venv_python.mkdir(parents=True)
    python_path = venv_python / "python"
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")
    python_path.chmod(0o755)

    config = BackendConfiguration.detected(repo_root=str(repo_root))
    assert config.python_executable == str(python_path)


def test_backend_configuration_falls_back_to_current_python(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    config = BackendConfiguration.detected(repo_root=str(repo_root))
    assert config.python_executable == sys.executable
