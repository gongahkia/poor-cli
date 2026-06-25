from __future__ import annotations

import json
import zipfile
from pathlib import Path

from haus import geometry
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
    assert validation["layout"]["rooms"][0]["occupancy"] == "unknown"
    assert validation["layout"]["items"][0]["scenario_status"] == "existing"

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
    assert duplicate["status"] == "draft"


def test_bundled_legacy_layout_fixture_migrates() -> None:
    fixture = Path(__file__).parent / "fixtures" / "layout_v1_legacy.json"
    migrated = workbench.migrate_layout(json.loads(fixture.read_text()))
    assert migrated["schema"] == workbench.LAYOUT_SCHEMA_ID
    assert migrated["layout_schema_version"] == workbench.CURRENT_LAYOUT_SCHEMA_VERSION
    assert migrated["metadata"]["calibration"]["scale_m_per_px"] == 0.02
    assert migrated["items"][0]["id"] == "item-1"
    assert migrated["items"][0]["structural_status"] == "unknown"
    assert migrated["rooms"][0]["id"] == "room-1"


def test_known_scale_floorplan_fixture_metadata() -> None:
    fixture = Path(__file__).parent / "fixtures" / "known_scale_floorplan.expected.json"
    metadata = json.loads(fixture.read_text())
    image_path = fixture.parent / metadata["fixture"]
    assert image_path.exists()
    assert metadata["known_scale_m_per_px"] > 0
    assert metadata["expected_wall_count"] >= 4
    assert metadata["expected_room_count_min"] >= 1


def test_sample_compact_apartment_renovation_report_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample_compact_apartment_renovation_report.md"
    report = fixture.read_text()
    assert "Project: Compact Apartment" in report
    assert "conservative, balanced, and ambitious" in report
    assert workbench.PRODUCT_SAFE_DISCLAIMER in report
    assert "professional verification" in report


def test_sample_designer_presales_project_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample_designer_presales_project.json"
    project = json.loads(fixture.read_text())
    assert project["journey"] == "designer"
    assert project["designer"]["client_brief"]["client_name"] == "Avery Lee"
    assert project["layout"]["schema"] == workbench.LAYOUT_SCHEMA_ID


def test_validation_report_contains_severities_overlays_unknowns_and_plain_english() -> None:
    report = workbench.build_validation_report(_layout(), journey="renovation")
    severities = {warning["severity"] for warning in report["warnings"]}
    assert {"warning", "serious"} <= severities
    assert report["severity_model"] == ["info", "warning", "serious", "blocked"]
    assert report["room_summaries"]
    assert report["confidence_explanations"] == []
    assert report["overlays"]["walkway_corridors"]
    assert report["overlays"]["blocked_areas"]
    assert report["overlays"]["product_footprints"][0]["measurement"]
    assert all(warning["explanation"] and warning["suggested_fix"] for warning in report["warnings"])

    estimated_layout = _layout()
    estimated_layout["metadata"]["calibration"]["user_confirmed"] = False
    unknowns = workbench.unknowns_for_layout(estimated_layout)
    assert any(item["field"] == "scale" for item in unknowns)
    low_confidence = workbench.build_validation_report(estimated_layout)
    assert any(item["reason"] == "missing_scale" for item in low_confidence["confidence_explanations"])


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


def test_shared_geometry_handles_rotated_room_bounds_and_door_swings() -> None:
    room = {
        "id": "living",
        "label": "Living",
        "polygon": [
            {"x": 0, "z": 0},
            {"x": 5, "z": 0},
            {"x": 5, "z": 2},
            {"x": 3, "z": 2},
            {"x": 3, "z": 4},
            {"x": 0, "z": 4},
        ],
    }
    inside = {"id": "desk", "pos": [1.5, 0.35, 1.5], "geo": [1.1, 0.7, 0.5], "rot": 0.785, "visible": True}
    outside = {"id": "sofa", "pos": [4.5, 0.4, 3.5], "geo": [1.4, 0.8, 0.8], "rot": 0.2, "visible": True}
    layout = {"rooms": [room], "items": [inside, outside]}

    assert geometry.item_inside_room(inside, room)
    assert not geometry.item_inside_room(outside, room)
    room_bound = geometry.room_bound_plan_application(layout, "Living", [inside, outside])
    assert room_bound["ok"] is False
    assert "sofa is outside Living." in room_bound["errors"]

    swing_layout = {
        "version": 1,
        "metadata": {"calibration": {"scale_m_per_px": 0.01, "user_confirmed": True}},
        "items": [
            {"id": "door", "type": "door", "name": "Bedroom door", "width_m": 0.8, "swing_direction": "in", "pos": [0, 1, 0], "geo": [0.8, 2, 0.08], "visible": True},
            {"id": "chair", "type": "furniture", "name": "Chair", "pos": [0, 0.4, 0.55], "geo": [0.5, 0.8, 0.5], "visible": True},
        ],
    }
    report = workbench.build_validation_report(swing_layout)
    assert any(warning["code"] == "door_swing_conflict" for warning in report["warnings"])


def test_validation_snapshots_and_diffs_are_project_history() -> None:
    project = workbench.new_project("Validation Diff", "accessibility", _layout())
    before = workbench.build_validation_report(_layout(), journey="accessibility", accessibility_profile="wheelchair")
    fixed = _layout()
    fixed["items"][1]["width_m"] = 1.0
    after = workbench.build_validation_report(fixed, journey="accessibility", accessibility_profile="wheelchair")

    snapshot = workbench.validation_snapshot(project, before)
    diff = workbench.diff_validation_reports(before, after)

    assert snapshot["severity_counts"]["blocked"] >= 1
    assert project["validation_snapshots"][0]["id"] == snapshot["id"]
    assert diff["after_warning_count"] <= diff["before_warning_count"]
    assert project["layout_versions"][-1]["note"] == "Validation snapshot captured"


def test_reports_filter_selected_scenarios_and_export_bundle(tmp_path: Path) -> None:
    project = workbench.new_project("Client / Path", "renovation", _layout())
    project["source_file"] = "/Users/designer/private/client-plan.png"
    applied = workbench.create_scenario("Selected", "renovation", _layout(), status="applied")
    draft = workbench.create_scenario("Unselected Draft", "renovation", _layout(), status="draft")
    project["scenarios"] = [applied, draft]
    report = workbench.build_validation_report(_layout(), journey="renovation")

    rendered = workbench.render_journey_report(project, "renovation", report, selected_ids=[applied["id"]])
    assert rendered["title"] == "Renovation Concept Pack"
    assert rendered["preview"]["selected_scenario_count"] == 1
    assert "Selected" in rendered["html"]
    assert "Unselected Draft" not in rendered["html"]
    assert "/Users/designer/private" not in rendered["html"]
    assert "[redacted]/client-plan.png" in rendered["html"]
    assert rendered["filename"].endswith(".html")

    bundle = workbench.export_project_bundle(
        project,
        tmp_path / "bundle.zip",
        reports={"renovation": rendered["html"]},
        screenshots={"selected": b"png"},
        source_images={"client-plan.png": b"image"},
        catalog_cache={"items": []},
    )
    with zipfile.ZipFile(bundle) as zf:
        assert {
            "layout.json",
            "project.json",
            "reports/renovation.html",
            "screenshots/selected.png",
            "source-images/client-plan.png",
            "catalog/cache.json",
        } <= set(zf.namelist())


def test_import_repair_manual_dimensions_and_validation_markdown() -> None:
    manual = workbench.layout_from_room_dimensions([{"label": "Office", "width_m": 3, "depth_m": 2.5}])
    assert manual["rooms"][0]["label"] == "Office"
    assert len(manual["items"]) == 4

    repaired = workbench.repair_layout({"layout_schema_version": 99, "catalog": "bad"})
    assert repaired["ok"] is True
    assert any("Missing items array" in warning for warning in repaired["warnings"])
    assert any("Unsupported schema version" in warning for warning in repaired["warnings"])

    imported = workbench.import_haus_json({"version": 1, "items": [], "scenarios": [{"id": "scenario-1"}]})
    assert imported["kind"] == "layout"
    assert imported["layout"]["scenarios"][0]["id"] == "scenario-1"

    report = workbench.build_validation_report(manual, journey="renovation")
    markdown = workbench.validation_markdown(report)
    assert "# Validation Report" in markdown
    assert workbench.PRODUCT_SAFE_DISCLAIMER in markdown
    scenario_json = json.loads(workbench.export_scenario_json(workbench.create_scenario("A", "blank", manual)))
    assert scenario_json["schema"] == "haus.scenario.v1"


def test_designer_presales_artifacts_and_client_safe_static_report(tmp_path: Path) -> None:
    project = workbench.new_project("Designer Client", "designer", _layout())
    brief = workbench.client_brief_object(
        {
            "client_name": "Avery Lee",
            "project_type": "Condo refresh",
            "design_brief": "More storage and a calmer living room",
            "style_words": "warm, minimal",
            "budget_band": "medium",
            "timeline": "8 weeks",
            "meeting_date": "2026-07-01",
        },
        selected_scenario="Base",
    )
    report = workbench.build_validation_report(_layout(), journey="designer")
    lead = workbench.lead_qualification_summary(brief, report)
    settings = workbench.branded_report_settings({"business_name": "Studio A", "contact": "hello@example.com", "accent_color": "#123abc"})
    static = workbench.designer_static_report(project, brief, settings=settings, validation_report=report)
    folder = workbench.designer_project_folder(tmp_path, brief["client_name"], project["title"])

    assert brief["client_name"] == "Avery Lee"
    assert "spatial_risks" in lead
    assert settings["accent_color"] == "#123abc"
    assert workbench.mood_board_placeholder()["status"] == "placeholder"
    assert "## Exclusions" in workbench.proposal_outline_export(brief, project["scenarios"][0])
    assert "measurements" in workbench.client_questions_export(brief)
    assert workbench.append_revision_log(project, "A", "B", "more storage")["from"] == "A"
    assert "Design Call Script" in workbench.design_call_script_export(brief, project["scenarios"])
    assert {item["id"] for item in workbench.screenshot_templates()} == {"whole_flat", "room_close_up", "warning_overlay", "selected_scenario"}
    assert "Tool-call trace" not in workbench.client_safe_text("Plan\n\nTool-call trace: hidden\n\nDone")
    assert "Studio A" in static
    assert "raw_plan" not in static
    assert (folder / "reports").exists()
