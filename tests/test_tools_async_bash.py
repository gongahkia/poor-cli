"""Unit tests for ToolRegistryAsync.bash()."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from poor_cli.exceptions import CommandExecutionError
from poor_cli.tools_async import ToolRegistryAsync


class _FakeProcess:
    class _FakeStream:
        def __init__(self, data: bytes):
            self._data = data
            self._cursor = 0

        async def read(self, size: int) -> bytes:
            if self._cursor >= len(self._data):
                return b""
            chunk = self._data[self._cursor:self._cursor + size]
            self._cursor += len(chunk)
            return chunk

    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes):
        self.returncode = returncode
        self.stdout = self._FakeStream(stdout)
        self.stderr = self._FakeStream(stderr)
        self.killed = False
        self.waited = False

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waited = True


@pytest.mark.asyncio
async def test_bash_validator_block_path_raises_command_execution_error():
    registry = ToolRegistryAsync()
    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
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
            "poor_cli.tools_async.asyncio.create_subprocess_exec",
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
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(return_value=successful_process),
    ):
        result = await registry.bash("echo hello world")

    assert result == "hello world\n"


@pytest.mark.asyncio
async def test_bash_truncates_large_output():
    registry = ToolRegistryAsync()
    registry.MAX_CAPTURED_OUTPUT_BYTES = 10
    noisy_process = _FakeProcess(
        returncode=0,
        stdout=b"0123456789ABCDEFGHIJ",
        stderr=b"",
    )

    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(return_value=noisy_process),
    ):
        result = await registry.bash("echo noisy")

    assert result.startswith("0123456789")
    assert "[Output truncated: stdout truncated at 10 bytes]" in result


@pytest.mark.asyncio
async def test_bash_timeout_is_clamped_by_security_config():
    registry = ToolRegistryAsync()
    registry.config = SimpleNamespace(
        security=SimpleNamespace(max_bash_timeout_seconds=5)
    )
    process = _FakeProcess(returncode=0, stdout=b"ok\n", stderr=b"")
    observed = {}

    async def _wait_for(awaitable, timeout):
        observed["timeout"] = timeout
        return await awaitable

    with (
        patch(
            "poor_cli.tools_async.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        patch(
            "poor_cli.tools_async.asyncio.wait_for",
            AsyncMock(side_effect=_wait_for),
        ),
    ):
        result = await registry.bash("echo ok", timeout=60)

    assert result == "ok\n"
    assert observed["timeout"] == 5
