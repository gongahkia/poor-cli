"""Tests for minimal core initialization used by diagnostics commands."""

from __future__ import annotations

import asyncio
import json

from poor_cli.cli.config_cmds import run_core_info_command
from poor_cli.core import PoorCLICore


def test_core_initialize_minimal_skips_provider_bootstrap() -> None:
    async def _run() -> None:
        core = PoorCLICore()
        await core.initialize(minimal=True)
        try:
            assert core._initialized is True
            assert core.provider is None
            tools = core.get_available_tools()
            assert isinstance(tools, list)
            assert len(tools) > 0
            status = core.build_status_view()
            assert isinstance(status, dict)
            assert status.get("session", {}).get("initialized") is True
        finally:
            await core.shutdown(fast=True)

    asyncio.run(_run())


def test_run_core_info_command_works_without_api_key(capsys) -> None:
    exit_code = run_core_info_command(
        "get_available_tools",
        ["--json"],
        "poor-cli diag tools",
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
