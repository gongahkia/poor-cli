from __future__ import annotations

from pathlib import Path

from poor_cli.hooks import BaseHook, load_hooks
from poor_cli.models import Budget, TaskSpec, make_id
from poor_cli.orchestrator import Orchestrator
from poor_cli.providers import CachedReplayProvider, ProviderRequest, ProviderResponse
from poor_cli.store import RunStore
from poor_cli.tools import ToolDispatcher


class AuditHook(BaseHook):
    def __init__(self) -> None:
        self.events: list[tuple[str, str | bool]] = []

    def before_turn(self, context):
        self.events.append(("turn", str(context["task_id"])))

    def after_tool_call(self, context, result):
        self.events.append(("tool", bool(context["cached"])))

    def before_model_call(self, context):
        self.events.append(("model", str(context["model"])))

    def after_run(self, context):
        self.events.append(("run", str(context["status"])))


class EchoProvider:
    def call(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(provider=request.provider, model=request.model, content=request.prompt)


def test_hooks_intercept_tool_provider_and_run_paths(tmp_path: Path) -> None:
    hook = AuditHook()
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    task_id = make_id("task")
    store.insert_tasks(run_id, [TaskSpec(task_id=task_id, title="Task", objective="obj", suggested_agent="generic")])

    ToolDispatcher(store, run_id, workdir=tmp_path, hooks=[hook]).call("replay_emit", {"value": "x"}, task_id)
    ToolDispatcher(store, run_id, workdir=tmp_path, hooks=[hook], replay_only=True).call("replay_emit", {"value": "x"}, task_id)
    CachedReplayProvider(store, run_id, EchoProvider(), hooks=[hook]).call(ProviderRequest(provider="test", model="echo", prompt="hi"))
    Orchestrator(store, tmp_path, hooks=[hook]).run(run_id, Budget(), selected_agents={"generic"})

    assert ("tool", False) in hook.events
    assert ("tool", True) in hook.events
    assert ("model", "echo") in hook.events
    assert ("turn", task_id) in hook.events
    assert ("run", "completed") in hook.events
    store.close()


def test_load_hooks_from_entry_points(monkeypatch) -> None:
    class EntryPoint:
        name = "audit"

        def load(self):
            return AuditHook

    class EntryPoints:
        def select(self, group: str):
            assert group == "poor_cli.hooks"
            return [EntryPoint()]

    monkeypatch.setattr("poor_cli.hooks.entry_points", lambda: EntryPoints())

    manager = load_hooks()

    assert len(manager.hooks) == 1
    assert isinstance(manager.hooks[0], AuditHook)
