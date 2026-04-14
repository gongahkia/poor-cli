import asyncio
import json
import shlex
import sys

import pytest

from poor_cli.tool_stream import ToolStreamSession, reset_tool_stream_session, set_tool_stream_session
from poor_cli.tools_async import ToolRegistryAsync


@pytest.mark.asyncio
async def test_stream_produces_chunks():
    chunks = []

    async def send(payload):
        chunks.append(payload)

    session = ToolStreamSession(send)
    registry = ToolRegistryAsync()
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('alpha', flush=True); time.sleep(0.02); print('beta', flush=True)",
        ]
    )
    token = set_tool_stream_session(session)
    try:
        result = await registry.execute_tool_raw(
            "run_tests",
            {
                "command": command,
                "_tool_stream_request_id": "req-1",
                "_tool_stream_event_id": "event-1",
                "_tool_call_id": "call-1",
            },
        )
    finally:
        reset_tool_stream_session(token)

    assert len(chunks) >= 2
    assert chunks[0]["eventId"] == "event-1"
    assert "alpha" in "".join(chunk["chunk"] for chunk in chunks)
    payload = json.loads(result.raw_output)
    assert payload["ok"] is True
    assert "alpha" in payload["output_excerpt"]
    assert "beta" in payload["output_excerpt"]


@pytest.mark.asyncio
async def test_backpressure_blocks_when_unacked():
    sent = []

    async def send(payload):
        sent.append(payload)

    session = ToolStreamSession(send, max_buffered_chunks=2)
    await session.publish(request_id="r", event_id="e", tool_call_id="c", tool_name="bash", chunk="0")
    await session.publish(request_id="r", event_id="e", tool_call_id="c", tool_name="bash", chunk="1")

    blocked = asyncio.create_task(
        session.publish(request_id="r", event_id="e", tool_call_id="c", tool_name="bash", chunk="2")
    )
    await asyncio.sleep(0.05)
    assert not blocked.done()

    await session.ack("e", 1)
    assert await asyncio.wait_for(blocked, timeout=1)
    assert [payload["chunkIndex"] for payload in sent] == [0, 1, 2]


@pytest.mark.asyncio
async def test_drop_on_disconnect():
    calls = 0

    async def send(_payload):
        nonlocal calls
        calls += 1
        raise BrokenPipeError()

    session = ToolStreamSession(send, max_buffered_chunks=1)
    assert not await session.publish(
        request_id="r",
        event_id="e",
        tool_call_id="c",
        tool_name="bash",
        chunk="first",
    )
    assert not await asyncio.wait_for(
        session.publish(request_id="r", event_id="e", tool_call_id="c", tool_name="bash", chunk="second"),
        timeout=1,
    )
    assert calls == 1


@pytest.mark.asyncio
async def test_final_output_correct_after_streaming_chunks():
    chunks = []

    async def send(payload):
        chunks.append(payload)

    session = ToolStreamSession(send)
    registry = ToolRegistryAsync()
    token = set_tool_stream_session(session)
    try:
        result = await registry.execute_tool_raw(
            "bash",
            {
                "command": "printf 'final-alpha\\nfinal-beta\\n'",
                "_tool_stream_request_id": "req-2",
                "_tool_stream_event_id": "event-2",
                "_tool_call_id": "call-2",
            },
        )
    finally:
        reset_tool_stream_session(token)

    assert "final-alpha" in result
    assert "final-beta" in result
    chunk_text = "".join(chunk["chunk"] for chunk in chunks)
    assert "final-alpha" in chunk_text
    assert "final-beta" in chunk_text
    assert "__CWD__=" not in result


@pytest.mark.asyncio
async def test_cancel_kills_subprocess():
    chunks = []

    async def send(payload):
        chunks.append(payload)

    session = ToolStreamSession(send)
    registry = ToolRegistryAsync()
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(30)",
        ]
    )
    token = set_tool_stream_session(session)
    try:
        task = asyncio.create_task(
            registry.execute_tool_raw(
                "run_tests",
                {
                    "command": command,
                    "_tool_stream_request_id": "req-cancel",
                    "_tool_stream_event_id": "event-cancel",
                    "_tool_call_id": "call-cancel",
                },
            )
        )
        for _ in range(50):
            if chunks:
                break
            await asyncio.sleep(0.02)
        assert chunks
        assert await session.cancel("event-cancel")
        result = await asyncio.wait_for(task, timeout=5)
    finally:
        reset_tool_stream_session(token)

    payload = json.loads(result.raw_output)
    assert payload["ok"] is False
    assert payload["exit_code"] != 0
