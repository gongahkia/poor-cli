"""tests for poor_cli.turn_pin_overlay and its integration with
history_pruning.prune(turn_pin_overlay=...).
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from poor_cli.turn_pin_overlay import TurnPinOverlay
from poor_cli.history_pruning import HistoryPruner, PruningPolicy, _apply_turn_pin_overlay


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".poor-cli").mkdir()
    return tmp_path


def test_set_get_roundtrip(repo: Path) -> None:
    ov = TurnPinOverlay(repo).load()
    ov.set("t1", "soft")
    ov.set("t2", "hard")
    ov2 = TurnPinOverlay(repo).load()
    assert ov2.get("t1") == "soft"
    assert ov2.get("t2") == "hard"
    assert ov2.get("missing") is None


def test_null_clears(repo: Path) -> None:
    ov = TurnPinOverlay(repo).load()
    ov.set("t1", "soft")
    ov.set("t1", None)
    assert ov.get("t1") is None
    ov2 = TurnPinOverlay(repo).load()
    assert ov2.get("t1") is None


def test_invalid_state_raises(repo: Path) -> None:
    ov = TurnPinOverlay(repo).load()
    with pytest.raises(ValueError):
        ov.set("t1", "banana")


def test_corrupt_file_recovers(repo: Path) -> None:
    path = repo / ".poor-cli" / "turn_pins.json"
    path.write_text("{not valid json")
    ov = TurnPinOverlay(repo).load()
    assert ov.all() == {}


def test_all_excludes_invalid_entries(repo: Path) -> None:
    path = repo / ".poor-cli" / "turn_pins.json"
    path.write_text(json.dumps({"t1": "soft", "t2": "bogus", "t3": 42, "t4": "hard"}))
    ov = TurnPinOverlay(repo).load()
    assert ov.all() == {"t1": "soft", "t4": "hard"}


def test_apply_overlay_merges_into_metadata() -> None:
    history = [
        {"role": "user", "content": "hi", "metadata": {"turn_id": "t1"}},
        {"role": "assistant", "content": "hello", "metadata": {"turn_id": "t2"}},
        {"role": "user", "content": "what", "metadata": {"turnId": "t3"}},
    ]
    overlay = {"t1": "soft", "t3": "hard"}
    out = _apply_turn_pin_overlay(history, overlay)
    assert out[0]["metadata"]["pinned"] == "soft"
    assert "pinned" not in out[1]["metadata"]
    assert out[2]["metadata"]["pinned"] == "hard"
    # original history untouched
    assert "pinned" not in history[0]["metadata"]


def test_apply_overlay_ignores_invalid_states() -> None:
    history = [{"role": "user", "content": "x", "metadata": {"turn_id": "t1"}}]
    out = _apply_turn_pin_overlay(history, {"t1": "bogus"})
    assert "pinned" not in out[0]["metadata"]


def test_pruner_respects_overlay_soft_pin() -> None:
    # build a history with 4 msgs; without overlay msg 1 would be prunable,
    # with overlay setting soft pin it survives under non-severe pressure.
    history = [
        {"role": "user", "content": "old question" * 50, "metadata": {"turn_id": "t1"}},
        {"role": "assistant", "content": "old answer" * 50, "metadata": {"turn_id": "t1"}},
        {"role": "user", "content": "recent question" * 50, "metadata": {"turn_id": "t2"}},
        {"role": "assistant", "content": "recent answer" * 50, "metadata": {"turn_id": "t2"}},
    ]
    pruner = HistoryPruner()
    without = pruner.prune(history, target_tokens=100, mode="frugal", economy_preset="frugal").history
    with_overlay = pruner.prune(
        history, target_tokens=100, mode="frugal", economy_preset="frugal",
        turn_pin_overlay={"t1": "soft"},
    ).history
    assert len(with_overlay) >= len(without), "soft pin should preserve at least as many msgs"
