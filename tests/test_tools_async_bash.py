"""Unit tests for ToolRegistryAsync.bash()."""

import asyncio
import signal
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

    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes, pid: int = 0):
        self.returncode = returncode
        self.stdout = self._FakeStream(stdout)
        self.stderr = self._FakeStream(stderr)
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.waited = False

    def terminate(self):
        self.terminated = True

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
async def test_run_command_capture_timeout_terminates_process_group():
    registry = ToolRegistryAsync()
    running_process = _FakeProcess(returncode=0, stdout=b"", stderr=b"", pid=3210)

    async def _raise_timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    with (
        patch(
            "poor_cli.tools_async.asyncio.create_subprocess_exec",
            AsyncMock(return_value=running_process),
        ) as spawn_mock,
        patch(
            "poor_cli.tools_async.asyncio.wait_for",
            AsyncMock(side_effect=_raise_timeout),
        ),
        patch("poor_cli.tools_async.os.killpg", return_value=None, create=True) as killpg_mock,
    ):
        result = await registry._run_command_capture(["sleep", "10"], timeout=1)

    assert result["timed_out"] is True
    assert running_process.waited is True
    killpg_mock.assert_called_once_with(3210, signal.SIGKILL)
    assert spawn_mock.await_args.kwargs["start_new_session"] is True


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


@pytest.mark.asyncio
async def test_bash_cwd_persists_across_calls():
    registry = ToolRegistryAsync()
    proc_cd = _FakeProcess(
        returncode=0,
        stdout=b"__CWD__=/tmp\n",
        stderr=b"",
    )
    proc_pwd = _FakeProcess(
        returncode=0,
        stdout=b"/tmp\n__CWD__=/tmp\n",
        stderr=b"",
    )
    call_count = {"n": 0}

    async def _factory(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return proc_cd
        return proc_pwd

    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=_factory),
    ) as mock_exec:
        await registry.bash("cd /tmp")
        assert registry._cwd == "/tmp"
        result = await registry.bash("pwd")

    assert "/tmp" in result
    assert mock_exec.await_args.kwargs["cwd"] == "/tmp"  # second call used persisted cwd


@pytest.mark.asyncio
async def test_bash_cwd_resets_on_session_clear():
    registry = ToolRegistryAsync()
    proc = _FakeProcess(
        returncode=0,
        stdout=b"__CWD__=/tmp\n",
        stderr=b"",
    )
    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        await registry.bash("cd /tmp")

    assert registry._cwd == "/tmp"
    registry.reset_cwd()
    import os
    assert registry._cwd == os.getcwd()


@pytest.mark.asyncio
async def test_bash_cwd_invalid_dir_no_change():
    registry = ToolRegistryAsync()
    original_cwd = registry._cwd
    proc = _FakeProcess(
        returncode=1,
        stdout=b"__CWD__=/nonexistent\n",
        stderr=b"sh: cd: /nonexistent: No such file or directory\n",
    )
    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        with pytest.raises(CommandExecutionError):
            await registry.bash("cd /nonexistent_path_xyz")

    assert registry._cwd == original_cwd  # unchanged on failure


@pytest.mark.asyncio
async def test_bash_cwd_chained_cd():
    registry = ToolRegistryAsync()
    proc = _FakeProcess(
        returncode=0,
        stdout=b"__CWD__=/var\n",
        stderr=b"",
    )
    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        await registry.bash("cd /tmp && cd /var")

    assert registry._cwd == "/var"


@pytest.mark.asyncio
async def test_bash_cwd_explicit_marker_stripped():
    registry = ToolRegistryAsync()
    proc = _FakeProcess(
        returncode=0,
        stdout=b"hello world\n__CWD__=/home/user\n",
        stderr=b"",
    )
    with patch(
        "poor_cli.tools_async.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = await registry.bash("echo hello world")

    assert "__CWD__" not in result
    assert result == "hello world\n"
    assert registry._cwd == "/home/user"
