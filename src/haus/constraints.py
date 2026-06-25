from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

CONSTRAINT_PACK_SCHEMA_ID = "haus.constraint_pack.v1"
DEFAULT_CONSTRAINT_PACKS = ("compact_hdb", "furniture_fit", "agent_guardrails")


def _pack_dir():
    return files("haus").joinpath("corpus", "constraints")


def _safe_pack_id(pack_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", pack_id.strip()).strip("._-")


def constraint_pack_ids() -> list[str]:
    root = _pack_dir()
    if not root.is_dir():
        return []
    return sorted(path.name.removesuffix(".json") for path in root.iterdir() if path.name.endswith(".json"))


def get_constraint_pack(pack_id: str) -> dict[str, Any]:
    safe = _safe_pack_id(pack_id)
    path = _pack_dir().joinpath(f"{safe}.json")
    if not path.is_file():
        raise KeyError(f"Unknown constraint pack: {pack_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != CONSTRAINT_PACK_SCHEMA_ID:
        raise ValueError(f"Invalid constraint pack: {pack_id}")
    return payload


def list_constraint_packs() -> list[dict[str, Any]]:
    packs = []
    for pack_id in constraint_pack_ids():
        pack = get_constraint_pack(pack_id)
        packs.append(
            {
                "id": pack["id"],
                "label": pack.get("label", pack["id"]),
                "scope": pack.get("scope", []),
                "region": pack.get("region", "global"),
                "source_basis": pack.get("source_basis", "planning_target"),
                "disclaimer": pack.get("disclaimer", ""),
            }
        )
    return packs


def load_constraint_packs(pack_ids: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    selected = pack_ids or DEFAULT_CONSTRAINT_PACKS
    return [get_constraint_pack(pack_id) for pack_id in selected]


def merge_constraint_targets(pack_ids: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    for pack in load_constraint_packs(pack_ids):
        for key, value in pack.get("targets", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                existing = targets.get(key)
                targets[key] = max(float(existing), float(value)) if isinstance(existing, (int, float)) else float(value)
            elif value is not None and key not in targets:
                targets[key] = value
    return targets
