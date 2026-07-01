from __future__ import annotations

from haus.catalog import catalog_item_to_layout_item, catalog_search_meta, get_catalog_item, search_furniture_catalog, search_ikea_catalog


def test_ikea_catalog_search_uses_seed_without_tinyfish(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    items = search_ikea_catalog("BILLY", max_results=5)

    assert items
    assert items[0]["source"] == "ikea"
    assert "BILLY" in items[0]["name"]
    assert items[0]["clearance_rules"]
    assert items[0]["delivery_constraints"]["checkpoints"]
    assert items[0]["provenance"]["provider"] == "seed"
    assert "verified" in items[0]["stale_warning"].lower()
    assert get_catalog_item(items[0]["id"]) is not None


def test_furniture_catalog_search_uses_non_ikea_seed_without_tinyfish(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    items = search_furniture_catalog("sofa", max_results=5, sources="wayfair")

    assert items
    assert items[0]["source"] == "wayfair"
    assert items[0]["source_provider"] == "seed"


def test_furniture_catalog_refresh_uses_cache_and_seed_for_selected_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))

    items = search_furniture_catalog("sofa", max_results=5, sources="wayfair", refresh=True)
    meta = catalog_search_meta(items, refresh=True)

    assert items
    assert items[0]["source"] == "wayfair"
    assert items[0]["source_provider"] == "seed"
    assert meta["fallback_used"] is True
    assert meta["live_result_count"] == 0


def test_catalog_item_becomes_layout_furniture() -> None:
    item = {
        "id": "ikea-test-desk",
        "name": "Test desk",
        "category": "desk",
        "dimensions_m": {"width": 1.2, "height": 0.75, "depth": 0.6},
        "product_url": "https://www.ikea.com/sg/en/",
        "price": 99,
        "currency": "SGD",
    }

    layout_item = catalog_item_to_layout_item(item, x=1.0, z=2.0, rotation_deg=90)

    assert layout_item["type"] == "furniture"
    assert layout_item["furnitureType"] == "ikea:ikea-test-desk"
    assert layout_item["geo"] == [1.2, 0.75, 0.6]
    assert layout_item["catalog"]["price"] == 99
    assert "clearance_rules" in layout_item["catalog"]


def test_catalog_supports_accessibility_and_renovation_placeholder_categories(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    shower = search_ikea_catalog("shower chair", max_results=5)[0]
    partition = search_ikea_catalog("sliding door partition", max_results=5)[0]

    assert shower["category"] == "shower_chair"
    assert shower["clearance_rules"]["transfer_clearance_m"] >= 0.75
    assert partition["category"] in {"sliding_door", "partition"}
    assert partition["delivery_constraints"]["requires_manual_measurement"] is True


def test_ikea_catalog_refresh_uses_seed_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))

    items = search_ikea_catalog("BILLY", max_results=5, refresh=True)
    meta = catalog_search_meta(items, refresh=True)

    assert items
    assert items[0]["source_provider"] == "seed"
    assert meta["fallback_used"] is True
    assert meta["live_result_count"] == 0
