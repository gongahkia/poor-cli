"""Tests for poor_cli.tools.deploy."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TableBlock
from poor_cli.tools import deploy as deploy_tools


def _ctx(cwd):
    return SimpleNamespace(
        cwd=str(cwd), has_plugin=lambda _n: False, notify_client=lambda *a, **k: None
    )


def _run(coro):
    return asyncio.run(coro)


def _write_config(cwd: Path, data: dict) -> None:
    path = cwd / ".poor-cli"
    path.mkdir(exist_ok=True)
    (path / "deploy.json").write_text(json.dumps(data))


@pytest.fixture(autouse=True)
def _reset():
    deploy_tools._reset()
    yield
    deploy_tools._reset()


def test_targets_empty_without_config(tmp_path):
    r = _run(deploy_tools.handle_targets(ctx=_ctx(tmp_path), args={}))
    assert not r.is_error
    assert "no deploy targets configured" in r.content[0].text


def test_targets_lists_configured(tmp_path):
    _write_config(
        tmp_path,
        {
            "targets": {
                "staging": {"cmd": "echo staging", "description": "stg"},
                "prod": {"cmd": "echo prod"},
            }
        },
    )
    r = _run(deploy_tools.handle_targets(ctx=_ctx(tmp_path), args={}))
    assert not r.is_error
    tables = [b for b in r.content if isinstance(b, TableBlock)]
    assert tables
    names = {row[0] for row in tables[0].rows}
    assert names == {"staging", "prod"}


def test_run_dry_run_doesnt_execute(tmp_path):
    _write_config(tmp_path, {"targets": {"dev": {"cmd": "echo should-not-run"}}})
    r = _run(
        deploy_tools.handle_run_target(
            ctx=_ctx(tmp_path), args={"target": "dev", "dry_run": True}
        )
    )
    assert not r.is_error
    assert "[dry-run]" in r.content[0].text


def test_run_executes_configured_target(tmp_path):
    _write_config(tmp_path, {"targets": {"dev": {"cmd": f"{sys.executable} -c \"print('deployed')\""}}})
    r = _run(
        deploy_tools.handle_run_target(
            ctx=_ctx(tmp_path), args={"target": "dev"}
        )
    )
    assert not r.is_error
    out = " ".join(
        b.code for b in r.content if hasattr(b, "code")
    )
    assert "deployed" in out


def test_run_unknown_target_error(tmp_path):
    _write_config(tmp_path, {"targets": {"only": {"cmd": "echo"}}})
    r = _run(
        deploy_tools.handle_run_target(
            ctx=_ctx(tmp_path), args={"target": "missing"}
        )
    )
    assert r.is_error
    assert "available: only" in r.content[0].text


def test_preview_start_stop_status(tmp_path):
    r1 = _run(deploy_tools.handle_preview_status(ctx=_ctx(tmp_path), args={}))
    assert "never started" in r1.content[0].text
    r2 = _run(
        deploy_tools.handle_preview_start(
            ctx=_ctx(tmp_path),
            args={"cmd": f"{sys.executable} -c \"import time; time.sleep(30)\""},
        )
    )
    assert not r2.is_error
    r3 = _run(deploy_tools.handle_preview_status(ctx=_ctx(tmp_path), args={}))
    assert "running" in r3.content[0].text
    r4 = _run(deploy_tools.handle_preview_stop(ctx=_ctx(tmp_path), args={}))
    assert not r4.is_error
