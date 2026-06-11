from __future__ import annotations

import json
from pathlib import Path

from haus import workbench


def _layout() -> dict:
    return {
        "version": 1,
        "metadata": {
            "source_filename": "sample-plan.png",
            "calibration": {
                "scale_m_per_px": 0.01,
                "confidence": "confirmed",
                "user_confirmed": True,
            },
        },
        "rooms": [
            {
                "id": "living",
                "label": "Living",
                "kind": "living",
                "bounds": {"x_min": -2.5, "z_min": -2.0, "x_max": 2.5, "z_max": 2.0},
            },
            {
                "id": "bedroom",
                "label": "Bedroom",
                "kind": "bedroom",
                "bounds": {"x_min": 3.0, "z_min": -2.0, "x_max": 6.0, "z_max": 2.0},
            },
        ],
        "items": [
            {
                "id": "wall-1",
                "type": "wall",
                "pos": [0.0, 1.3, -2.1],
                "geo": [5.0, 2.6, 0.15],
                "rot": 0,
                "visible": True,
            },
            {
                "id": "entry-door",
                "type": "door",
                "name": "Entry door",
                "width_m": 0.7,
                "swing_direction": "in",
                "pos": [-2.0, 1.0, 0.0],
                "geo": [0.7, 2.0, 0.08],
                "rot": 0,
                "visible": True,
            },
            {
                "id": "sofa",
                "type": "furniture",
                "furnitureType": "sofa_3",
                "room": "Living",
                "pos": [0.0, 0.4, 0.0],
                "geo": [2.1, 0.8, 0.9],
                "rot": 0,
                "visible": True,
                "locked": True,
            },
            {
                "id": "coffee",
                "type": "furniture",
                "furnitureType": "coffee",
                "room": "Living",
                "pos": [0.0, 0.2, 0.55],
                "geo": [1.0, 0.4, 0.5],
                "rot": 0,
                "visible": True,
            },
            {
                "id": "bed",
                "type": "furniture",
                "furnitureType": "bed_queen",
                "room": "Bedroom",
                "pos": [4.0, 0.3, 0.0],
                "geo": [1.52, 0.6, 2.03],
                "rot": 0,
                "visible": True,
            },
            {
                "id": "wardrobe",
                "type": "furniture",
                "furnitureType": "wardrobe",
                "room": "Bedroom",
                "pos": [5.0, 1.0, 0.0],
                "geo": [1.2, 2.0, 0.6],
                "rot": 0,
                "visible": True,
            },
            {
                "id": "rug",
                "type": "furniture",
                "furnitureType": "rug",
                "hazard": True,
                "room": "Living",
                "pos": [1.4, 0.02, 0.0],
                "geo": [1.0, 0.04, 1.0],
                "rot": 0,
                "visible": True,
            },
            {
                "id": "toilet",
                "type": "furniture",
                "furnitureType": "toilet",
                "room": "Bathroom",
                "pos": [6.5, 0.2, 0.0],
                "geo": [0.4, 0.4, 0.7],
                "rot": 0,
                "visible": True,
            },
        ],
    }


def test_layout_migration_validation_and_project_model() -> None:
    layout = workbench.migrate_layout({"version": 1, "items": [], "metadata": {"scale_m_per_px": 0.02}})
    assert layout["schema"] == workbench.LAYOUT_SCHEMA_ID
    assert layout["layout_schema_version"] == workbench.CURRENT_LAYOUT_SCHEMA_VERSION
    assert layout["metadata"]["calibration"]["scale_m_per_px"] == 0.02

    validation = workbench.validate_layout_schema(_layout())
    assert validation["ok"] is True
    assert validation["layout"]["items"][0]["structural_status"] == "unknown"

    project = workbench.new_project("Real Home", "renovation", _layout())
    assert project["title"] == "Real Home"
    assert project["journey"] == "renovation"
    assert project["source_file"] == "sample-plan.png"
    assert project["layout_versions"][0]["status"] == "draft"
    assert project["scenarios"][0]["name"] == "Base"

    applied = workbench.capture_project_version(project, "applied", _layout(), note="Selected option")
    assert applied["status"] == "applied"
    duplicate = workbench.duplicate_scenario(project["scenarios"][0], "Branch A")
    assert duplicate["parent_scenario_id"] == project["scenarios"][0]["id"]
    assert duplicate["name"] == "Branch A"


def test_validation_report_contains_severities_overlays_unknowns_and_plain_english() -> None:
    report = workbench.build_validation_report(_layout(), journey="renovation")
    severities = {warning["severity"] for warning in report["warnings"]}
    assert {"warning", "serious"} <= severities
    assert report["severity_model"] == ["info", "warning", "serious", "blocked"]
    assert report["room_summaries"]
    assert report["overlays"]["walkway_corridors"]
    assert report["overlays"]["blocked_areas"]
    assert report["overlays"]["product_footprints"][0]["measurement"]
    assert all(warning["explanation"] and warning["suggested_fix"] for warning in report["warnings"])

    estimated_layout = _layout()
    estimated_layout["metadata"]["calibration"]["user_confirmed"] = False
    unknowns = workbench.unknowns_for_layout(estimated_layout)
    assert any(item["field"] == "scale" for item in unknowns)


def test_command_router_prompts_and_llm_badge() -> None:
    assert workbench.command_route("draft a plan") == "draft_plan"
    assert workbench.command_route("make it cheaper") == "revise_plan"
    assert workbench.command_route("apply this scenario") == "apply_plan"
    assert workbench.command_route("validate the bathroom") == "validate_layout"
    assert workbench.command_route("export report") == "export_report"
    assert workbench.command_route("move the sofa") == "edit_object"
    prompt = workbench.journey_system_prompt("accessibility", {"country": "US"})
    assert "Accessibility Checker" in prompt
    assert "not ADA certification" in prompt
    assert workbench.llm_review_badge({"mode": "llm_reviewed", "provider_reviewed": True}) == "LLM reviewed"
    assert workbench.llm_review_badge({"mode": "llm_reviewed"}) == "Deterministic"


def test_renovation_scenarios_are_drafts_and_wall_changes_are_guarded() -> None:
    base = _layout()
    original = json.dumps(base, sort_keys=True)
    scenarios = workbench.renovation_scenarios(base, {"allowed_wall_changes": "exploratory_concept"})
    assert [scenario["name"] for scenario in scenarios] == ["conservative", "balanced", "ambitious"]
    assert json.dumps(base, sort_keys=True) == original
    assert scenarios[1]["proposed_wall_changes"][0]["concept_only"] is True
    assert scenarios[1]["proposed_wall_changes"][0]["requires_professional_verification"] is True
    assert scenarios[0]["scores"]["likely_cost_tier"] == "low"
    assert scenarios[0]["storage_plan"]["zones"]
    assert scenarios[0]["kitchen_work_zone"]["status"] in {"needs_inputs", "review_clearances"}
    assert scenarios[0]["bathroom_clearance"]["status"] in {"needs_inputs", "review_clearances"}
    assert scenarios[2]["open_plan_concepts"][0]["concept_only"] is True
    assert scenarios[2]["room_reassignments"]
    assert scenarios[2]["before_after_annotations"]
    assert scenarios[2]["fixed_service_zones"]
    assert scenarios[2]["materials_and_finishes"]["status"] == "placeholder"
    assert "exact prices" in workbench.cost_tier_explanation("high")

    blocked = workbench.apply_renovation_scenario(base, scenarios[1])
    assert blocked["blocked"] is True
    applied = workbench.apply_renovation_scenario(base, scenarios[1], confirm_wall_changes=True)
    assert applied["ok"] is True
    sanity = workbench.renovation_sanity_check(scenarios[1])
    assert sanity["issues"]
    revised = workbench.revise_renovation_scenario(scenarios[1], "make it cheaper and more storage")
    assert revised["status"] == "revised"
    assert revised["cost_tier"] == "low"


def test_renovation_scope_brief_includes_professional_boundaries() -> None:
    project = workbench.new_project("Compact Apartment", "renovation", _layout())
    scenario = workbench.renovation_scenarios(_layout())[0]
    brief = workbench.renovation_scope_brief(project, scenario)
    assert "# Renovation Scope Brief" in brief
    assert "concept-only" in brief
    assert "Which walls are confirmed non-structural?" in brief


def test_accessibility_report_checks_and_sources() -> None:
    report = workbench.accessibility_report(_layout(), "wheelchair")
    assert report["title"] == "Home Accessibility Planning Review"
    assert workbench.ACCESSIBILITY_DISCLAIMER in report["disclaimers"]
    assert any(source["source_type"] == "practical_guidance" for source in report["standards_sources"])
    assert any(source["source_type"] == "formal_code_inspired_screening" for source in report["standards_sources"])
    codes = {warning["code"] for warning in report["warnings"]}
    assert "doorway_width" in codes
    assert "path_clearance" in codes or "overlap" in codes
    assert "bed_transfer" in codes
    assert "toilet_transfer" in codes
    assert "trip_hazard" in codes
    assert "lighting_recommendation" in codes
    assert report["fix_list"]["renovate"]
    assert report["quick_wins"]
    assert report["ask_a_professional"]
    assert report["caregiver_routes"][0]["label"].startswith("caregiver-assisted")
    assert report["night_route"]["label"] == "night route from bed to bathroom"
    assert len(report["bathroom_safety_checklist"]) == 4
    examples = workbench.accessible_fixture_examples()
    assert examples["bedroom"]
    assert examples["bathroom"]


def test_furniture_dimension_model_fit_and_exports(tmp_path: Path) -> None:
    dims = workbench.parse_product_dimensions("Width 210 cm Depth 95 cm Height 80 cm")
    assert dims == {"width_m": 2.1, "depth_m": 0.95, "height_m": 0.8}

    product = workbench.manual_product_entry(
        {
            "name": "Large sofa",
            "width_m": 2.4,
            "depth_m": 1.1,
            "height_m": 0.8,
            "clearance_need_m": 0.7,
            "source_confidence": "estimated",
            "price": 1200,
            "retailer": "Example",
        }
    )
    assert product["source_confidence"] == "estimated"
    card = workbench.product_card(product, {"status": "fails"})
    assert card["fit_status"] == "fails"
    assert "2.40m" in card["dimensions"]

    fit = workbench.check_product_fit(_layout(), product, "Living")
    assert fit["status"] in {"fits", "fails"}
    assert fit["all_orientations"]
    path = workbench.delivery_path_check(_layout(), product)
    assert path["checkpoints"] == ["entry door", "corridor", "bedroom door", "elevator placeholder", "stair placeholder"]
    assert path["overlays"][0]["type"] == "delivery_path"
    assert workbench.assembly_clearance(product)["required_clearance_m"] >= 0.6
    assert workbench.pullout_clearance({"category": "wardrobe", **product})["required_clearance_m"] >= 0.75

    catalog = [
        product,
        workbench.manual_product_entry({"name": "Smaller sofa", "width_m": 1.8, "depth_m": 0.8, "height_m": 0.8, "category": "sofa"}),
    ]
    catalog[0]["category"] = "sofa"
    catalog[1]["category"] = "sofa"
    assert workbench.suggest_substitutes(catalog[0], catalog)
    comparison = workbench.compare_product_alternatives(catalog, _layout())
    assert {"name", "fit_score", "clearance_risk"} <= set(comparison[0])

    shopping = workbench.shopping_list_export(catalog, {product["id"]: fit})
    assert "Product,Width m,Depth m,Height m,Quantity,Source URL,Fit notes" in shopping
    assert "Large sofa" in shopping
    assert workbench.buy_nothing_yet_warning(_layout(), product)
    assert workbench.room_layout_optimizer("bedroom")
    assert workbench.budget_estimate(catalog)["known_total"] == 1200
    assert workbench.measurement_checklist(_layout(), catalog)

    cache_path = tmp_path / "catalog" / "products.json"
    workbench.save_product_cache(cache_path, catalog)
    assert workbench.load_product_cache(cache_path)[0]["name"] == "Large sofa"


def test_html_report_includes_builder_options_and_print_fallback() -> None:
    project = workbench.new_project("Report Project", "accessibility", _layout())
    report = workbench.accessibility_report(_layout(), "walker")
    html = workbench.build_html_report(
        project,
        report,
        include_assumptions=True,
        include_warnings=True,
        include_shopping_list=False,
        include_scenarios=True,
        include_images=True,
    )
    assert "Report Project" in html
    assert "Print / Save PDF" in html
    assert workbench.PRODUCT_SAFE_DISCLAIMER in html
    record = workbench.report_export_record("html", "report.html")
    assert record["disclaimer"] == workbench.PRODUCT_SAFE_DISCLAIMER
