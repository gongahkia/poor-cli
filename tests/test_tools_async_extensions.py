import json
from unittest.mock import AsyncMock, patch

import pytest

import poor_cli.web_search as web_search_module
from poor_cli.exceptions import ValidationError
from poor_cli.tools_async import ToolRegistryAsync


def test_github_tools_registered_only_when_gh_exists():
    with patch("poor_cli.tools_async.shutil.which", return_value=None):
        registry = ToolRegistryAsync()
        assert "gh_pr_list" not in registry.tools
        assert "web_search" in registry.tools

    with patch("poor_cli.tools_async.shutil.which", return_value="/usr/bin/gh"):
        registry = ToolRegistryAsync()
        assert "gh_pr_list" in registry.tools
        assert "gh_pr_view" in registry.tools


def test_extended_tools_are_registered():
    registry = ToolRegistryAsync()
    for tool_name in {
        "run_tests",
        "git_status_diff",
        "apply_patch_unified",
        "format_and_lint",
        "dependency_inspect",
        "fetch_url",
        "json_yaml_edit",
        "process_logs",
    }:
        assert tool_name in registry.tools


@pytest.mark.asyncio
async def test_web_search_uses_brave_when_key_present():
    registry = ToolRegistryAsync()
    with (
        patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "abc"}, clear=False),
        patch.object(web_search_module, "brave_search", AsyncMock(return_value="brave result")) as mock_brave,
    ):
        result = await registry.web_search("latest updates")
    assert result == "brave result"
    mock_brave.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_search_falls_back_to_duckduckgo():
    registry = ToolRegistryAsync()
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(web_search_module, "duckduckgo_search", AsyncMock(return_value="ddg result")) as mock_ddg,
    ):
        result = await registry.web_search("latest updates")
    assert result == "ddg result"
    mock_ddg.assert_awaited_once()


@pytest.mark.asyncio
async def test_json_yaml_edit_updates_json_file(tmp_path):
    registry = ToolRegistryAsync()
    config_path = tmp_path / "config.json"
    config_path.write_text('{"api":{"timeout":5}}', encoding="utf-8")

    result = await registry.json_yaml_edit(
        file_path=str(config_path),
        updates_json='{"api.timeout": 10, "feature.enabled": true}',
    )

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated["api"]["timeout"] == 10
    assert updated["feature"]["enabled"] is True
    assert "Updated" in result


@pytest.mark.asyncio
async def test_process_logs_summarizes_errors(tmp_path):
    registry = ToolRegistryAsync()
    log_file = tmp_path / "app.log"
    log_file.write_text(
        "2026-03-03 10:00:00 INFO startup complete\n"
        "2026-03-03 10:01:00 ERROR db timeout after 30s\n"
        "2026-03-03 10:01:05 ERROR db timeout after 31s\n",
        encoding="utf-8",
    )

    summary = json.loads(await registry.process_logs(path=str(log_file)))

    assert summary["lines_analyzed"] >= 3
    assert summary["level_counts"]["error"] >= 2
    assert summary["top_errors"]


@pytest.mark.asyncio
async def test_run_tests_returns_structured_payload():
    registry = ToolRegistryAsync()
    with patch.object(
        registry,
        "_run_command_capture",
        AsyncMock(
            return_value={
                "stdout": "FAILED tests/test_x.py::test_case - assertion\n",
                "stderr": "",
                "exit_code": 1,
                "timed_out": False,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }
        ),
    ):
        payload = json.loads(await registry.run_tests(command="pytest tests/ -v"))

    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["command"].startswith("pytest")


@pytest.mark.asyncio
async def test_git_status_diff_returns_risk_hints():
    registry = ToolRegistryAsync()
    sequence = [
        {
            "stdout": "/repo\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        },
        {
            "stdout": "M  .github/workflows/tests.yml\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        },
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
    ]

    with patch.object(registry, "_run_command_capture", AsyncMock(side_effect=sequence)):
        payload = json.loads(await registry.git_status_diff())

    assert payload["repository_root"] == "/repo"
    assert payload["risk_hints"]


@pytest.mark.asyncio
async def test_fetch_url_blocks_private_hosts():
    registry = ToolRegistryAsync()
    with pytest.raises(ValidationError):
        await registry.fetch_url("http://127.0.0.1:8080")
