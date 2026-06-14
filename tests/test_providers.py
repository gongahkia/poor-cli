from __future__ import annotations

from pathlib import Path

import pytest

from poor_cli.offline import OfflineModeError
from poor_cli.providers import CachedReplayProvider, ProviderReplayMiss, ProviderRequest, ProviderResponse, load_provider_entry_points
from poor_cli.store import RunStore


class EchoProvider:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(provider=request.provider, model=request.model, content=f"echo:{request.prompt}", raw={"calls": self.calls})


def test_cached_replay_provider_records_then_replays(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    request = ProviderRequest(provider="test", model="echo", prompt="hello", params={"temperature": 0})
    wrapped = EchoProvider()

    first = CachedReplayProvider(store, run_id, wrapped).call(request)
    replayed = CachedReplayProvider(store, run_id, replay_only=True).call(request)

    assert wrapped.calls == 1
    assert first.content == "echo:hello"
    assert replayed.content == "echo:hello"
    assert replayed.cached is True
    assert [event["type"] for event in store.list_events(run_id)] == [
        "provider.cache_miss",
        "provider.call.started",
        "provider.call.completed",
        "provider.cache_hit",
    ]
    store.close()


def test_cached_replay_provider_fails_closed_on_miss(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    request = ProviderRequest(provider="test", model="echo", prompt="missing")

    with pytest.raises(ProviderReplayMiss):
        CachedReplayProvider(store, run_id, replay_only=True).call(request)

    assert store.list_events(run_id)[0]["type"] == "provider.cache_miss"
    store.close()


def test_cached_replay_provider_blocks_live_call_when_offline(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    request = ProviderRequest(provider="test", model="echo", prompt="missing")
    monkeypatch.setenv("POOR_CLI_OFFLINE", "1")

    with pytest.raises(OfflineModeError):
        CachedReplayProvider(store, run_id, EchoProvider()).call(request)

    events = [event["type"] for event in store.list_events(run_id)]
    assert events == ["provider.cache_miss"]
    store.close()


def test_provider_entry_points_load_provider_instances(monkeypatch) -> None:
    class EntryPoint:
        name = "echo"

        def load(self):
            return EchoProvider

    class EntryPoints:
        def select(self, group: str):
            assert group == "poor_cli.providers"
            return [EntryPoint()]

    monkeypatch.setattr("poor_cli.extensions.entry_points", lambda: EntryPoints())

    providers = load_provider_entry_points()

    assert isinstance(providers["echo"], EchoProvider)
