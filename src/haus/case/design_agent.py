"""Design Agent wrapper — pinned proposals, optional live LLM, deterministic fallback.

Implements POST /case/{id}/design per SPEC-HTTP-CASE.md section 4.2:
- When `pinned_proposal_id` is set on the Case, returns a recorded items[] verbatim
  (demo-replay hook; the determinism contract from SPEC section 6 / 2.8).
- Otherwise optionally asks a live LLM provider for a structured proposal when
  `mode="live"` or `HAUS_CASE_DESIGN_MODE=live`.
- If live generation is unavailable or malformed, falls back to the existing
  deterministic planner in agent_loop.plan_room,
  which is what the MCP `design_room`/`design_flat` tools already use.

`hints` are the array of `machine_hint` objects from compliance findings (SPEC 2.4).
Live mode includes them in the structured prompt. The pinned-proposal path ignores
hints entirely — the demo's "LLM keeps proposing the same bad thing" beat depends
on this. Stage 1 demo should stay pinned-only unless a live provider run is being
shown intentionally.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence

from ..agent_loop import RoomPlan, RoomZone, plan_room
# Reuse the same furniture catalog + item builder the MCP design tools use.
# Keeping a single source of truth for furniture dimensions across MCP / HTTP / tests.
from ..mcp_server import FURNITURE_CATALOG, _build_furniture_item
from .ingest import enrich_wall_hdb_types, touch


class PinnedProposalNotFound(Exception):
    """Raised when a Case carries a pinned_proposal_id with no matching file."""


class LiveProposalUnavailable(Exception):
    """Raised when live LLM proposal generation cannot produce valid operations."""


class DesignAgent:
    """Stage-1 Design Agent.

    proposals_dir: directory containing pinned proposal JSON files. File naming:
        {proposal_id}.json. Schema:
            {
              "proposal_id": str,
              "description": str (optional),
              "items": [<item>, ...]   # full replacement for case['items']
            }
    """

    def __init__(
        self,
        proposals_dir: str | Path | None = None,
        *,
        mode: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        cache_live_proposals: bool | None = None,
    ) -> None:
        self.proposals_dir = Path(proposals_dir) if proposals_dir else None
        self.mode = _normalize_mode(mode or os.environ.get("HAUS_CASE_DESIGN_MODE", "auto"))
        self.provider = provider or os.environ.get("HAUS_CASE_LLM_PROVIDER")
        self.model = model or os.environ.get("HAUS_CASE_LLM_MODEL")
        self.cache_live_proposals = (
            _env_bool("HAUS_CASE_CACHE_LIVE_PROPOSALS", False)
            if cache_live_proposals is None
            else cache_live_proposals
        )

    def propose(
        self,
        case: dict[str, Any],
        *,
        hints: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run a design pass on the Case in place; return the same Case dict.

        Post-state: `design_status` = `compliance_pending` per SPEC section 4.2.
        """
        trace: dict[str, Any] = {"mode": self.mode, "source": None, "fallback_reason": None}
        proposal_id = case.get("pinned_proposal_id")
        if proposal_id:
            new_items = self._load_pinned(proposal_id)
            trace["source"] = "pinned"
            trace["proposal_id"] = proposal_id
        elif self.mode == "live":
            try:
                new_items = self._live(case, hints=hints)
                trace["source"] = "live"
                trace["provider"] = self.provider
                trace["model"] = self.model
                self._maybe_cache_live(case, new_items)
            except LiveProposalUnavailable as exc:
                new_items = self._deterministic(case, hints=hints)
                trace["source"] = "deterministic"
                trace["fallback_reason"] = str(exc)
        else:
            new_items = self._deterministic(case, hints=hints)
            trace["source"] = "deterministic"

        case["items"] = enrich_wall_hdb_types(new_items)
        case["design_agent_trace"] = trace
        case["design_status"] = "compliance_pending"
        touch(case)
        return case

    # ------------------------------------------------------------------
    # Pinned-proposal path
    # ------------------------------------------------------------------

    def _load_pinned(self, proposal_id: str) -> list[dict[str, Any]]:
        if self.proposals_dir is None:
            raise PinnedProposalNotFound(
                f"pinned_proposal_id={proposal_id!r} set but DesignAgent has no proposals_dir."
            )
        path = self.proposals_dir / f"{proposal_id}.json"
        if not path.exists():
            raise PinnedProposalNotFound(f"Pinned proposal not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items")
        if not isinstance(items, list):
            raise PinnedProposalNotFound(
                f"Pinned proposal {path} missing required 'items' array."
            )
        # deep-copy via JSON round-trip to avoid sharing references with the proposal
        return json.loads(json.dumps(items))

    # ------------------------------------------------------------------
    # Live LLM path (explicit opt-in for judge/demo exploration)
    # ------------------------------------------------------------------

    def _live(
        self,
        case: dict[str, Any],
        *,
        hints: Sequence[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        provider, api_key, model = self._resolve_live_provider()
        prompt = _live_prompt(case, hints=hints)

        try:
            from .. import chat_server
        except Exception as exc:  # pragma: no cover - defensive import guard
            raise LiveProposalUnavailable(f"chat provider plumbing unavailable: {exc}") from exc

        def disabled_dispatch(name: str, args: dict[str, Any]) -> str:
            return (
                f"Tool {name!r} is unavailable in the Case Design Agent. "
                "Return structured JSON operations only."
            )

        try:
            text, _history = chat_server._CHAT_FNS[provider](
                api_key,
                [{"role": "user", "content": prompt}],
                model,
                disabled_dispatch,
            )
        except Exception as exc:
            raise LiveProposalUnavailable(f"live {provider} proposal failed: {exc}") from exc

        payload = _extract_json_object(text)
        if payload is None:
            raise LiveProposalUnavailable("live proposal did not contain a JSON object")

        items = json.loads(json.dumps(case.get("items", [])))
        if isinstance(payload.get("items"), list):
            candidate = [dict(it) for it in payload["items"] if isinstance(it, dict)]
            if not candidate:
                raise LiveProposalUnavailable("live proposal returned an empty items array")
            return candidate

        operations = payload.get("operations")
        if not isinstance(operations, list):
            raise LiveProposalUnavailable("live proposal missing operations array")

        return _apply_live_operations(items, operations)

    def _resolve_live_provider(self) -> tuple[str, str, str]:
        try:
            from .. import chat_server
        except Exception as exc:  # pragma: no cover - defensive import guard
            raise LiveProposalUnavailable(f"chat provider plumbing unavailable: {exc}") from exc

        providers = chat_server._provider_available()
        provider = self.provider or (providers[0] if providers else "")
        if provider not in chat_server._CHAT_FNS:
            raise LiveProposalUnavailable("no supported live LLM provider is configured")
        env_key = chat_server._ENV_KEYS.get(provider, "")
        api_key = os.environ.get(env_key, "")
        if not api_key:
            raise LiveProposalUnavailable(f"{env_key} is not set")
        model = self.model or chat_server._DEFAULT_MODELS.get(provider, "default")
        self.provider = provider
        self.model = model
        return provider, api_key, model

    def _maybe_cache_live(self, case: dict[str, Any], items: list[dict[str, Any]]) -> None:
        if not self.cache_live_proposals or self.proposals_dir is None:
            return
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        case_id = str(case.get("case_id") or "case")
        digest = hashlib.sha1(  # noqa: S324 - stable demo cache key, not security.
            json.dumps({"case_id": case_id, "items": items}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:10]
        proposal_id = f"live_{case_id[:8]}_{digest}"
        path = self.proposals_dir / f"{proposal_id}.json"
        payload = {
            "proposal_id": proposal_id,
            "description": "Live LLM proposal cached by Haus Case Design Agent.",
            "items": items,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        case["pinned_proposal_id"] = proposal_id

    # ------------------------------------------------------------------
    # Deterministic planner path (fallback when no pinned_proposal_id)
    # ------------------------------------------------------------------

    def _deterministic(
        self,
        case: dict[str, Any],
        *,
        hints: Sequence[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Furnish each room via agent_loop.plan_room; preserve walls untouched.

        Hints are inspected only to log the constraint set — the deterministic
        planner does not consume them programmatically. A real LLM planner would.
        """
        brief = case.get("brief", {})
        style_prompt = str(brief.get("style_prompt") or "minimalist HDB")
        constraints = " ".join(brief.get("constraints", [])) if isinstance(brief.get("constraints"), list) else str(brief.get("constraints", ""))

        # walls survive; furniture is regenerated each design pass for determinism
        new_items: list[dict[str, Any]] = [
            it for it in case.get("items", []) if it.get("type") == "wall"
        ]

        for room in case.get("rooms", []):
            bounds = room.get("bounds")
            if not isinstance(bounds, dict):
                continue
            try:
                x_min = float(bounds["x_min"])
                z_min = float(bounds["z_min"])
                x_max = float(bounds["x_max"])
                z_max = float(bounds["z_max"])
            except (KeyError, ValueError, TypeError):
                continue
            origin_x = (x_min + x_max) / 2.0
            origin_z = (z_min + z_max) / 2.0
            zone = RoomZone(
                room_id=str(room.get("id") or ""),
                label=str(room.get("label") or room.get("id") or ""),
                kind=str(room.get("kind") or "living"),
                bounds=(x_min, z_min, x_max, z_max),
                source="curated",
            )
            plan: RoomPlan = plan_room(
                room_id=zone.label or zone.room_id,
                style_prompt=f"{style_prompt} {zone.kind}",
                constraints=constraints,
                origin_x=origin_x,
                origin_z=origin_z,
                bounds=zone.bounds,
                zone_source=zone.source,
            )
            for planned in plan.items:
                if planned.furniture_type not in FURNITURE_CATALOG:
                    continue
                item = _build_furniture_item(
                    planned.furniture_type,
                    plan.origin_x + planned.dx,
                    plan.origin_z + planned.dz,
                    planned.rotation_deg,
                )
                if planned.name:
                    item["name"] = planned.name
                item["room"] = zone.room_id or zone.label
                new_items.append(item)

        return new_items


def _normalize_mode(value: str) -> str:
    mode = value.strip().lower().replace("-", "_")
    if mode in {"live", "llm", "llm_live"}:
        return "live"
    if mode in {"deterministic", "fallback", "auto", ""}:
        return "deterministic"
    return "deterministic"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _item_name(item: dict[str, Any]) -> str | None:
    name = item.get("name")
    return str(name) if name else None


def _apply_live_operations(
    items: list[dict[str, Any]],
    operations: Sequence[Any],
) -> list[dict[str, Any]]:
    next_items = json.loads(json.dumps(items))
    for raw in operations:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or raw.get("op") or "").strip().lower()
        if action in {"remove", "remove_item", "remove_item_by_name"}:
            name = raw.get("name") or raw.get("element_name")
            if not name:
                continue
            next_items = [it for it in next_items if _item_name(it) != str(name)]
        elif action in {"add", "add_item"}:
            item = raw.get("item")
            if isinstance(item, dict) and isinstance(item.get("type"), str):
                next_items.append(dict(item))
        elif action in {"set_visible", "visibility"}:
            name = raw.get("name") or raw.get("element_name")
            if not name:
                continue
            visible = bool(raw.get("visible", True))
            for item in next_items:
                if _item_name(item) == str(name):
                    item["visible"] = visible
        elif action in {"move", "move_item"}:
            name = raw.get("name") or raw.get("element_name")
            pos = raw.get("pos")
            if not name or not isinstance(pos, list) or len(pos) < 3:
                continue
            for item in next_items:
                if _item_name(item) == str(name):
                    item["pos"] = [float(pos[0]), float(pos[1]), float(pos[2])]
    return next_items


def _live_prompt(
    case: dict[str, Any],
    *,
    hints: Sequence[dict[str, Any]] | None,
) -> str:
    rooms = [
        {
            "id": room.get("id"),
            "label": room.get("label"),
            "kind": room.get("kind"),
            "bounds": room.get("bounds"),
        }
        for room in case.get("rooms", [])
        if isinstance(room, dict)
    ]
    protected = [
        {
            "name": item.get("name"),
            "hdb_type": item.get("hdb_type"),
            "geo": item.get("geo"),
            "pos": item.get("pos"),
        }
        for item in case.get("items", [])
        if isinstance(item, dict)
        and item.get("type") == "wall"
        and item.get("hdb_type") in {"structural", "shelter"}
    ]
    furniture = [
        {
            "name": item.get("name"),
            "type": item.get("type"),
            "furnitureType": item.get("furnitureType"),
            "room": item.get("room"),
            "pos": item.get("pos"),
            "geo": item.get("geo"),
        }
        for item in case.get("items", [])
        if isinstance(item, dict) and item.get("type") != "wall"
    ][:80]
    payload = {
        "brief": case.get("brief", {}),
        "rooms": rooms,
        "protected_walls": protected,
        "current_furniture": furniture,
        "compliance_hints": list(hints or []),
    }
    return (
        "You are the Haus Case Design Agent for an HDB renovation workflow. "
        "Return only JSON. Do not remove or hide protected_walls. "
        "Prefer small furniture/layout operations over replacing the whole plan. "
        "Supported JSON shapes:\n"
        "{\"operations\":[{\"action\":\"add_item\",\"item\":{...}},"
        "{\"action\":\"remove_item_by_name\",\"name\":\"...\"},"
        "{\"action\":\"move_item\",\"name\":\"...\",\"pos\":[x,y,z]}]}\n"
        "or {\"items\":[...full Haus layout items...]}. "
        "Haus item coordinates are meters: pos=[x,y,z], rot is radians, geo=[w,h,d].\n\n"
        f"Case context:\n{json.dumps(payload, indent=2)}"
    )
