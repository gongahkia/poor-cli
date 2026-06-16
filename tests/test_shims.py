from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from bench.shim_live_dogfood import dogfood_payload
from poor_cli.cli import main
from poor_cli.replay import replay_verify
from poor_cli.shims import resolve_real_binary
from poor_cli.store import RunStore


def test_shims_install_doctor_uninstall_temp_path(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    shims, bin_dir = tmp_path / "shims", tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    _fake_binary(bin_dir, "codex")
    monkeypatch.setenv("PATH", os.pathsep.join([str(shims), str(bin_dir), os.environ.get("PATH", "")]))

    assert main(["shims", "install", "--dir", str(shims)]) == 0
    output = capsys.readouterr().out
    assert "export PATH=" in output
    assert (shims / "claude").exists()
    assert (shims / "codex").exists()

    assert main(["shims", "doctor", "--dir", str(shims)]) == 0
    doctor = capsys.readouterr().out
    assert "claude: shim=ok real=" in doctor
    assert "codex: shim=ok real=" in doctor
    assert resolve_real_binary("claude", shims, str(shims)) is None

    assert main(["shims", "uninstall", "--dir", str(shims)]) == 0
    assert not (shims / "claude").exists()


def test_shims_install_refuses_unmanaged_file(tmp_path: Path, capsys: Any) -> None:
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "claude").write_text("#!/bin/sh\n", encoding="utf-8")

    assert main(["shims", "install", "--dir", str(shims)]) == 1
    assert "refusing to overwrite unmanaged shim" in capsys.readouterr().err


def test_generated_shims_capture_claude_and_codex_records(tmp_path: Path, monkeypatch: Any) -> None:
    shims, bin_dir = tmp_path / "shims", tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    _fake_binary(bin_dir, "codex")
    assert main(["shims", "install", "--dir", str(shims)]) == 0

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(shims), str(bin_dir), str(Path(sys.executable).parent), env.get("PATH", "")])
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["OPENAI_API_KEY"] = "sk-testsecret123456789"

    claude = subprocess.run(["claude", "-p", "explain repo"], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    codex = subprocess.run(["codex", "exec", "review diff"], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert claude.returncode == 0, claude.stderr
    assert codex.returncode == 0, codex.stderr
    assert "fake-claude:-p explain repo" in claude.stdout
    assert "fake-codex:exec review diff" in codex.stdout

    store = RunStore(tmp_path / ".poor-cli" / "v6")
    try:
        runs = store.list_runs()
        assert {run["user_goal"] for run in runs} == {"explain repo", "review diff"}
        for run in runs:
            assert store.list_artifacts(run["run_id"], "shim.capture")
            assert store.list_artifacts(run["run_id"], "shim.result")
            assert store.list_artifacts(run["run_id"], "route.decision")
            preflight_artifacts = store.list_artifacts(run["run_id"], "route.preflight")
            assert preflight_artifacts
            preflight = json.loads(store.artifact_payload(preflight_artifacts[0]["artifact_id"]))
            assert preflight["command"] in {"claude", "codex"}
            assert preflight["pass_through_command"][0] == preflight["command"]
            assert replay_verify(store, run["run_id"])["verified"] is True
            capture = json.loads(store.artifact_payload(store.list_artifacts(run["run_id"], "shim.capture")[0]["artifact_id"]))
            assert capture["redacted_env"].get("OPENAI_API_KEY") == "[redacted]"
    finally:
        store.close()

    blobs = [path.read_bytes() for path in (tmp_path / ".poor-cli").rglob("*") if path.is_file()]
    assert not any(b"sk-testsecret123456789" in blob for blob in blobs)


def test_live_shim_dogfood_harness_uses_path_shims(tmp_path: Path, monkeypatch: Any) -> None:
    bin_dir = tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    _fake_binary(bin_dir, "codex")
    _poor_cli_binary(bin_dir)
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    monkeypatch.chdir(tmp_path)

    payload = dogfood_payload(confirm_live_agents=True, timeout_seconds=10)

    assert payload["accepted"] is True
    assert payload["checks"]["claude_ok"] is True
    assert payload["checks"]["codex_ok"] is True
    assert {run["agent"] for run in payload["runs"]} == {"claude", "codex"}


def test_live_shim_dogfood_requires_confirmation(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)

    payload = dogfood_payload(confirm_live_agents=False)

    assert payload["accepted"] is False
    assert payload["blocked_by"] == "--confirm-live-agents"


def test_claude_print_stdin_capture_preserves_input(tmp_path: Path, monkeypatch: Any) -> None:
    shims, bin_dir = tmp_path / "shims", tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    assert main(["shims", "install", "--dir", str(shims)]) == 0
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _Stdin(b"piped prompt"))

    assert main(["shims", "exec", "claude", "--", "-p"]) == 0
    store = RunStore(tmp_path / ".poor-cli" / "v6")
    try:
        run = store.list_runs()[0]
        assert run["user_goal"] == "piped prompt"
        capture = json.loads(store.artifact_payload(store.list_artifacts(run["run_id"], "shim.capture")[0]["artifact_id"]))
        assert capture["stdin"] == "piped prompt"
    finally:
        store.close()


def test_shim_high_risk_interrupts_before_agent(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    bin_dir = tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _Stdin(b""))

    assert main(["--store-dir", str(tmp_path / "store"), "shims", "exec", "claude", "--", "-p", "migrate auth schema"]) == 2
    captured = capsys.readouterr()
    assert "poor-cli shim interrupted: high-risk write task requires confirmation" in captured.err
    assert "fake-claude" not in captured.out
    store = RunStore(tmp_path / "store")
    try:
        run = store.list_runs()[0]
        assert run["status"] == "awaiting_confirmation"
        assert not store.list_artifacts(run["run_id"], "shim.result")
        assert any(event["type"] == "shim.interrupted" for event in store.list_events(run["run_id"]))
    finally:
        store.close()


def test_shim_high_risk_can_be_allowed_by_repo_config(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    bin_dir = tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    config = tmp_path / ".poor-cli" / "config.toml"
    config.parent.mkdir()
    config.write_text("version = 1\n[shims]\nallow_high_risk = true\n", encoding="utf-8")
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _Stdin(b""))

    assert main(["--store-dir", str(tmp_path / "store"), "shims", "exec", "claude", "--", "-p", "migrate auth schema"]) == 0
    assert "fake-claude:-p migrate auth schema" in capsys.readouterr().out


def test_shim_high_risk_can_be_confirmed_on_tty(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    bin_dir = tmp_path / "bin"
    _fake_binary(bin_dir, "claude")
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _TtyStdin())
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    assert main(["--store-dir", str(tmp_path / "store"), "shims", "exec", "claude", "--", "-p", "migrate auth schema"]) == 0
    captured = capsys.readouterr()
    assert "poor-cli shim confirmation required: high-risk write task" in captured.err
    assert "fake-claude:-p migrate auth schema" in captured.out
    store = RunStore(tmp_path / "store")
    try:
        run = store.list_runs()[0]
        assert run["status"] == "completed"
        assert any(event["type"] == "shim.confirmed" for event in store.list_events(run["run_id"]))
    finally:
        store.close()


class _Stdin:
    def __init__(self, data: bytes):
        self.buffer = _BytesIn(data)

    def isatty(self) -> bool:
        return False


class _TtyStdin:
    def isatty(self) -> bool:
        return True


class _BytesIn:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


def _fake_binary(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(f"#!/bin/sh\ncat >/dev/null\nprintf 'fake-{name}:%s\\n' \"$*\"\n", encoding="utf-8")
    path.chmod(0o755)


def _poor_cli_binary(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "poor-cli"
    path.write_text(f'#!/bin/sh\nexec {sys.executable} -m poor_cli "$@"\n', encoding="utf-8")
    path.chmod(0o755)
