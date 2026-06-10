from __future__ import annotations

import base64

import pytest

from haus.room_capture import build_room_capture_layout


def _data_url() -> str:
    data = base64.b64encode(b"fake-png").decode("ascii")
    return f"data:image/png;base64,{data}"


def test_room_capture_builds_measured_shell_with_photo_and_opening() -> None:
    layout = build_room_capture_layout(
        {
            "measurements": {"width_m": 3.6, "depth_m": 3.2, "height_m": 2.6},
            "photos": [{"name": "north.png", "view": "north", "data_url": _data_url()}],
            "openings": [{"kind": "door", "wall": "south", "offset_m": 0, "width_m": 0.9}],
        }
    )

    assert layout["metadata"]["source"] == "room_capture"
    assert layout["room_capture"]["measurements"]["width_m"] == 3.6
    assert len(layout["items"]) == 7
    assert any(item["type"] == "reference_image" for item in layout["items"])
    assert any(item.get("room_capture_opening", {}).get("kind") == "door" for item in layout["items"])


def test_room_capture_rejects_bad_measurements() -> None:
    with pytest.raises(ValueError, match="width_m"):
        build_room_capture_layout({"measurements": {"width_m": 0, "depth_m": 3, "height_m": 2.6}})
