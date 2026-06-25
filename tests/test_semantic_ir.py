from __future__ import annotations

import json

from haus import semantic_ir
from haus.constraints import get_constraint_pack, list_constraint_packs


def _layout() -> dict:
    return {
        "version": 1,
        "metadata": {"calibration": {"confidence": "estimated", "user_confirmed": False}},
        "rooms": [
            {
                "id": "living",
                "label": "Living",
                "kind": "living",
                "bounds": {"x_min": 0, "z_min": 0, "x_max": 3, "z_max": 3},
                "openings": [{"id": "living-kitchen", "type": "opening", "width_m": 0.9, "connects_to": ["kitchen"]}],
            },
            {
                "id": "kitchen",
                "label": "Kitchen",
                "kind": "kitchen",
                "bounds": {"x_min": 3, "z_min": 0, "x_max": 5, "z_max": 3},
            },
        ],
        "items": [
            {"id": "entry", "type": "door", "width_m": 0.68, "pos": [0, 1, 1.5], "geo": [0.68, 2, 0.08], "rot": 0, "visible": True},
            {"id": "wall-1", "type": "wall", "structural_status": "unknown", "pos": [3, 1.3, 1.5], "geo": [0.15, 2.6, 3], "rot": 0, "visible": True},
            {"id": "sofa", "type": "furniture", "furnitureType": "sofa_3", "room": "Living", "pos": [1, 0.4, 1.4], "geo": [2.1, 0.8, 0.9], "rot": 0, "visible": True},
            {"id": "coffee", "type": "furniture", "furnitureType": "coffee", "room": "Living", "pos": [1, 0.2, 1.95], "geo": [1.0, 0.4, 0.5], "rot": 0, "visible": True},
        ],
    }


def test_constraint_packs_are_discoverable() -> None:
    packs = list_constraint_packs()
    ids = {pack["id"] for pack in packs}
    assert {"compact_hdb", "furniture_fit", "agent_guardrails"} <= ids
    assert get_constraint_pack("compact_hdb")["schema"] == "haus.constraint_pack.v1"


def test_layout_graph_contains_rooms_edges_zones_and_findings() -> None:
    graph = semantic_ir.build_layout_graph(_layout(), ["compact_hdb", "agent_guardrails"])
    assert graph["schema"] == semantic_ir.LAYOUT_GRAPH_SCHEMA_ID
    assert {room["id"] for room in graph["rooms"]} == {"living", "kitchen"}
    assert graph["adjacency"]
    assert any(zone["room_id"] == "living" and "sit" in zone["affordances"] for zone in graph["zones"])
    codes = {finding["code"] for finding in graph["findings"]}
    assert {"missing_or_estimated_scale", "doorway_width", "structural_unknown", "tight_clearance"} <= codes


def test_reasoning_report_and_semantic_layout_are_agent_ready() -> None:
    report = semantic_ir.reasoning_report(_layout(), ["compact_hdb", "agent_guardrails"])
    assert report["status"] in {"blocked", "needs_revision"}
    assert report["agent_next_actions"]

    semantic = semantic_ir.build_semantic_layout(_layout())
    assert semantic["schema"] == semantic_ir.SEMANTIC_SCHEMA_ID
    assert "circulation" in semantic
    assert semantic["reasoning"]["findings"]


def test_scenario_transaction_applies_and_reverts() -> None:
    before = _layout()
    after = json.loads(json.dumps(before))
    after["items"].append(
        {"id": "desk", "type": "furniture", "furnitureType": "desk", "room": "Living", "pos": [2.2, 0.375, 2.2], "geo": [1.2, 0.75, 0.6], "rot": 0, "visible": True}
    )
    txn = semantic_ir.scenario_transaction(before, after, intent="add work surface")
    assert txn["schema"] == semantic_ir.SCENARIO_PATCH_SCHEMA_ID
    assert txn["diff"]["change_counts"]["add"] == 1
    applied = semantic_ir.apply_scenario_patch(before, txn)
    assert any(item["id"] == "desk" for item in applied["items"])
    reverted = semantic_ir.revert_scenario_patch(applied, txn)
    assert not any(item["id"] == "desk" for item in reverted["items"])


def test_multimodal_contract_schema_catalog_and_evals() -> None:
    contract = semantic_ir.multimodal_intake_contract()
    assert contract["schema"] == semantic_ir.MULTIMODAL_INTAKE_SCHEMA_ID
    assert any(entry["kind"] == "floorplan_image" for entry in contract["accepted_inputs"])

    catalog = semantic_ir.schema_catalog()
    assert semantic_ir.LAYOUT_GRAPH_SCHEMA_ID in catalog["schemas"]

    report = semantic_ir.run_agent_eval_suite()
    assert report["failed"] == 0
    assert report["metrics"]["expected_finding_recall"] == 1.0
