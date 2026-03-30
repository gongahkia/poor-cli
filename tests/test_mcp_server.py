from __future__ import annotations

from pathlib import Path

import pytest

import haus.mcp_server as mcp_server


@pytest.fixture()
def isolated_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    layout_path = tmp_path / "mcp-layout.json"
    monkeypatch.setattr(mcp_server, "LAYOUT_PATH", layout_path)
    mcp_server._SIMULATION_CACHE.clear()
    return layout_path


def _obj(
    *,
    item_type: str,
    x: float,
    z: float,
    w: float,
    h: float,
    d: float,
    rot: float = 0.0,
    furniture_type: str | None = None,
) -> dict:
    item = {
        "type": item_type,
        "pos": [x, h / 2, z],
        "rot": rot,
        "visible": True,
        "geo": [w, h, d],
        "color": 0x888888,
    }
    if furniture_type:
        item["furnitureType"] = furniture_type
    return item


def test_check_sightline_detects_blocker(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="sofa_3", x=0.0, z=0.0, w=2.2, h=0.8, d=0.9),
            _obj(item_type="furniture", furniture_type="tv_console", x=4.0, z=0.0, w=1.5, h=0.5, d=0.4),
            _obj(item_type="wall", x=2.0, z=0.0, w=0.3, h=2.6, d=2.0),
        ],
    }
    assert mcp_server._save_layout(layout) is None

    result = mcp_server.check_sightline(index_from=0, index_to=1)
    assert "BLOCKED" in result
    assert "[2]" in result


def test_suggest_furniture_placement_returns_ranked_candidates(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="tv_console", x=0.0, z=0.0, w=1.5, h=0.5, d=0.4),
        ],
    }
    assert mcp_server._save_layout(layout) is None

    result = mcp_server.suggest_furniture_placement(
        furniture_type="sofa_3",
        near_index=0,
        face_index=0,
        min_distance=1.6,
        max_distance=3.5,
        require_clear_sightline=True,
        max_candidates=3,
    )
    assert "Top" in result
    assert "score=" in result


def test_simulate_and_apply_option_adds_objects(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="tv_console", x=0.0, z=0.0, w=1.5, h=0.5, d=0.4),
        ],
    }
    assert mcp_server._save_layout(layout) is None

    simulated = mcp_server.simulate_layout_options(
        requirement="place a sofa where I can see the tv",
        max_options=1,
    )
    assert "Generated 1 simulated option" in simulated

    applied = mcp_server.apply_simulated_option(option_index=1)
    assert "Applied simulated option 1" in applied

    objects = mcp_server.list_objects()
    assert "sofa" in objects.lower()


def test_corrupt_layout_is_recovered_without_crash(isolated_layout: Path) -> None:
    isolated_layout.write_text("{ this is invalid json", encoding="utf-8")

    result = mcp_server.list_objects()
    assert "Layout is empty" in result

    backups = list(isolated_layout.parent.glob("mcp-layout.corrupt-*.json"))
    assert backups
