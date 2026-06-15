from __future__ import annotations

from pathlib import Path

from poor_cli.native_runner import ProviderBackedAgentRunner
from poor_cli.provider_events import normalize_tool_calls, provider_capabilities
from poor_cli.providers import ProviderRequest, ProviderResponse
from poor_cli.store import RunStore


class ToolCallingProvider:
    def __init__(self) -> None:
        self.calls: list[ProviderRequest] = []

    def call(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if len(self.calls) == 1:
            raw = {
                "choices": [
                    {"message": {"tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": '{"path":"note.txt"}'}}]}}
                ]
            }
            return ProviderResponse(provider=request.provider, model=request.model, content="", raw=raw)
        assert request.messages is not None
        assert any(message.get("role") == "tool" for message in request.messages)
        return ProviderResponse(provider=request.provider, model=request.model, content="done", raw={})


def test_native_runner_executes_tool_loop_and_records_replay(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    provider = ToolCallingProvider()

    result = ProviderBackedAgentRunner(provider, store, run_id, tmp_path).run(
        provider_name="vllm", model="qwen", prompt="read note", system_prompt="sys", task_id="task_1", params={}
    )
    replay = ProviderBackedAgentRunner(ToolCallingProvider(), store, run_id, tmp_path, replay_only=True).run(
        provider_name="vllm", model="qwen", prompt="read note", system_prompt="sys", task_id="task_1", params={}
    )

    assert result.stdout == "done"
    assert result.tool_calls == 1
    assert replay.stdout == "done"
    assert len(provider.calls) == 2
    assert store.list_artifacts(run_id, "provider.response")
    assert store.list_artifacts(run_id, "tool.result")
    store.close()


def test_openai_final_args_done_event_normalizes_tool_call() -> None:
    raw = {
        "events": [
            {
                "type": "response.function_call_arguments.done",
                "item": {"call_id": "c", "name": "read_file", "arguments": '{"path":"a"}'},
            }
        ]
    }

    calls = normalize_tool_calls("openai", raw)

    assert calls[0].id == "c"
    assert calls[0].arguments == {"path": "a"}


def test_provider_capability_probe_shape() -> None:
    caps = provider_capabilities("openai", 128000)

    assert caps["tools"] is True
    assert caps["streaming"] is True
    assert caps["max_context"] == 128000
