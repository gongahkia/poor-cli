from types import SimpleNamespace

from poor_cli.core_provider_info import ProviderInfoMixin


def _core_stub(routing_mode: str = "manual"):
    class Core(ProviderInfoMixin):
        pass

    core = Core()
    core._config_manager = SimpleNamespace(
        get_api_key_info=lambda _provider_name: {"key": "", "source": "none"}
    )
    core.config = SimpleNamespace(
        model=SimpleNamespace(
            routing_mode=routing_mode,
            providers={
                "openai": SimpleNamespace(
                    default_model="gpt-5.1",
                    base_url="",
                    api_key_env_var="OPENAI_API_KEY",
                ),
            },
        ),
    )
    core._resolved_routing_mode = "manual"
    core._provider_readiness_cache = {}
    core._schedule_calls = 0

    def _schedule():
        core._schedule_calls += 1

    core._schedule_provider_readiness_probe = _schedule
    return core


def test_get_routing_mode_manual_uses_cached_or_background(monkeypatch):
    core = _core_stub("manual")
    mode = core.get_routing_mode()
    assert mode == "manual"
    assert core._schedule_calls == 1


def test_get_provider_readiness_populates_cache(monkeypatch):
    core = _core_stub("manual")
    payload = {"openai": {"ready": True, "available": True}}
    core._provider_readiness_cache = payload
    status = core.get_provider_readiness()
    assert status == payload
    assert core._provider_readiness_cache == payload
    assert core._schedule_calls == 1
