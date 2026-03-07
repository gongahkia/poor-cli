"""MCP server for haus floor plan editor.

Exposes tools for AI assistants to manipulate the floor plan layout.
Reads/writes a JSON layout file that the browser editor can import.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from mcp.server import FastMCP

LAYOUT_PATH = Path("viewer/mcp-layout.json")
FURNITURE_CATALOG = {
    "bed_single":      {"w": 0.9,  "h": 0.5,  "d": 1.9, "color": 0x88bbee},
    "bed_queen":       {"w": 1.5,  "h": 0.55, "d": 2.0, "color": 0x77aadd},
    "bed_king":        {"w": 1.8,  "h": 0.55, "d": 2.0, "color": 0x6699cc},
    "wardrobe":        {"w": 1.8,  "h": 2.0,  "d": 0.6, "color": 0x4A3728},
    "wardrobe_s":      {"w": 0.9,  "h": 2.0,  "d": 0.6, "color": 0x5A4738},
    "bedside":         {"w": 0.5,  "h": 0.5,  "d": 0.4, "color": 0x8B7355},
    "dresser":         {"w": 1.2,  "h": 0.8,  "d": 0.5, "color": 0x7A6245},
    "sofa_2":          {"w": 1.5,  "h": 0.8,  "d": 0.8, "color": 0x555555},
    "sofa_3":          {"w": 2.2,  "h": 0.8,  "d": 0.9, "color": 0x4a4a4a},
    "sofa_l":          {"w": 2.2,  "h": 0.8,  "d": 1.6, "color": 0x505050},
    "coffee":          {"w": 1.0,  "h": 0.4,  "d": 0.5, "color": 0x6B4226},
    "tv_console":      {"w": 1.5,  "h": 0.5,  "d": 0.4, "color": 0x3a3a3a},
    "dining_4":        {"w": 1.2,  "h": 0.75, "d": 0.8, "color": 0x8B6914},
    "dining_6":        {"w": 1.6,  "h": 0.75, "d": 0.9, "color": 0x8B6914},
    "shoe_rack":       {"w": 0.8,  "h": 1.0,  "d": 0.3, "color": 0x5C4033},
    "fridge":          {"w": 0.7,  "h": 1.7,  "d": 0.7, "color": 0xcccccc},
    "washer":          {"w": 0.6,  "h": 0.85, "d": 0.6, "color": 0xdddddd},
    "kitchen_counter": {"w": 1.2,  "h": 0.9,  "d": 0.6, "color": 0x888888},
    "sink":            {"w": 0.8,  "h": 0.85, "d": 0.6, "color": 0x999999},
    "toilet":          {"w": 0.4,  "h": 0.4,  "d": 0.7, "color": 0xeeeeee},
    "shower":          {"w": 0.9,  "h": 2.0,  "d": 0.9, "color": 0xaaddee},
    "desk":            {"w": 1.2,  "h": 0.75, "d": 0.6, "color": 0xD2B48C},
    "desk_l":          {"w": 1.6,  "h": 0.75, "d": 1.2, "color": 0xC4A882},
    "bookshelf":       {"w": 0.8,  "h": 1.8,  "d": 0.3, "color": 0x5A4020},
    "chair":           {"w": 0.5,  "h": 0.45, "d": 0.5, "color": 0x333333},
}

mcp = FastMCP(
    "haus-editor",
    instructions=(
        "You are an AI assistant for the haus floor plan editor. "
        "Use the provided tools to add, move, remove, and query furniture "
        "and walls in the user's floor plan layout. Coordinates are in meters. "
        "X is left-right, Z is forward-back. Y is vertical (height)."
    ),
)


def _load_layout() -> dict:
    if LAYOUT_PATH.exists():
        return json.loads(LAYOUT_PATH.read_text())
    return {"version": 1, "items": []}


def _save_layout(data: dict) -> None:
    LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAYOUT_PATH.write_text(json.dumps(data, indent=2))


@mcp.tool()
def list_furniture_catalog() -> str:
    """List all available furniture types with their dimensions."""
    lines = []
    for name, spec in FURNITURE_CATALOG.items():
        lines.append(f"  {name}: {spec['w']}m x {spec['d']}m (height {spec['h']}m)")
    return "Available furniture types:\n" + "\n".join(lines)


@mcp.tool()
def list_objects() -> str:
    """List all objects currently in the layout with their index, type, and position."""
    data = _load_layout()
    if not data["items"]:
        return "Layout is empty. No objects placed yet."
    lines = []
    for i, item in enumerate(data["items"]):
        t = item.get("furnitureType") or item.get("type", "object")
        p = item["pos"]
        rot = math.degrees(item.get("rot", 0))
        vis = "visible" if item.get("visible", True) else "hidden"
        lines.append(f"  [{i}] {t} at ({p[0]:.2f}, {p[2]:.2f}) rot={rot:.0f}° {vis}")
    return f"Layout has {len(data['items'])} objects:\n" + "\n".join(lines)


@mcp.tool()
def add_furniture(furniture_type: str, x: float = 0.0, z: float = 0.0, rotation_deg: float = 0.0) -> str:
    """Add a furniture item to the layout.

    Args:
        furniture_type: Type from catalog (e.g., 'bed_queen', 'sofa_3', 'desk').
        x: X position in meters.
        z: Z position in meters.
        rotation_deg: Rotation in degrees (0, 90, 180, 270).
    """
    if furniture_type not in FURNITURE_CATALOG:
        return f"Error: unknown type '{furniture_type}'. Use list_furniture_catalog() to see options."
    spec = FURNITURE_CATALOG[furniture_type]
    data = _load_layout()
    item = {
        "type": "furniture",
        "furnitureType": furniture_type,
        "pos": [x, spec["h"] / 2, z],
        "rot": math.radians(rotation_deg),
        "visible": True,
        "geo": [spec["w"], spec["h"], spec["d"]],
        "color": spec["color"],
    }
    data["items"].append(item)
    _save_layout(data)
    idx = len(data["items"]) - 1
    return f"Added {furniture_type} at ({x}, {z}) as item [{idx}]."


@mcp.tool()
def add_wall(x1: float, z1: float, x2: float, z2: float, height: float = 2.6, thickness: float = 0.15) -> str:
    """Add a wall segment between two points.

    Args:
        x1: Start X in meters.
        z1: Start Z in meters.
        x2: End X in meters.
        z2: End Z in meters.
        height: Wall height in meters (default 2.6).
        thickness: Wall thickness in meters (default 0.15).
    """
    dx, dz = x2 - x1, z2 - z1
    length = math.sqrt(dx * dx + dz * dz)
    if length < 0.01:
        return "Error: wall too short (start and end points are the same)."
    cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
    angle = -math.atan2(dz, dx)
    data = _load_layout()
    item = {
        "type": "wall",
        "pos": [cx, height / 2, cz],
        "rot": angle,
        "visible": True,
        "geo": [length, height, thickness],
        "color": 0x666666,
    }
    data["items"].append(item)
    _save_layout(data)
    idx = len(data["items"]) - 1
    return f"Added wall ({x1},{z1})->({x2},{z2}), length={length:.2f}m as item [{idx}]."


@mcp.tool()
def move_object(index: int, x: float, z: float) -> str:
    """Move an object to a new position.

    Args:
        index: Object index (from list_objects).
        x: New X position in meters.
        z: New Z position in meters.
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range (0-{len(data['items'])-1})."
    item = data["items"][index]
    item["pos"][0] = x
    item["pos"][2] = z
    _save_layout(data)
    t = item.get("furnitureType") or item.get("type")
    return f"Moved [{index}] {t} to ({x}, {z})."


@mcp.tool()
def rotate_object(index: int, rotation_deg: float) -> str:
    """Set an object's rotation.

    Args:
        index: Object index (from list_objects).
        rotation_deg: New rotation in degrees.
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    data["items"][index]["rot"] = math.radians(rotation_deg)
    _save_layout(data)
    return f"Rotated [{index}] to {rotation_deg}°."


@mcp.tool()
def remove_object(index: int) -> str:
    """Remove an object from the layout.

    Args:
        index: Object index (from list_objects).
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    removed = data["items"].pop(index)
    _save_layout(data)
    t = removed.get("furnitureType") or removed.get("type")
    return f"Removed [{index}] {t}. Remaining items re-indexed."


@mcp.tool()
def remove_objects_by_type(object_type: str) -> str:
    """Remove all objects of a given type.

    Args:
        object_type: Type to remove — 'wall', 'model_part', or a furniture type like 'bed_queen'.
    """
    data = _load_layout()
    before = len(data["items"])
    data["items"] = [
        item for item in data["items"]
        if not (item.get("type") == object_type or item.get("furnitureType") == object_type)
    ]
    removed = before - len(data["items"])
    _save_layout(data)
    return f"Removed {removed} {object_type} item(s). {len(data['items'])} remaining."


@mcp.tool()
def clear_layout() -> str:
    """Remove all objects from the layout."""
    _save_layout({"version": 1, "items": []})
    return "Layout cleared."


@mcp.tool()
def get_layout_json() -> str:
    """Get the full layout as JSON (for importing into the editor)."""
    return json.dumps(_load_layout(), indent=2)


@mcp.tool()
def get_object_details(index: int) -> str:
    """Get full details for one object: type, position, rotation, dimensions, color, visibility.

    Args:
        index: Object index (from list_objects).
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range (0-{len(data['items'])-1})."
    item = data["items"][index]
    t = item.get("furnitureType") or item.get("type", "object")
    p = item["pos"]
    rot = math.degrees(item.get("rot", 0))
    geo = item.get("geo", [1, 1, 1])
    color = f"#{item.get('color', 0):06x}"
    vis = item.get("visible", True)
    return (f"[{index}] {t}\n"
            f"  position: ({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f})\n"
            f"  rotation: {rot:.1f} deg\n"
            f"  dimensions: w={geo[0]:.2f} h={geo[1]:.2f} d={geo[2]:.2f}\n"
            f"  color: {color}\n"
            f"  visible: {vis}")


@mcp.tool()
def get_layout_summary() -> str:
    """Get a summary of the layout: object counts by type, furniture breakdown, hidden count, bounding box."""
    data = _load_layout()
    items = data["items"]
    if not items:
        return "Layout is empty."
    type_counts: dict[str, int] = {}
    furniture_counts: dict[str, int] = {}
    hidden = 0
    xs, zs = [], []
    for item in items:
        t = item.get("type", "object")
        type_counts[t] = type_counts.get(t, 0) + 1
        if t == "furniture":
            ft = item.get("furnitureType", "unknown")
            furniture_counts[ft] = furniture_counts.get(ft, 0) + 1
        if not item.get("visible", True):
            hidden += 1
        p = item["pos"]
        xs.append(p[0])
        zs.append(p[2])
    lines = [f"Total objects: {len(items)}"]
    for t, c in sorted(type_counts.items()):
        lines.append(f"  {t}: {c}")
    if furniture_counts:
        lines.append("Furniture breakdown:")
        for ft, c in sorted(furniture_counts.items()):
            lines.append(f"  {ft}: {c}")
    if hidden:
        lines.append(f"Hidden: {hidden}")
    lines.append(f"XZ bounding box: X=[{min(xs):.2f}, {max(xs):.2f}] Z=[{min(zs):.2f}, {max(zs):.2f}]")
    return "\n".join(lines)


@mcp.tool()
def resize_object(index: int, width: float | None = None, height: float | None = None, depth: float | None = None) -> str:
    """Resize an object. Only provided dimensions are changed. Minimum 0.05m per axis.

    Args:
        index: Object index (from list_objects).
        width: New width in meters (X axis).
        height: New height in meters (Y axis).
        depth: New depth in meters (Z axis).
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    item = data["items"][index]
    geo = item.get("geo", [1, 1, 1])
    if width is not None:
        geo[0] = max(0.05, width)
    if height is not None:
        geo[1] = max(0.05, height)
    if depth is not None:
        geo[2] = max(0.05, depth)
    item["geo"] = geo
    item["pos"][1] = geo[1] / 2  # stay grounded
    _save_layout(data)
    return f"Resized [{index}] to w={geo[0]:.2f} h={geo[1]:.2f} d={geo[2]:.2f}."


@mcp.tool()
def set_color(index: int, color: str) -> str:
    """Set an object's color.

    Args:
        index: Object index (from list_objects).
        color: Hex color string (e.g. '#ff0000').
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    try:
        c = int(color.lstrip("#"), 16)
    except ValueError:
        return f"Error: invalid color '{color}'. Use hex like '#ff0000'."
    data["items"][index]["color"] = c
    _save_layout(data)
    return f"Set [{index}] color to {color}."


@mcp.tool()
def set_visibility(index: int, visible: bool) -> str:
    """Show or hide an object.

    Args:
        index: Object index (from list_objects).
        visible: True to show, False to hide.
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    data["items"][index]["visible"] = visible
    _save_layout(data)
    state = "visible" if visible else "hidden"
    return f"Set [{index}] to {state}."


@mcp.tool()
def duplicate_object(index: int, x: float, z: float) -> str:
    """Duplicate an object to a new position, preserving all properties.

    Args:
        index: Object index (from list_objects).
        x: X position for the copy.
        z: Z position for the copy.
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    import copy
    new_item = copy.deepcopy(data["items"][index])
    new_item["pos"][0] = x
    new_item["pos"][2] = z
    data["items"].append(new_item)
    _save_layout(data)
    new_idx = len(data["items"]) - 1
    t = new_item.get("furnitureType") or new_item.get("type")
    return f"Duplicated [{index}] {t} to ({x}, {z}) as [{new_idx}]."


@mcp.tool()
def batch_move(indices: list[int], dx: float, dz: float) -> str:
    """Move multiple objects by a relative offset. All indices validated before applying.

    Args:
        indices: List of object indices to move.
        dx: Relative X offset in meters.
        dz: Relative Z offset in meters.
    """
    data = _load_layout()
    n = len(data["items"])
    for i in indices:
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1}). No objects moved."
    for i in indices:
        data["items"][i]["pos"][0] += dx
        data["items"][i]["pos"][2] += dz
    _save_layout(data)
    return f"Moved {len(indices)} objects by dx={dx}, dz={dz}."


@mcp.tool()
def measure_distance(index1: int, index2: int) -> str:
    """XZ Euclidean distance between two object centers.

    Args:
        index1: First object index.
        index2: Second object index.
    """
    data = _load_layout()
    n = len(data["items"])
    for i in (index1, index2):
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1})."
    p1, p2 = data["items"][index1]["pos"], data["items"][index2]["pos"]
    dx, dz = p1[0] - p2[0], p1[2] - p2[2]
    dist = math.sqrt(dx * dx + dz * dz)
    return f"Distance between [{index1}] and [{index2}]: {dist:.3f}m"


@mcp.tool()
def find_objects_in_area(x_min: float, z_min: float, x_max: float, z_max: float) -> str:
    """Find all objects whose center falls within an XZ bounding box.

    Args:
        x_min: Minimum X coordinate.
        z_min: Minimum Z coordinate.
        x_max: Maximum X coordinate.
        z_max: Maximum Z coordinate.
    """
    data = _load_layout()
    found = []
    for i, item in enumerate(data["items"]):
        p = item["pos"]
        if x_min <= p[0] <= x_max and z_min <= p[2] <= z_max:
            t = item.get("furnitureType") or item.get("type", "object")
            found.append(f"  [{i}] {t} at ({p[0]:.2f}, {p[2]:.2f})")
    if not found:
        return "No objects found in the specified area."
    return f"Found {len(found)} objects:\n" + "\n".join(found)


@mcp.tool()
def check_overlap(index1: int, index2: int) -> str:
    """AABB overlap check on XZ plane between two objects. Accounts for rotation.

    Args:
        index1: First object index.
        index2: Second object index.
    """
    data = _load_layout()
    n = len(data["items"])
    for i in (index1, index2):
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1})."
    def _extents(item):
        geo = item.get("geo", [1, 1, 1])
        r = item.get("rot", 0)
        half_x = (abs(geo[0] * math.cos(r)) + abs(geo[2] * math.sin(r))) / 2
        half_z = (abs(geo[0] * math.sin(r)) + abs(geo[2] * math.cos(r))) / 2
        p = item["pos"]
        return p[0] - half_x, p[0] + half_x, p[2] - half_z, p[2] + half_z
    ax_min, ax_max, az_min, az_max = _extents(data["items"][index1])
    bx_min, bx_max, bz_min, bz_max = _extents(data["items"][index2])
    overlap = ax_min < bx_max and ax_max > bx_min and az_min < bz_max and az_max > bz_min
    if overlap:
        return f"Objects [{index1}] and [{index2}] OVERLAP on XZ plane."
    return f"Objects [{index1}] and [{index2}] do NOT overlap."


@mcp.tool()
def find_nearest(index: int, count: int = 3) -> str:
    """Find N nearest objects by XZ distance, sorted.

    Args:
        index: Reference object index.
        count: Number of nearest neighbors to return (default 3).
    """
    data = _load_layout()
    n = len(data["items"])
    if index < 0 or index >= n:
        return f"Error: index {index} out of range (0-{n-1})."
    p = data["items"][index]["pos"]
    dists = []
    for i, item in enumerate(data["items"]):
        if i == index:
            continue
        q = item["pos"]
        dx, dz = p[0] - q[0], p[2] - q[2]
        dists.append((math.sqrt(dx * dx + dz * dz), i))
    dists.sort()
    results = dists[:count]
    if not results:
        return "No other objects in layout."
    lines = []
    for d, i in results:
        t = data["items"][i].get("furnitureType") or data["items"][i].get("type", "object")
        lines.append(f"  [{i}] {t} — {d:.3f}m")
    return f"Nearest {len(results)} objects to [{index}]:\n" + "\n".join(lines)


@mcp.tool()
def align_objects(indices: list[int], axis: str, reference: str = "center") -> str:
    """Align objects along an axis.

    Args:
        indices: List of object indices to align.
        axis: Axis to align on — 'x' or 'z'.
        reference: 'min', 'max', or 'center' (average of group). Default 'center'.
    """
    if axis not in ("x", "z"):
        return "Error: axis must be 'x' or 'z'."
    if reference not in ("min", "max", "center"):
        return "Error: reference must be 'min', 'max', or 'center'."
    data = _load_layout()
    n = len(data["items"])
    for i in indices:
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1}). No changes made."
    comp = 0 if axis == "x" else 2
    vals = [data["items"][i]["pos"][comp] for i in indices]
    if reference == "min":
        target = min(vals)
    elif reference == "max":
        target = max(vals)
    else:
        target = sum(vals) / len(vals)
    for i in indices:
        data["items"][i]["pos"][comp] = target
    _save_layout(data)
    return f"Aligned {len(indices)} objects on {axis}={target:.3f} (ref={reference})."


@mcp.tool()
def distribute_objects(indices: list[int], axis: str) -> str:
    """Evenly space objects along an axis. First/last stay as anchors.

    Args:
        indices: List of object indices (>= 3).
        axis: Axis to distribute along — 'x' or 'z'.
    """
    if axis not in ("x", "z"):
        return "Error: axis must be 'x' or 'z'."
    if len(indices) < 3:
        return "Error: need at least 3 objects to distribute."
    data = _load_layout()
    n = len(data["items"])
    for i in indices:
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1}). No changes made."
    comp = 0 if axis == "x" else 2
    ordered = sorted(indices, key=lambda i: data["items"][i]["pos"][comp])
    start = data["items"][ordered[0]]["pos"][comp]
    end = data["items"][ordered[-1]]["pos"][comp]
    step = (end - start) / (len(ordered) - 1)
    for k, i in enumerate(ordered):
        data["items"][i]["pos"][comp] = start + k * step
    _save_layout(data)
    return f"Distributed {len(indices)} objects along {axis} from {start:.3f} to {end:.3f}."


@mcp.tool()
def snap_to_grid(indices: list[int], grid_size: float = 0.25) -> str:
    """Round object positions to nearest grid multiple.

    Args:
        indices: List of object indices to snap.
        grid_size: Grid cell size in meters (default 0.25).
    """
    if grid_size <= 0:
        return "Error: grid_size must be positive."
    data = _load_layout()
    n = len(data["items"])
    for i in indices:
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1}). No changes made."
    for i in indices:
        p = data["items"][i]["pos"]
        p[0] = round(p[0] / grid_size) * grid_size
        p[2] = round(p[2] / grid_size) * grid_size
    _save_layout(data)
    return f"Snapped {len(indices)} objects to {grid_size}m grid."


@mcp.tool()
def rename_object(index: int, name: str) -> str:
    """Assign a human-readable label to an object. Empty string removes it.

    Args:
        index: Object index.
        name: Label to assign (empty string to remove).
    """
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    if name:
        data["items"][index]["name"] = name
    else:
        data["items"][index].pop("name", None)
    _save_layout(data)
    return f"{'Renamed' if name else 'Cleared name for'} [{index}] → '{name}'." if name else f"Cleared name for [{index}]."


@mcp.tool()
def find_by_name(name: str) -> str:
    """Case-insensitive substring search on object names.

    Args:
        name: Search string.
    """
    data = _load_layout()
    found = []
    for i, item in enumerate(data["items"]):
        obj_name = item.get("name", "")
        if obj_name and name.lower() in obj_name.lower():
            t = item.get("furnitureType") or item.get("type", "object")
            p = item["pos"]
            found.append(f"  [{i}] \"{obj_name}\" ({t}) at ({p[0]:.2f}, {p[2]:.2f})")
    if not found:
        return f"No objects found matching '{name}'."
    return f"Found {len(found)} matching objects:\n" + "\n".join(found)


@mcp.tool()
def tag_room(indices: list[int], room_name: str) -> str:
    """Assign a room label to objects.

    Args:
        indices: List of object indices to tag.
        room_name: Room name to assign.
    """
    data = _load_layout()
    n = len(data["items"])
    for i in indices:
        if i < 0 or i >= n:
            return f"Error: index {i} out of range (0-{n-1}). No changes made."
    for i in indices:
        data["items"][i]["room"] = room_name
    _save_layout(data)
    return f"Tagged {len(indices)} objects as '{room_name}'."


@mcp.tool()
def list_rooms() -> str:
    """List all room labels with their object indices and types."""
    data = _load_layout()
    rooms: dict[str, list[str]] = {}
    for i, item in enumerate(data["items"]):
        room = item.get("room")
        if room:
            t = item.get("furnitureType") or item.get("type", "object")
            rooms.setdefault(room, []).append(f"[{i}] {t}")
    if not rooms:
        return "No rooms defined. Use tag_room to assign rooms."
    lines = []
    for room, objs in sorted(rooms.items()):
        lines.append(f"  {room}: {', '.join(objs)}")
    return f"{len(rooms)} rooms:\n" + "\n".join(lines)


@mcp.tool()
def swap_furniture(index: int, new_type: str) -> str:
    """Replace furniture type keeping position, rotation, visibility, name, room.

    Args:
        index: Object index.
        new_type: New furniture type from catalog.
    """
    if new_type not in FURNITURE_CATALOG:
        return f"Error: unknown type '{new_type}'. Use list_furniture_catalog()."
    data = _load_layout()
    if index < 0 or index >= len(data["items"]):
        return f"Error: index {index} out of range."
    item = data["items"][index]
    spec = FURNITURE_CATALOG[new_type]
    old_type = item.get("furnitureType") or item.get("type")
    item["type"] = "furniture"
    item["furnitureType"] = new_type
    item["geo"] = [spec["w"], spec["h"], spec["d"]]
    item["color"] = spec["color"]
    item["pos"][1] = spec["h"] / 2  # re-ground Y
    _save_layout(data)
    return f"Swapped [{index}] from {old_type} to {new_type}."


def run_server() -> None:
    """Start the MCP server on stdio."""
    mcp.run()
