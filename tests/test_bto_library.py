from __future__ import annotations

import json
from pathlib import Path


def test_bto_layout_library_has_four_editor_json_layouts() -> None:
    library_dir = Path("corpus/library")
    layouts = sorted(library_dir.glob("*.json"))

    assert len(layouts) >= 4

    for path in layouts:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["metadata"]["name"]
        assert data["metadata"]["source"].startswith("corpus/cleaned/")
        assert data["metadata"]["wall_count"] > 0
        assert len(data["items"]) == data["metadata"]["wall_count"]
        assert data["rooms"]
        for room in data["rooms"]:
            assert room["id"]
            assert room["label"]
            assert room["kind"]
            bounds = room["bounds"]
            assert bounds["x_min"] < bounds["x_max"]
            assert bounds["z_min"] < bounds["z_max"]

        first = data["items"][0]
        assert first["type"] == "wall"
        assert len(first["pos"]) == 3
        assert len(first["geo"]) == 3
        assert first["geo"][1] == 2.6
