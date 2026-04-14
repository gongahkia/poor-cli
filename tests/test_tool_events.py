from poor_cli.tool_events import (
    DISMISSED_MARKER,
    TimelineStore,
    strip_dismissed_results_from_history,
)


def test_timeline_state_transitions():
    store = TimelineStore()
    event = store.pending(
        turn_id="turn-1",
        tool_name="bash",
        args={"command": "printf ok"},
        tool_call_id="call-1",
    )
    assert event.status == "pending"

    store.running(
        turn_id="turn-1",
        tool_name="bash",
        args={"command": "printf ok"},
        tool_call_id="call-1",
    )
    assert store.get("call-1").status == "running"

    store.result(event_id="call-1", status="done", result="ok\n")
    done = store.get("call-1")
    assert done.status == "done"
    assert done.duration_ms is not None
    assert done.result_preview == "ok"


def test_timeline_failed_and_cancelled_states():
    store = TimelineStore()
    store.running(turn_id="turn-1", tool_name="bash", tool_call_id="call-fail")
    store.result(event_id="call-fail", status="failed", result="", error="boom")
    assert store.get("call-fail").status == "failed"
    assert store.get("call-fail").error == "boom"

    store.running(turn_id="turn-1", tool_name="bash", tool_call_id="call-cancel")
    assert store.cancel("call-cancel")
    assert store.get("call-cancel").status == "cancelled"


def test_timeline_stream_chunks_append_to_event():
    store = TimelineStore()
    store.running(turn_id="turn-1", tool_name="run_tests", tool_call_id="call-1")
    store.append_chunk(event_id="call-1", chunk="alpha\n")
    store.append_chunk(event_id="call-1", chunk="beta\n")
    assert store.get("call-1").stream_chunks == ["alpha\n", "beta\n"]


def test_dismiss_excludes_result_from_future_context():
    store = TimelineStore()
    event = store.running(turn_id="turn-1", tool_name="bash", tool_call_id="call-1")
    event.finish("done", "secret output")
    assert store.dismiss("call-1")

    history = [
        {"role": "assistant", "content": "called bash"},
        {"role": "tool", "tool_call_id": "call-1", "content": "secret output"},
        {"role": "assistant", "content": "summary: secret output"},
    ]
    cleaned = strip_dismissed_results_from_history(history, store.dismissed_events())
    assert cleaned[1]["content"] == DISMISSED_MARKER
    assert cleaned[2]["content"] == f"summary: {DISMISSED_MARKER}"


def test_dismiss_strips_anthropic_tool_result_content():
    store = TimelineStore()
    event = store.running(turn_id="turn-1", tool_name="bash", tool_call_id="toolu_1")
    event.finish("done", "anthropic output")
    store.dismiss("toolu_1")

    history = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "anthropic output"},
            ],
        }
    ]
    cleaned = strip_dismissed_results_from_history(history, store.dismissed_events())
    assert cleaned[0]["content"][0]["content"] == DISMISSED_MARKER
