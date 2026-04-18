"""tests for provider probe latency optimizations."""

from __future__ import annotations

import threading
import time

from poor_cli.config import Config
from poor_cli import provider_probe


class _ConfigManagerStub:
    def get_api_key_info(self, _provider_name: str):
        return {"key": "", "source": "none"}


def _reset_probe_cache() -> None:
    with provider_probe._probe_cache_lock:
        provider_probe._probe_cache_at = 0.0
        provider_probe._probe_cache_signature = ""
        provider_probe._probe_cache_result = None
        provider_probe._probe_cache_refreshing = False


def test_probe_providers_parallelizes_local_probes(monkeypatch):
    config = Config()
    manager = _ConfigManagerStub()
    _reset_probe_cache()
    monkeypatch.setenv("POORCLI_PROVIDER_PROBE_ALL_LOCAL", "1")

    active = 0
    max_active = 0
    lock = threading.Lock()

    def _mark_work():
        nonlocal active, max_active
        with lock:
            active += 1
            if active > max_active:
                max_active = active
        time.sleep(0.03)
        with lock:
            active -= 1

    def _fake_ollama(_config):
        _mark_work()
        return {"ready": False, "models": [], "baseUrl": "http://localhost:11434"}

    def _fake_openai_compat(_config, provider_name):
        _mark_work()
        return {"ready": False, "models": [], "baseUrl": f"http://{provider_name}.local"}

    monkeypatch.setattr(provider_probe, "_discover_ollama_models", _fake_ollama)
    monkeypatch.setattr(provider_probe, "_discover_openai_compatible_models", _fake_openai_compat)

    provider_probe.probe_providers(manager, config)
    assert max_active >= 2


def test_probe_providers_cache_avoids_reprobe(monkeypatch):
    config = Config()
    manager = _ConfigManagerStub()
    _reset_probe_cache()
    monkeypatch.setenv("POORCLI_PROVIDER_PROBE_ALL_LOCAL", "1")

    call_count = {"ollama": 0, "openai_compat": 0}

    def _fake_ollama(_config):
        call_count["ollama"] += 1
        return {"ready": False, "models": [], "baseUrl": "http://localhost:11434"}

    def _fake_openai_compat(_config, provider_name):
        call_count["openai_compat"] += 1
        return {"ready": False, "models": [], "baseUrl": f"http://{provider_name}.local"}

    monkeypatch.setattr(provider_probe, "_discover_ollama_models", _fake_ollama)
    monkeypatch.setattr(provider_probe, "_discover_openai_compatible_models", _fake_openai_compat)

    provider_probe.probe_providers(manager, config)
    provider_probe.probe_providers(manager, config)

    assert call_count["ollama"] == 1
    assert call_count["openai_compat"] == len(provider_probe.LOCAL_OPENAI_COMPATIBLE_PROVIDERS)


def test_probe_providers_default_focuses_on_active_local_provider(monkeypatch):
    config = Config()
    manager = _ConfigManagerStub()
    _reset_probe_cache()
    config.model.provider = "openai"
    config.model.routing_mode = "manual"

    call_count = {"ollama": 0, "openai_compat": 0}

    def _fake_ollama(_config):
        call_count["ollama"] += 1
        return {"ready": False, "models": [], "baseUrl": "http://localhost:11434"}

    def _fake_openai_compat(_config, provider_name):
        call_count["openai_compat"] += 1
        return {"ready": False, "models": [], "baseUrl": f"http://{provider_name}.local"}

    monkeypatch.setattr(provider_probe, "_discover_ollama_models", _fake_ollama)
    monkeypatch.setattr(provider_probe, "_discover_openai_compatible_models", _fake_openai_compat)

    payload = provider_probe.probe_providers(
        manager,
        config,
        allow_stale=False,
        background_refresh=False,
        force_refresh=True,
    )

    assert call_count["ollama"] == 0
    assert call_count["openai_compat"] == 0
    for name in provider_probe.LOCAL_OPENAI_COMPATIBLE_PROVIDERS:
        if name in payload:
            assert payload[name]["ready"] is False
