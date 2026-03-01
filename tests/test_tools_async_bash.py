"""Unit tests for ToolRegistryAsync.bash()."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from poor_cli.exceptions import CommandExecutionError
from poor_cli.tools_async import ToolRegistryAsync


class _FakeProcess:
    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False
        self.waited = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waited = True


@pytest.mark.asyncio
async def test_bash_validator_block_path_raises_command_execution_error():
    registry = ToolRegistryAsync()
    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_shell",
        AsyncMock(),
    ) as mock_subprocess:
        with pytest.raises(CommandExecutionError, match="blocked by validator"):
            await registry.bash("rm -rf /")

    mock_subprocess.assert_not_awaited()


@pytest.mark.asyncio
async def test_bash_timeout_kills_process_and_raises():
    registry = ToolRegistryAsync()
    running_process = _FakeProcess(returncode=0, stdout=b"", stderr=b"")

    async def _raise_timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    with (
        patch(
            "poor_cli.tools_async.asyncio.create_subprocess_shell",
            AsyncMock(return_value=running_process),
        ),
        patch(
            "poor_cli.tools_async.asyncio.wait_for",
            AsyncMock(side_effect=_raise_timeout),
        ),
    ):
        with pytest.raises(CommandExecutionError, match="timed out"):
            await registry.bash("sleep 10", timeout=1)

    assert running_process.killed is True
    assert running_process.waited is True


@pytest.mark.asyncio
async def test_bash_success_path_returns_stdout():
    registry = ToolRegistryAsync()
    successful_process = _FakeProcess(
        returncode=0,
        stdout=b"hello world\n",
        stderr=b"",
    )

    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_shell",
        AsyncMock(return_value=successful_process),
    ):
        result = await registry.bash("echo hello world")

    assert result == "hello world\n"
