from __future__ import annotations

import asyncio
import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Protocol


class ToolStreamCancelled(Exception):
    pass


class StreamingToolResult(Protocol):
    def __aiter__(self) -> AsyncIterator[str]: ...
    async def final(self) -> Any: ...
    async def cancel(self) -> None: ...


SendToolChunk = Callable[[Dict[str, Any]], Awaitable[None]]

_current_session: ContextVar[Optional["ToolStreamSession"]] = ContextVar(
    "poor-cli_tool_stream_session",
    default=None,
)


def current_tool_stream_session() -> Optional["ToolStreamSession"]:
    return _current_session.get()


def set_tool_stream_session(session: Optional["ToolStreamSession"]):
    return _current_session.set(session)


def reset_tool_stream_session(token: Any) -> None:
    _current_session.reset(token)


@dataclass
class _State:
    produced: int = 0
    acked: int = 0
    disconnected: bool = False
    cancelled: bool = False
    result: Optional[StreamingToolResult] = None


class ToolStreamSession:
    def __init__(self, send_chunk: SendToolChunk, *, max_buffered_chunks: int = 16):
        self._send_chunk = send_chunk
        self._max_buffered_chunks = max(1, int(max_buffered_chunks))
        self._states: Dict[str, _State] = {}
        self._condition = asyncio.Condition()

    async def register(self, event_id: str, result: StreamingToolResult) -> None:
        async with self._condition:
            state = self._states.setdefault(event_id, _State())
            state.result = result

    async def publish(
        self,
        *,
        request_id: str,
        event_id: str,
        tool_call_id: str,
        tool_name: str,
        chunk: str,
    ) -> bool:
        async with self._condition:
            state = self._states.setdefault(event_id, _State())
            while (
                state.produced - state.acked >= self._max_buffered_chunks
                and not state.disconnected
                and not state.cancelled
            ):
                await self._condition.wait()
            if state.cancelled:
                raise ToolStreamCancelled(event_id)
            if state.disconnected:
                return False
            chunk_index = state.produced
            state.produced += 1

        try:
            await self._send_chunk(
                {
                    "requestId": request_id,
                    "eventId": event_id,
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "chunkIndex": chunk_index,
                    "chunk": chunk,
                }
            )
            return True
        except Exception:
            async with self._condition:
                state = self._states.setdefault(event_id, _State())
                state.disconnected = True
                self._condition.notify_all()
            return False

    async def ack(self, event_id: str, chunks_processed: int) -> None:
        async with self._condition:
            state = self._states.setdefault(event_id, _State())
            state.acked = max(state.acked, int(chunks_processed))
            self._condition.notify_all()

    async def cancel(self, event_id: str) -> bool:
        async with self._condition:
            state = self._states.setdefault(event_id, _State())
            state.cancelled = True
            result = state.result
            self._condition.notify_all()
        if result is not None:
            await result.cancel()
        return result is not None

    async def close(self) -> None:
        async with self._condition:
            results = [state.result for state in self._states.values() if state.result is not None]
            for state in self._states.values():
                state.disconnected = True
            self._condition.notify_all()
        for result in results:
            with contextlib.suppress(Exception):
                await result.cancel()


class SubprocessStreamingResult:
    def __init__(
        self,
        *,
        process: asyncio.subprocess.Process,
        timeout: int,
        max_bytes: int,
        signal_process: Callable[[Any, int], bool],
        finalizer: Callable[[str, str, int, bool, bool, bool, bool], Any],
    ):
        self.process = process
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._signal_process = signal_process
        self._finalizer = finalizer
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._stdout_truncated = False
        self._stderr_truncated = False
        self._timed_out = False
        self._cancelled = False
        self._runner: Optional[asyncio.Task[None]] = None

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        self._ensure_runner()
        try:
            while True:
                item = await self._queue.get()
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            await self.cancel()
            raise

    def _ensure_runner(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run())

    async def _run(self) -> None:
        readers = [
            asyncio.create_task(self._read_pipe(self.process.stdout, self._stdout, "stdout")),
            asyncio.create_task(self._read_pipe(self.process.stderr, self._stderr, "stderr")),
        ]
        try:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=self.timeout)
            except asyncio.TimeoutError:
                self._timed_out = True
                self._signal_process(self.process, 9)
                await self.process.wait()
            await asyncio.gather(*readers, return_exceptions=True)
        finally:
            await self._queue.put(None)

    async def _read_pipe(self, pipe: Any, captured: bytearray, _label: str) -> None:
        if pipe is None:
            return
        while True:
            chunk = await pipe.readline()
            if not chunk:
                break
            self._capture(captured, chunk)
            await self._queue.put(chunk.decode("utf-8", errors="replace"))

    def _capture(self, captured: bytearray, chunk: bytes) -> None:
        if len(captured) >= self.max_bytes:
            if captured is self._stdout:
                self._stdout_truncated = True
            else:
                self._stderr_truncated = True
            return
        remaining = self.max_bytes - len(captured)
        if len(chunk) > remaining:
            if captured is self._stdout:
                self._stdout_truncated = True
            else:
                self._stderr_truncated = True
        captured.extend(chunk[:remaining])

    async def final(self) -> Any:
        self._ensure_runner()
        await self._runner
        stdout = bytes(self._stdout).decode("utf-8", errors="replace")
        stderr = bytes(self._stderr).decode("utf-8", errors="replace")
        return self._finalizer(
            stdout,
            stderr,
            int(self.process.returncode or 0),
            self._timed_out,
            self._stdout_truncated,
            self._stderr_truncated,
            self._cancelled,
        )

    async def cancel(self) -> None:
        if self.process.returncode is not None:
            return
        self._cancelled = True
        self._signal_process(self.process, 15)
        try:
            await asyncio.wait_for(self.process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self._signal_process(self.process, 9)
            await self.process.wait()


class CallbackStreamingResult:
    def __init__(self, run: Callable[[Callable[[str], Awaitable[None]]], Awaitable[Any]]):
        self._run_callback = run
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._runner: Optional[asyncio.Task[None]] = None
        self._result: Any = None
        self._cancelled = False

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        self._ensure_runner()
        try:
            while True:
                item = await self._queue.get()
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            await self.cancel()
            raise

    def _ensure_runner(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run())

    async def _run(self) -> None:
        async def emit(chunk: str) -> None:
            if not self._cancelled:
                await self._queue.put(chunk)

        try:
            self._result = await self._run_callback(emit)
        finally:
            await self._queue.put(None)

    async def final(self) -> Any:
        self._ensure_runner()
        await self._runner
        return self._result

    async def cancel(self) -> None:
        self._cancelled = True
        if self._runner is not None:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
