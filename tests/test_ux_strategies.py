"""Tests for poor_cli.ux_strategies persistence + enum validation."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from poor_cli.ux_strategies import (
    DEFAULTS, RERANKER_CHOICES, ADAPTIVE_CHOICES,
    load, save, set_value, adaptive_override_from_str,
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".poor-cli").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_load_returns_defaults_when_file_missing(repo: Path) -> None:
    assert load() == DEFAULTS


def test_save_then_load_roundtrip(repo: Path) -> None:
    save({"memory_reranker_strategy": "cross_encoder",
          "memory_reranker_cross_encoder_model": "custom/model",
          "adaptive_tool_scoring": "on"})
    got = load()
    assert got["memory_reranker_strategy"] == "cross_encoder"
    assert got["memory_reranker_cross_encoder_model"] == "custom/model"
    assert got["adaptive_tool_scoring"] == "on"


def test_load_falls_back_to_default_for_invalid_enum(repo: Path) -> None:
    path = repo / ".poor-cli" / "strategies.json"
    path.write_text(json.dumps({"memory_reranker_strategy": "lol"}))
    got = load()
    assert got["memory_reranker_strategy"] == DEFAULTS["memory_reranker_strategy"]


def test_set_value_rejects_bad_enum(repo: Path) -> None:
    with pytest.raises(ValueError):
        set_value("memory_reranker_strategy", "nope")


def test_set_value_rejects_unknown_name(repo: Path) -> None:
    with pytest.raises(ValueError):
        set_value("not_a_strategy", "x")


def test_adaptive_override_str_mapping() -> None:
    assert adaptive_override_from_str("auto") is None
    assert adaptive_override_from_str("on") is True
    assert adaptive_override_from_str("off") is False
    assert adaptive_override_from_str("") is None
    assert adaptive_override_from_str("garbage") is None


def test_corrupt_json_recovers(repo: Path) -> None:
    path = repo / ".poor-cli" / "strategies.json"
    path.write_text("{not json")
    assert load() == DEFAULTS


def test_choices_constants_exposed() -> None:
    assert "mmr" in RERANKER_CHOICES
    assert "cross_encoder" in RERANKER_CHOICES
    assert "score_order" in RERANKER_CHOICES
    assert set(ADAPTIVE_CHOICES) == {"auto", "on", "off"}
