"""
Tests for poor_cli.repl_async non-interactive CLI entrypoints.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poor_cli.repl_async import PoorCLIAsync, main


class TestRunNonInteractive:
    """Test non-interactive run mode execution."""

    @pytest.mark.asyncio
    async def test_run_non_interactive_success_returns_zero(self):
        repl = object.__new__(PoorCLIAsync)
        repl.initialize = AsyncMock()
        repl._process_request_non_interactive = AsyncMock(
            return_value={
                "ok": True,
                "response": "done",
                "tool_calls": [],
                "error": None,
            }
        )
        repl._shutdown_sessions = AsyncMock()

        with patch("builtins.print") as mock_print:
            exit_code = await PoorCLIAsync.run_non_interactive(repl, "hello world")

        assert exit_code == 0
        repl.initialize.assert_awaited_once_with(show_welcome=False)
        repl._process_request_non_interactive.assert_awaited_once_with("hello world")
        repl._shutdown_sessions.assert_awaited_once_with()
        mock_print.assert_called_once_with("done")

    @pytest.mark.asyncio
    async def test_run_non_interactive_failure_returns_one(self):
        repl = object.__new__(PoorCLIAsync)
        repl.initialize = AsyncMock()
        repl._process_request_non_interactive = AsyncMock(
            return_value={
                "ok": False,
                "response": "",
                "tool_calls": [{"name": "bash", "result": "denied"}],
                "error": {"type": "RuntimeError", "message": "bad request"},
            }
        )
        repl._shutdown_sessions = AsyncMock()

        with patch("builtins.print") as mock_print:
            exit_code = await PoorCLIAsync.run_non_interactive(repl, "hello world")

        assert exit_code == 1
        repl.initialize.assert_awaited_once_with(show_welcome=False)
        repl._process_request_non_interactive.assert_awaited_once_with("hello world")
        repl._shutdown_sessions.assert_awaited_once_with()
        mock_print.assert_called_once_with("Error: bad request", file=sys.stderr)

    @pytest.mark.asyncio
    async def test_run_non_interactive_json_output(self):
        repl = object.__new__(PoorCLIAsync)
        repl.initialize = AsyncMock()
        repl._process_request_non_interactive = AsyncMock(
            return_value={
                "ok": True,
                "response": "done",
                "tool_calls": [{"name": "read_file", "arguments": {"file_path": "a.py"}, "result": "ok"}],
                "error": None,
            }
        )
        repl._shutdown_sessions = AsyncMock()

        with patch("builtins.print") as mock_print:
            exit_code = await PoorCLIAsync.run_non_interactive(
                repl,
                "hello world",
                output_format="json",
            )

        assert exit_code == 0
        repl.initialize.assert_awaited_once_with(show_welcome=False)
        repl._process_request_non_interactive.assert_awaited_once_with("hello world")
        repl._shutdown_sessions.assert_awaited_once_with()
        printed_json = mock_print.call_args.args[0]
        assert '"ok": true' in printed_json
        assert '"tool_calls"' in printed_json


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
        mock_repl.run_non_interactive.assert_called_once_with("ship it", output_format="text")
        mock_asyncio_run.assert_called_once_with("non-interactive-coro")

    def test_main_run_subcommand_allows_json_output(self, monkeypatch):
        monkeypatch.setattr(
            "poor_cli.repl_async.sys.argv",
            ["poor-cli", "run", "ship it", "--output", "json"],
        )
        mock_repl = MagicMock()
        mock_repl.run_non_interactive.return_value = "non-interactive-coro"

        with (
            patch("poor_cli.repl_async.PoorCLIAsync", return_value=mock_repl),
            patch("poor_cli.repl_async.asyncio.run", return_value=0) as mock_asyncio_run,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        mock_repl.run_non_interactive.assert_called_once_with("ship it", output_format="json")
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
