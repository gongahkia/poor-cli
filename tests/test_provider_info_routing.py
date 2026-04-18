from types import SimpleNamespace

from poor_cli.core_provider_info import ProviderInfoMixin


def _core_stub(routing_mode: str = "manual"):
    class Core(ProviderInfoMixin):
        pass

    core = Core()
    core._config_manager = object()
    core.config = SimpleNamespace(model=SimpleNamespace(routing_mode=routing_mode))
    core._resolved_routing_mode = "manual"
    core._provider_readiness_cache = {}
    core._schedule_calls = 0

    def _schedule():
        core._schedule_calls += 1

    core._schedule_provider_readiness_probe = _schedule
    return core


def test_get_routing_mode_manual_uses_cached_or_background(monkeypatch):
    core = _core_stub("manual")
    monkeypatch.setattr("poor_cli.core_provider_info.probe_providers", lambda *_args, **_kwargs: {"openai": {"ready": True}})
    mode = core.get_routing_mode()
    assert mode == "manual"
    assert core._schedule_calls == 1


def test_get_provider_readiness_populates_cache(monkeypatch):
    core = _core_stub("manual")
    payload = {"openai": {"ready": True, "available": True}}
    monkeypatch.setattr("poor_cli.core_provider_info.probe_providers", lambda *_args, **_kwargs: payload)
    status = core.get_provider_readiness()
    assert status == payload
    assert core._provider_readiness_cache == payload
