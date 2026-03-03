from unittest.mock import AsyncMock, patch

import pytest

import poor_cli.web_search as web_search_module
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
