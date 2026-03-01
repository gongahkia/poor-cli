"""
Tests for poor_cli.repl_async non-interactive CLI entrypoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poor_cli.repl_async import PoorCLIAsync, main


class TestRunNonInteractive:
    """Test non-interactive run mode execution."""

    @pytest.mark.asyncio
    async def test_run_non_interactive_success_returns_zero(self):
        repl = object.__new__(PoorCLIAsync)
        repl.initialize = AsyncMock()
        repl.process_request = AsyncMock(return_value=True)
        repl._shutdown_sessions = AsyncMock()

        exit_code = await PoorCLIAsync.run_non_interactive(repl, "hello world")

        assert exit_code == 0
        repl.initialize.assert_awaited_once_with(show_welcome=False)
        repl.process_request.assert_awaited_once_with("hello world")
        repl._shutdown_sessions.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_run_non_interactive_failure_returns_one(self):
        repl = object.__new__(PoorCLIAsync)
        repl.initialize = AsyncMock()
        repl.process_request = AsyncMock(return_value=False)
        repl._shutdown_sessions = AsyncMock()

        exit_code = await PoorCLIAsync.run_non_interactive(repl, "hello world")

        assert exit_code == 1
        repl.initialize.assert_awaited_once_with(show_welcome=False)
        repl.process_request.assert_awaited_once_with("hello world")
        repl._shutdown_sessions.assert_awaited_once_with()


class TestMainEntrypoint:
    """Test argument parsing behavior for main()."""

    def test_main_run_subcommand_uses_non_interactive_path(self, monkeypatch):
        monkeypatch.setattr("poor_cli.repl_async.sys.argv", ["poor-cli", "run", "ship it"])
        mock_repl = MagicMock()
        mock_repl.run_non_interactive.return_value = "non-interactive-coro"

        with (
            patch("poor_cli.repl_async.PoorCLIAsync", return_value=mock_repl),
            patch("poor_cli.repl_async.asyncio.run", return_value=0) as mock_asyncio_run,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        mock_repl.run_non_interactive.assert_called_once_with("ship it")
        mock_asyncio_run.assert_called_once_with("non-interactive-coro")

    def test_main_without_subcommand_runs_interactive(self, monkeypatch):
        monkeypatch.setattr("poor_cli.repl_async.sys.argv", ["poor-cli"])
        mock_repl = MagicMock()
        mock_repl.run.return_value = "interactive-coro"

        with (
            patch("poor_cli.repl_async.PoorCLIAsync", return_value=mock_repl),
            patch("poor_cli.repl_async.asyncio.run") as mock_asyncio_run,
        ):
            main()

        mock_repl.run.assert_called_once_with()
        mock_asyncio_run.assert_called_once_with("interactive-coro")
