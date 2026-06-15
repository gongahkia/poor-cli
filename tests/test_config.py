from __future__ import annotations

import json
from pathlib import Path

import pytest

from poor_cli.cli import main
from poor_cli.config import (
    ConfigError,
    add_provider,
    doctor,
    empty_config,
    explain_route,
    load_config,
    model_registry,
    provider_preset,
    provider_rows,
    save_repo_config,
    switch_provider,
)


def test_config_rejects_plaintext_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    path = tmp_path / ".poor-cli" / "config.toml"
    path.parent.mkdir()
    path.write_text(
        'version = 1\n[providers.bad]\nkind = "openai"\nmodels = ["gpt"]\napi_key = "secret"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="plaintext secret"):
        load_config(tmp_path, include_env=False)


def test_provider_profiles_models_and_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    config = add_provider(config, "openai", profile["openai"])
    config = switch_provider(config, "openai")
    save_repo_config(config, tmp_path)

    loaded = load_config(tmp_path, include_env=False)
    rows = provider_rows(loaded)
    models = model_registry(loaded)
    route = explain_route(loaded, "fix parser")

    assert rows[0]["active"] is True
    assert rows[0]["kind"] == "openai"
    assert models == [{"alias": "openai:gpt-5.5", "profile": "openai", "model": "gpt-5.5"}]
    assert route["profile"] == "openai"
    assert route["model"] == "gpt-5.5"


def test_route_alias_and_missing_profile_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    config = add_provider(config, "openai", profile["openai"])
    config["models"] = {"fast": {"profile": "openai", "model": "gpt-5.5"}}
    config["routes"] = {"executor": {"profile": "missing", "model": "fast"}}

    route = explain_route(config, "fix parser")

    assert route["profile"] == "openai"
    assert route["model"] == "gpt-5.5"
    assert route["reason"] == "model alias"

    config["routes"] = {"executor": {"profile": "missing", "model": "unknown"}}
    fallback = explain_route(config, "fix parser")
    assert fallback["profile"] == "openai"
    assert fallback["fallbacks"] == [{"profile": "missing", "reason": "missing profile"}]


def test_route_capability_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    ollama = provider_preset("ollama", profile_id="ollama", model="qwen")
    openai = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    config = add_provider(config, "ollama", ollama["ollama"])
    config = add_provider(config, "openai", openai["openai"], make_active=False)
    config["routes"] = {"executor": {"profile": "ollama", "required_capability": "tools"}}

    route = explain_route(config, "fix parser")

    assert route["profile"] == "openai"
    assert route["reason"] == "capability fallback"
    assert route["fallbacks"] == [{"profile": "ollama", "reason": "missing capability: tools"}]


def test_route_budget_and_rate_limit_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    primary = provider_preset("openai", profile_id="primary", model="gpt-5.5")
    fallback = provider_preset("openai", profile_id="fallback", model="gpt-5.5-mini")
    primary["primary"]["limits"] = {"requests_per_minute": 0}
    config = add_provider(config, "primary", primary["primary"])
    config = add_provider(config, "fallback", fallback["fallback"], make_active=False)
    config["budgets"] = {"max_usd": 0.25}
    config["routes"] = {"executor": {"profile": "primary", "fallback_profile": "fallback", "max_cost_usd": 1.0}}

    route = explain_route(config, "fix parser")

    assert route["profile"] == "fallback"
    assert route["reason"] == "budget fallback"
    assert route["fallbacks"] == [{"profile": "primary", "reason": "over budget"}]

    config["routes"] = {"executor": {"profile": "primary"}}
    limited = explain_route(config, "fix parser")
    assert limited["profile"] == "fallback"
    assert limited["reason"] == "rate-limit fallback"
    assert limited["fallbacks"] == [{"profile": "primary", "reason": "rate limit unavailable"}]


def test_provider_doctor_discovers_ollama_models(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("ollama", profile_id="ollama", base_url="http://ollama.test")
    config = add_provider(config, "ollama", profile["ollama"])
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"models":[{"name":"qwen2.5-coder"}]}'

    def opener(request, timeout=0):
        seen["url"] = request.full_url
        return FakeResponse()

    report = doctor(config, "ollama", opener=opener)

    assert seen["url"] == "http://ollama.test/api/tags"
    assert report["endpoint"] == "ok"
    assert report["discovered_models"] == ["qwen2.5-coder"]


def test_provider_doctor_discovers_openai_compatible_models(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("openrouter", profile_id="openrouter", model="openrouter/fusion")
    config = add_provider(config, "openrouter", profile["openrouter"])
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"data":[{"id":"openrouter/fusion"}]}'

    def opener(request, timeout=0):
        seen["url"] = request.full_url
        return FakeResponse()

    report = doctor(config, "openrouter", opener=opener)

    assert seen["url"] == "https://openrouter.ai/api/v1/models"
    assert report["endpoint"] == "ok"
    assert report["model_exists"] is True


def test_cli_provider_add_list_switch_and_route_explain(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert main(["provider", "add", "compatible", "--id", "local", "--base-url", "http://local.test", "--model", "qwen"]) == 0
    capsys.readouterr()
    assert main(["provider", "list", "--json"]) == 0
    providers = json.loads(capsys.readouterr().out)["providers"]
    assert providers[0]["id"] == "local"
    assert providers[0]["active"] is True
    assert main(["provider", "models", "--json"]) == 0
    models = json.loads(capsys.readouterr().out)["models"]
    assert models == [{"alias": "local:qwen", "model": "qwen", "profile": "local"}]

    assert main(["provider", "switch", "local"]) == 0
    capsys.readouterr()
    assert main(["route", "explain", "fix parser", "--json"]) == 0
    route = json.loads(capsys.readouterr().out)
    assert route["profile"] == "local"
    assert route["model"] == "qwen"


def test_cli_provider_export_import(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert main(["provider", "add", "openai", "--model", "gpt-5.5"]) == 0
    capsys.readouterr()
    assert main(["provider", "export", "openai", "--json"]) == 0
    exported = capsys.readouterr().out
    payload = json.loads(exported)
    assert payload["providers"]["openai"]["auth"] == {"env": "OPENAI_API_KEY"}

    imported = tmp_path / "import.json"
    imported.write_text(exported, encoding="utf-8")
    (tmp_path / ".poor-cli" / "config.toml").unlink()
    assert main(["provider", "import", str(imported)]) == 0
    capsys.readouterr()
    assert main(["provider", "list", "--json"]) == 0
    providers = json.loads(capsys.readouterr().out)["providers"]
    assert providers[0]["id"] == "openai"
