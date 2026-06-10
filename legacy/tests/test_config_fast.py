"""Tests for lightweight runtime config reads."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from poor_cli import config_fast


def test_load_runtime_model_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_fast, "_DEFAULT_CONFIG_PATH", tmp_path / "missing-config.yaml")
    monkeypatch.setattr(config_fast, "_TRUSTED_REPOS_PATH", tmp_path / "missing-trust.json")
    monkeypatch.chdir(tmp_path)
    settings = config_fast.load_runtime_model_settings()
    assert settings["provider"] == "openai"
    assert isinstance(settings["model"], str) and settings["model"]
    assert settings["routingMode"] == "manual"


def test_load_runtime_model_settings_reads_global(monkeypatch, tmp_path: Path) -> None:
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text(
        yaml.safe_dump({"model": {"provider": "anthropic", "model_name": "claude-3-7-sonnet-20250219", "routing_mode": "quality"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_fast, "_DEFAULT_CONFIG_PATH", global_cfg)
    monkeypatch.setattr(config_fast, "_TRUSTED_REPOS_PATH", tmp_path / "missing-trust.json")
    monkeypatch.chdir(tmp_path)
    settings = config_fast.load_runtime_model_settings()
    assert settings == {
        "provider": "anthropic",
        "model": "claude-3-7-sonnet-20250219",
        "routingMode": "quality",
    }


def test_load_runtime_model_settings_applies_trusted_repo_override(monkeypatch, tmp_path: Path) -> None:
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text(
        yaml.safe_dump({"model": {"provider": "openai", "model_name": "gpt-5.1", "routing_mode": "manual"}}),
        encoding="utf-8",
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_cfg = repo_root / ".poor-cli" / "config.yaml"
    repo_cfg.parent.mkdir(parents=True)
    repo_cfg.write_text(
        yaml.safe_dump({"model": {"provider": "gemini", "model_name": "gemini-2.5-flash", "routing_mode": "speed"}}),
        encoding="utf-8",
    )
    trust_path = tmp_path / "trusted_repos.json"
    trust_path.write_text(
        json.dumps({"trusted": [str(repo_root.resolve())]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_fast, "_DEFAULT_CONFIG_PATH", global_cfg)
    monkeypatch.setattr(config_fast, "_TRUSTED_REPOS_PATH", trust_path)
    monkeypatch.chdir(repo_root)
    settings = config_fast.load_runtime_model_settings()
    assert settings == {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "routingMode": "speed",
    }


def test_load_runtime_model_settings_openai_default_without_catalog(monkeypatch, tmp_path: Path) -> None:
    global_cfg = tmp_path / "config.yaml"
    global_cfg.write_text(
        yaml.safe_dump({"model": {"provider": "openai"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_fast, "_MODEL_DEFAULT_CACHE", None)
    monkeypatch.setattr(config_fast, "_PROVIDER_CATALOG_PATH", tmp_path / "missing-provider-catalog.json")
    monkeypatch.setattr(config_fast, "_DEFAULT_CONFIG_PATH", global_cfg)
    monkeypatch.setattr(config_fast, "_TRUSTED_REPOS_PATH", tmp_path / "missing-trust.json")
    monkeypatch.chdir(tmp_path)
    settings = config_fast.load_runtime_model_settings()
    assert settings["provider"] == "openai"
    assert settings["model"] == "gpt-5.1"
