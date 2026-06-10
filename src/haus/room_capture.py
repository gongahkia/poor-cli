from __future__ import annotations

import base64
import math
from typing import Any

_MAX_CAPTURE_PHOTOS = 12
_MAX_CAPTURE_PHOTO_BYTES = 5 * 1024 * 1024
_ALLOWED_CAPTURE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _num(value: Any, name: str, *, minimum: float = 0.01, maximum: float = 100.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def _packed_rgb(r: int, g: int, b: int) -> int:
    return (r << 16) | (g << 8) | b


def _photo_data_url(raw: dict[str, Any], index: int) -> tuple[str, str, str]:
    name = str(raw.get("name") or f"room-reference-{index}").strip()[:120] or f"room-reference-{index}"
    view = str(raw.get("view") or raw.get("label") or f"view_{index}").strip()[:80] or f"view_{index}"
    data_url = str(raw.get("data_url") or raw.get("dataUrl") or "").strip()
    if not data_url:
        return name, view, ""
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise ValueError(f"photo {index} must be a base64 data URL.")
    header, data = data_url.split(",", 1)
    media_type = header.removeprefix("data:").split(";", 1)[0].lower().strip()
    if media_type not in _ALLOWED_CAPTURE_IMAGE_TYPES:
        allowed = ", ".join(sorted(_ALLOWED_CAPTURE_IMAGE_TYPES))
        raise ValueError(f"photo {index} must be one of: {allowed}.")
    try:
        decoded = base64.b64decode(data, validate=True)
    except Exception as exc:
        raise ValueError(f"photo {index} contains invalid base64 data.") from exc
    if len(decoded) > _MAX_CAPTURE_PHOTO_BYTES:
        raise ValueError(f"photo {index} is larger than 5 MB.")
    return name, view, data_url


def _photo_wall(index: int, view: str) -> str:
    text = view.lower()
    for wall in ("north", "east", "south", "west"):
        if wall in text:
            return wall
    return ("north", "east", "south", "west")[index % 4]


def _wall_item(name: str, wall: str, width: float, depth: float, height: float, thickness: float) -> dict[str, Any]:
    if wall == "north":
        return {
            "type": "wall",
            "name": name,
            "pos": [0.0, height / 2, -depth / 2],
            "rot": 0.0,
            "visible": True,
            "geo": [width, height, thickness],
            "color": _packed_rgb(118, 118, 118),
            "wall_type": "partition",
            "hdb_type": "partition",
        }
    if wall == "south":
        return {
            "type": "wall",
            "name": name,
            "pos": [0.0, height / 2, depth / 2],
            "rot": 0.0,
            "visible": True,
            "geo": [width, height, thickness],
            "color": _packed_rgb(118, 118, 118),
            "wall_type": "partition",
            "hdb_type": "partition",
        }
    x = -width / 2 if wall == "west" else width / 2
    return {
        "type": "wall",
        "name": name,
        "pos": [x, height / 2, 0.0],
        "rot": round(math.pi / 2, 6),
        "visible": True,
        "geo": [depth, height, thickness],
        "color": _packed_rgb(118, 118, 118),
        "wall_type": "partition",
        "hdb_type": "partition",
    }


def _photo_panel(
    *,
    index: int,
    name: str,
    view: str,
    data_url: str,
    width: float,
    depth: float,
    height: float,
) -> dict[str, Any]:
    wall = _photo_wall(index, view)
    inset = 0.018
    if wall in {"north", "south"}:
        z = -depth / 2 + inset if wall == "north" else depth / 2 - inset
        rot = 0.0 if wall == "north" else math.pi
        geo = [width * 0.96, height * 0.72, 0.01]
        pos = [0.0, height * 0.50, z]
    else:
        x = -width / 2 + inset if wall == "west" else width / 2 - inset
        rot = math.pi / 2 if wall == "west" else -math.pi / 2
        geo = [depth * 0.96, height * 0.72, 0.01]
        pos = [x, height * 0.50, 0.0]
    return {
        "type": "reference_image",
        "name": f"room_photo_{index}_{wall}",
        "label": name,
        "source_view": view,
        "pos": [round(v, 4) for v in pos],
        "rot": round(rot, 6),
        "visible": True,
        "geo": [round(v, 4) for v in geo],
        "color": _packed_rgb(240, 240, 240),
        "texture_data_url": data_url,
    }


def _opening_item(raw: dict[str, Any], index: int, width: float, depth: float, height: float) -> dict[str, Any]:
    wall = str(raw.get("wall") or "north").strip().lower()
    if wall not in {"north", "south", "east", "west"}:
        raise ValueError(f"opening {index} wall must be north/south/east/west.")
    kind = str(raw.get("kind") or "opening").strip().lower()
    if kind not in {"door", "window", "opening"}:
        raise ValueError(f"opening {index} kind must be door/window/opening.")
    opening_w = _num(raw.get("width_m", raw.get("width", 0.9)), f"opening {index} width", maximum=8.0)
    opening_h = _num(raw.get("height_m", raw.get("height", 2.1 if kind == "door" else 1.2)), f"opening {index} height", maximum=5.0)
    sill = _num(raw.get("sill_m", raw.get("bottom_m", 0.0 if kind == "door" else 0.9)), f"opening {index} sill", minimum=0.0, maximum=height)
    max_offset = width / 2 if wall in {"north", "south"} else depth / 2
    offset = _num(raw.get("offset_m", raw.get("offset", 0.0)), f"opening {index} offset", minimum=-max_offset, maximum=max_offset)
    y = min(height - opening_h / 2, sill + opening_h / 2)
    color = _packed_rgb(120, 170, 210) if kind == "window" else _packed_rgb(142, 102, 72)
    if wall in {"north", "south"}:
        z = -depth / 2 - 0.004 if wall == "north" else depth / 2 + 0.004
        rot = 0.0
        geo = [opening_w, opening_h, 0.025]
        pos = [offset, y, z]
    else:
        x = -width / 2 - 0.004 if wall == "west" else width / 2 + 0.004
        rot = math.pi / 2
        geo = [opening_w, opening_h, 0.025]
        pos = [x, y, offset]
    return {
        "type": "model_part",
        "name": f"{kind}_{index}_{wall}",
        "pos": [round(v, 4) for v in pos],
        "rot": round(rot, 6),
        "visible": True,
        "geo": [round(v, 4) for v in geo],
        "color": color,
        "room_capture_opening": {"kind": kind, "wall": wall, "offset_m": offset},
    }


def build_room_capture_layout(payload: dict[str, Any]) -> dict[str, Any]:
    measurements_raw = payload.get("measurements")
    measurements: dict[str, Any] = measurements_raw if isinstance(measurements_raw, dict) else payload
    width = _num(measurements.get("width_m", measurements.get("width")), "width_m", maximum=50.0)
    depth = _num(measurements.get("depth_m", measurements.get("depth")), "depth_m", maximum=50.0)
    height = _num(measurements.get("height_m", measurements.get("height", 2.6)), "height_m", minimum=1.8, maximum=8.0)
    thickness = _num(measurements.get("wall_thickness_m", 0.10), "wall_thickness_m", minimum=0.02, maximum=0.5)

    items: list[dict[str, Any]] = [
        {
            "type": "model_part",
            "name": "captured_room_floor",
            "pos": [0.0, -0.015, 0.0],
            "rot": 0.0,
            "visible": True,
            "geo": [round(width, 4), 0.03, round(depth, 4)],
            "color": _packed_rgb(214, 205, 190),
        },
        _wall_item("captured_wall_north", "north", width, depth, height, thickness),
        _wall_item("captured_wall_east", "east", width, depth, height, thickness),
        _wall_item("captured_wall_south", "south", width, depth, height, thickness),
        _wall_item("captured_wall_west", "west", width, depth, height, thickness),
    ]

    photos = payload.get("photos", [])
    if photos is None:
        photos = []
    if not isinstance(photos, list):
        raise ValueError("photos must be a list.")
    if len(photos) > _MAX_CAPTURE_PHOTOS:
        raise ValueError(f"At most {_MAX_CAPTURE_PHOTOS} room photos can be attached.")

    normalized_photos: list[dict[str, Any]] = []
    for idx, raw_photo in enumerate(photos):
        if not isinstance(raw_photo, dict):
            raise ValueError(f"photo {idx + 1} must be an object.")
        name, view, data_url = _photo_data_url(raw_photo, idx + 1)
        normalized_photos.append({"name": name, "view": view, "has_image": bool(data_url)})
        if data_url:
            items.append(_photo_panel(index=idx, name=name, view=view, data_url=data_url, width=width, depth=depth, height=height))

    openings = payload.get("openings", [])
    if openings in (None, ""):
        openings = []
    if not isinstance(openings, list):
        raise ValueError("openings must be a list.")
    for idx, opening in enumerate(openings, start=1):
        if not isinstance(opening, dict):
            raise ValueError(f"opening {idx} must be an object.")
        items.append(_opening_item(opening, idx, width, depth, height))

    return {
        "version": 1,
        "metadata": {
            "name": str(payload.get("name") or "Captured room"),
            "source": "room_capture",
            "capture_method": "guided_measurements",
            "units": "meters",
            "measurement_confidence": "user_supplied",
            "notes": [
                "Guided room shell from user measurements and reference photos.",
                "Not photogrammetry or construction-grade survey data.",
            ],
        },
        "rooms": [
            {
                "id": "captured_room",
                "label": "Captured Room",
                "kind": "room",
                "bounds": {
                    "x_min": round(-width / 2, 4),
                    "z_min": round(-depth / 2, 4),
                    "x_max": round(width / 2, 4),
                    "z_max": round(depth / 2, 4),
                },
            }
        ],
        "items": items,
        "room_capture": {
            "schema": "haus.room_capture.v1",
            "measurements": {
                "width_m": width,
                "depth_m": depth,
                "height_m": height,
                "wall_thickness_m": thickness,
            },
            "photos": normalized_photos,
        },
    }
