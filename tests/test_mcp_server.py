from __future__ import annotations

import math
import json
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


def test_ikea_catalog_tool_search_and_place(
    isolated_layout: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    assert mcp_server._save_layout({"version": 1, "items": []}) is None

    results = mcp_server.search_ikea_catalog("BILLY")
    assert "BILLY" in results
    added = mcp_server.add_catalog_furniture("ikea-seed-billy-bookcase", x=1.0, z=2.0)
    assert "Added IKEA catalog item" in added

    layout = json.loads(isolated_layout.read_text(encoding="utf-8"))
    assert layout["items"][0]["furnitureType"] == "ikea:ikea-seed-billy-bookcase"
    assert layout["items"][0]["catalog"]["source"] == "ikea"


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


def test_design_room_adds_tagged_furniture_with_trace(isolated_layout: Path) -> None:
    assert mcp_server._save_layout({"version": 1, "items": []}) is None

    result = mcp_server.design_room(
        room_id="Study",
        style_prompt="minimalist work from home",
        constraints="leave circulation clear",
    )

    assert "Design summary:" in result
    assert "Tool-call trace:" in result
    assert "choose_furniture_set" in result
    assert "add_furniture" in result

    rooms = mcp_server.list_rooms()
    assert "Study" in rooms
    objects = mcp_server.list_objects()
    assert "desk" in objects.lower()


def test_design_flat_adds_multiple_rooms(isolated_layout: Path) -> None:
    assert mcp_server._save_layout({"version": 1, "items": []}) is None

    result = mcp_server.design_flat(
        style_prompt="minimalist 4-room family flat",
        constraints="family friendly, clear walkways",
    )

    assert "Rooms designed: 5" in result
    assert "Living" in result
    assert "Kitchen" in result
    assert "Master Bedroom" in result

    rooms = mcp_server.list_rooms()
    assert "Living" in rooms
    assert "Kitchen" in rooms
    assert "Master Bedroom" in rooms


def test_design_flat_uses_curated_room_zones(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "rooms": [
            {
                "id": "living",
                "label": "Living",
                "kind": "living",
                "bounds": {"x_min": 0.0, "z_min": 0.0, "x_max": 5.0, "z_max": 4.0},
            }
        ],
        "items": [],
    }
    assert mcp_server._save_layout(layout) is None

    result = mcp_server.design_flat(style_prompt="minimalist living room", constraints="keep circulation clear")

    assert "Rooms designed: 1" in result
    assert "zone=curated" in result

    data = mcp_server._load_layout()
    furniture = [item for item in data["items"] if item.get("type") == "furniture"]
    assert furniture
    for item in furniture:
        rect = mcp_server._item_rect(item)
        assert rect[0] >= 0.0
        assert rect[1] <= 5.0
        assert rect[2] >= 0.0
        assert rect[3] <= 4.0


def test_design_flat_respects_polygon_room_zone(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "rooms": [
            {
                "id": "living",
                "label": "Living",
                "kind": "living",
                "polygon": [
                    {"x": 0.0, "z": 0.0},
                    {"x": 5.0, "z": 0.0},
                    {"x": 5.0, "z": 2.0},
                    {"x": 3.0, "z": 2.0},
                    {"x": 3.0, "z": 4.0},
                    {"x": 0.0, "z": 4.0},
                ],
            }
        ],
        "items": [],
    }
    assert mcp_server._save_layout(layout) is None

    result = mcp_server.design_flat(style_prompt="minimalist living room", constraints="keep circulation clear")

    assert "Rooms designed: 1" in result
    data = mcp_server._load_layout()
    zone = mcp_server._find_room_zone(data, "Living")
    assert zone is not None
    assert zone.polygon is not None
    for item in data["items"]:
        assert mcp_server._item_inside_room_zone(item, zone, inset=0.0)

    area = mcp_server.compute_room_area("Living")
    assert "polygon area" in area
    assert "Area: 16.00m" in area


def test_score_layout_profiles_distinguish_accessible_warning(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "items": [
            _obj(item_type="furniture", furniture_type="wardrobe", x=0.4, z=1.0, w=1.8, h=2.0, d=0.6),
        ],
    }
    assert mcp_server._save_layout(layout) is None

    compact = mcp_server.score_layout("compact_hdb")
    accessible = mcp_server.score_layout("accessible")

    assert "Compact HDB circulation" in compact
    assert "Accessibility-oriented circulation" in accessible
    assert "0.915m" in accessible
    assert "not a code-compliance certificate" in accessible


def test_semantic_layout_json_and_bim_report(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "rooms": [
            {
                "id": "kitchen",
                "label": "Kitchen",
                "kind": "kitchen",
                "bounds": {"x_min": 0.0, "z_min": 0.0, "x_max": 3.0, "z_max": 2.0},
                "openings": [{"kind": "door", "x": 0.0, "z": 1.0, "width": 0.9}],
            }
        ],
        "items": [
            _obj(item_type="furniture", furniture_type="fridge", x=1.0, z=1.0, w=0.7, h=1.7, d=0.7),
        ],
    }
    assert mcp_server._save_layout(layout) is None

    semantic = json.loads(mcp_server.get_semantic_layout_json())
    assert semantic["schema"] == "haus.semantic_layout.v1"
    assert semantic["units"] == "meters"
    assert semantic["rooms"][0]["openings"][0]["kind"] == "door"
    assert semantic["objects"][0]["semantic_kind"] == "appliance"
    assert semantic["bim_readiness"]["not_ifc"] is True

    report = mcp_server.bim_readiness_report()
    assert "not an IFC export" in report
    assert "MEP/plumbing/electrical" in report


def test_layout_without_rooms_gets_inferred_room_zones(isolated_layout: Path) -> None:
    assert mcp_server._save_layout({"version": 1, "items": []}) is None

    result = mcp_server.design_flat(style_prompt="minimalist 4-room family flat")

    assert "zone=inferred" in result


def test_design_flat_rejects_non_whole_flat_target(isolated_layout: Path) -> None:
    assert mcp_server._save_layout({"version": 1, "items": []}) is None

    result = mcp_server.design_flat(target="one bathroom")

    assert result.startswith("Error:")


def test_design_room_rejects_partial_origin(isolated_layout: Path) -> None:
    assert mcp_server._save_layout({"version": 1, "items": []}) is None

    result = mcp_server.design_room(room_id="Study", origin_x=1.0)

    assert result.startswith("Error:")


def test_corrupt_layout_is_recovered_without_crash(isolated_layout: Path) -> None:
    isolated_layout.write_text("{ this is invalid json", encoding="utf-8")

    result = mcp_server.list_objects()
    assert "Layout is empty" in result

    backups = list(isolated_layout.parent.glob("mcp-layout.corrupt-*.json"))
    assert backups


def test_layout_normalizer_preserves_case_and_wall_classification(isolated_layout: Path) -> None:
    layout = {
        "version": 1,
        "case_id": "case-demo",
        "design_status": "awaiting_human_approval",
        "revise_count": 3,
        "compliance_findings": [
            {"rule_id": "structural_wall_protected", "element_name": "wall_28"}
        ],
        "_baseline_items": [
            {
                "type": "wall",
                "name": "wall_28",
                "pos": [1, 1.3, 1],
                "rot": 0,
                "visible": True,
                "geo": [2, 2.6, 0.3],
                "color": 7874600,
                "hdb_type": "shelter",
            }
        ],
        "items": [
            {
                "type": "wall",
                "name": "wall_0",
                "pos": [0, 1.3, 0],
                "rot": 0,
                "visible": True,
                "geo": [1, 2.6, 0.15],
                "color": 5263440,
                "hdb_type": "structural",
                "wall_type": "structural",
                "hdb_thickness_m": 0.15,
            }
        ],
    }

    assert mcp_server._save_layout(layout) is None
    loaded = mcp_server._load_layout()

    assert loaded["case_id"] == "case-demo"
    assert loaded["design_status"] == "awaiting_human_approval"
    assert loaded["compliance_findings"][0]["element_name"] == "wall_28"
    assert loaded["_baseline_items"][0]["hdb_type"] == "shelter"
    assert loaded["items"][0]["hdb_type"] == "structural"
    assert loaded["items"][0]["wall_type"] == "structural"
