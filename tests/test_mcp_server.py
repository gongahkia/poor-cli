from __future__ import annotations

import math
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
            _obj(item_type="furniture", furniture_type="wardrobe", x=3.0, z=3.0, w=1.8, h=2.0, d=0.6),
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
    assert "accessibility=" in result


def test_oriented_polygon_collision_avoids_aabb_false_positive() -> None:
    base = _obj(
        item_type="furniture",
        furniture_type="sofa_3",
        x=0.0,
        z=0.0,
        w=2.8,
        h=0.8,
        d=0.3,
        rot=math.radians(45),
    )
    other = _obj(
        item_type="furniture",
        furniture_type="sofa_3",
        x=-2.5,
        z=-1.2,
        w=2.8,
        h=0.8,
        d=0.3,
        rot=0.0,
    )

    base_rect = mcp_server._item_rect(base, padding=0.02)
    other_rect = mcp_server._item_rect(other, padding=0.02)
    assert mcp_server._rect_intersects(base_rect, other_rect)

    base_poly = mcp_server._item_polygon(base, padding=0.02)
    other_poly = mcp_server._item_polygon(other, padding=0.02)
    assert not mcp_server._polygons_intersect(base_poly, other_poly)


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


def test_score_doorway_accessibility_reports_clear(isolated_layout: Path) -> None:
    layout = {"version": 1, "items": []}
    assert mcp_server._save_layout(layout) is None
    result = mcp_server.score_doorway_accessibility(door_x=0.0, door_z=0.0)
    assert "Accessibility score: 1.0" in result
    assert "free" in result.lower()


def test_score_doorway_accessibility_detects_obstruction(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="wardrobe", x=0.5, z=0.0, w=1.8, h=2.0, d=0.6),
        ],
    }
    assert mcp_server._save_layout(layout) is None
    result = mcp_server.score_doorway_accessibility(door_x=0.0, door_z=0.0, required_clearance=0.9)
    assert "wardrobe" in result.lower()
    assert "Accessibility score:" in result


def test_score_walkway_detects_narrow_gap(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="wardrobe", x=0.4, z=1.0, w=1.8, h=2.0, d=0.6),
        ],
    }
    assert mcp_server._save_layout(layout) is None
    result = mcp_server.score_walkway(x1=0.0, z1=0.0, x2=0.0, z2=3.0, min_width=1.5)
    assert "Walkway score:" in result
    assert "Encroaching" in result


def test_list_room_templates_returns_all() -> None:
    result = mcp_server.list_room_templates()
    assert "work_from_home" in result
    assert "family_living" in result
    assert "rental_bedroom" in result


def test_apply_room_template_places_furniture(isolated_layout: Path) -> None:
    layout = {"version": 1, "items": []}
    assert mcp_server._save_layout(layout) is None
    result = mcp_server.apply_room_template(template_name="work_from_home", origin_x=0.0, origin_z=0.0)
    assert "desk" in result.lower()
    assert "chair" in result.lower()
    objects = mcp_server.list_objects()
    assert "desk" in objects.lower()


def test_apply_room_template_tags_room(isolated_layout: Path) -> None:
    layout = {"version": 1, "items": []}
    assert mcp_server._save_layout(layout) is None
    mcp_server.apply_room_template(template_name="work_from_home", room_name="Office")
    rooms = mcp_server.list_rooms()
    assert "Office" in rooms


def test_apply_room_template_rejects_unknown(isolated_layout: Path) -> None:
    result = mcp_server.apply_room_template(template_name="nonexistent")
    assert "Error" in result


def test_suggest_placement_json_returns_structured(isolated_layout: Path) -> None:
    import json

    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="tv_console", x=0.0, z=0.0, w=1.5, h=0.5, d=0.4),
        ],
    }
    assert mcp_server._save_layout(layout) is None
    raw = mcp_server.suggest_placement_json(
        furniture_type="sofa_3",
        near_index=0,
        face_index=0,
        min_distance=1.6,
        max_distance=3.5,
        max_candidates=2,
    )
    result = json.loads(raw)
    assert "candidates" in result
    assert len(result["candidates"]) > 0
    cand = result["candidates"][0]
    assert "breakdown" in cand
    bd = cand["breakdown"]
    assert "distance_component" in bd
    assert "sightline_component" in bd
    assert "accessibility_component" in bd


def test_corrupt_layout_is_recovered_without_crash(isolated_layout: Path) -> None:
    isolated_layout.write_text("{ this is invalid json", encoding="utf-8")

    result = mcp_server.list_objects()
    assert "Layout is empty" in result

    backups = list(isolated_layout.parent.glob("mcp-layout.corrupt-*.json"))
    assert backups
