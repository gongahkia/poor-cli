from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannedItem:
    furniture_type: str
    dx: float
    dz: float
    rotation_deg: float = 0.0
    name: str = ""


@dataclass(frozen=True)
class RoomPlan:
    room_id: str
    room_kind: str
    style_prompt: str
    constraints: str
    origin_x: float
    origin_z: float
    items: list[PlannedItem]
    rationale: str


ROOM_KITS: dict[str, list[PlannedItem]] = {
    "living": [
        PlannedItem("sofa_3", 0.0, 0.0, 0.0, "sofa"),
        PlannedItem("coffee", 0.0, -1.1, 0.0, "coffee table"),
        PlannedItem("tv_console", 0.0, -2.6, 0.0, "tv console"),
    ],
    "family_living": [
        PlannedItem("sofa_l", 0.0, 0.0, 0.0, "lounge sofa"),
        PlannedItem("coffee", 0.0, -1.2, 0.0, "coffee table"),
        PlannedItem("tv_console", 0.0, -2.8, 0.0, "tv console"),
    ],
    "bedroom": [
        PlannedItem("bed_queen", 0.0, 0.0, 0.0, "queen bed"),
        PlannedItem("wardrobe", -1.8, 0.8, 90.0, "wardrobe"),
        PlannedItem("bedside", 1.1, 0.0, 0.0, "bedside table"),
    ],
    "compact_bedroom": [
        PlannedItem("bed_single", 0.0, 0.0, 0.0, "single bed"),
        PlannedItem("wardrobe_s", -1.4, 0.6, 90.0, "compact wardrobe"),
        PlannedItem("desk", 1.4, 0.7, 0.0, "study desk"),
        PlannedItem("chair", 1.4, 1.3, 180.0, "desk chair"),
    ],
    "office": [
        PlannedItem("desk", 0.0, 0.0, 0.0, "work desk"),
        PlannedItem("chair", 0.0, 0.7, 180.0, "office chair"),
        PlannedItem("bookshelf", -1.4, 0.0, 0.0, "bookshelf"),
    ],
    "dining": [
        PlannedItem("dining_6", 0.0, 0.0, 0.0, "dining table"),
        PlannedItem("shoe_rack", -1.8, 0.0, 90.0, "entry shoe rack"),
    ],
    "kitchen": [
        PlannedItem("fridge", -1.4, 0.0, 0.0, "fridge"),
        PlannedItem("kitchen_counter", -0.3, 0.0, 0.0, "counter"),
        PlannedItem("sink", 0.9, 0.0, 0.0, "sink cabinet"),
        PlannedItem("washer", 2.0, 0.0, 0.0, "washer"),
    ],
}


def _tokens(*parts: str) -> str:
    return " ".join(p.lower() for p in parts if p)


def infer_room_kind(room_id: str, style_prompt: str, constraints: str) -> str:
    text = _tokens(room_id, style_prompt, constraints)
    if any(word in text for word in ("office", "study", "desk", "work", "wfh")):
        return "office"
    if any(word in text for word in ("kitchen", "cook", "laundry", "washer")):
        return "kitchen"
    if any(word in text for word in ("dining", "eat", "meal")):
        return "dining"
    if any(word in text for word in ("bedroom", "bed", "sleep", "master")):
        if any(word in text for word in ("single", "rental", "compact", "small")):
            return "compact_bedroom"
        return "bedroom"
    if any(word in text for word in ("family", "l-sofa", "l sofa", "kids")):
        return "family_living"
    return "living"


def plan_room(
    *,
    room_id: str,
    style_prompt: str,
    constraints: str,
    origin_x: float,
    origin_z: float,
) -> RoomPlan:
    clean_room = room_id.strip() or infer_room_kind(room_id, style_prompt, constraints).replace("_", " ").title()
    clean_style = style_prompt.strip() or "minimalist HDB"
    clean_constraints = constraints.strip()
    room_kind = infer_room_kind(clean_room, clean_style, clean_constraints)
    items = ROOM_KITS[room_kind]
    rationale = (
        f"Selected a {room_kind.replace('_', ' ')} kit from the room label, "
        "style prompt, and constraints."
    )
    return RoomPlan(
        room_id=clean_room,
        room_kind=room_kind,
        style_prompt=clean_style,
        constraints=clean_constraints,
        origin_x=origin_x,
        origin_z=origin_z,
        items=items,
        rationale=rationale,
    )


def plan_flat(
    *,
    style_prompt: str,
    constraints: str,
    target: str,
    bounds: tuple[float, float, float, float],
) -> list[RoomPlan]:
    x_min, z_min, x_max, z_max = bounds
    width = max(4.0, x_max - x_min)
    depth = max(4.0, z_max - z_min)
    center_x = (x_min + x_max) / 2
    center_z = (z_min + z_max) / 2

    left_x = center_x - width * 0.24
    right_x = center_x + width * 0.24
    front_z = center_z - depth * 0.24
    back_z = center_z + depth * 0.24

    text = _tokens(style_prompt, constraints, target)
    compact = any(word in text for word in ("rental", "compact", "studio", "single"))
    family = "family" in text or "4-room" in text or "4 room" in text

    rooms = [
        ("Living", "family living" if family else "living"),
        ("Dining", "dining"),
        ("Kitchen", "kitchen"),
        ("Master Bedroom", "bedroom"),
        ("Study", "office" if not compact else "compact bedroom"),
    ]
    origins = [
        (left_x, front_z),
        (right_x, front_z),
        (right_x, center_z),
        (left_x, back_z),
        (right_x, back_z),
    ]

    plans: list[RoomPlan] = []
    for (room_id, hint), (origin_x, origin_z) in zip(rooms, origins):
        plans.append(
            plan_room(
                room_id=room_id,
                style_prompt=f"{style_prompt} {hint}",
                constraints=constraints,
                origin_x=origin_x,
                origin_z=origin_z,
            )
        )
    return plans
