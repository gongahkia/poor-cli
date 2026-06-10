from __future__ import annotations

from haus.catalog import catalog_item_to_layout_item, get_catalog_item, search_ikea_catalog


def test_ikea_catalog_search_uses_seed_without_tinyfish(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    items = search_ikea_catalog("BILLY", max_results=5)

    assert items
    assert items[0]["source"] == "ikea"
    assert "BILLY" in items[0]["name"]
    assert get_catalog_item(items[0]["id"]) is not None


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
