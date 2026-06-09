"""Design Agent v0 wrapper — pinned proposals + deterministic planner fallback.

Implements POST /case/{id}/design per SPEC-HTTP-CASE.md section 4.2:
- When `pinned_proposal_id` is set on the Case, returns a recorded items[] verbatim
  (demo-replay hook; the determinism contract from SPEC section 6 / 2.8).
- Otherwise falls back to the existing deterministic planner in agent_loop.plan_room,
  which is what the MCP `design_room`/`design_flat` tools already use.
- LLM-driven proposals are out of v0 scope: the provider plumbing in chat_server.py
  (_CHAT_FNS, _provider_available, _resolve_planner_mode) exists but wiring it into
  this agent is a follow-up. Stage 1 demo runs on pinned proposals; that is by design.

`hints` are the array of `machine_hint` objects from compliance findings (SPEC 2.4).
A real LLM planner would consume them as constraints. The deterministic planner here
respects only `do_not_remove` hints by leaving walls intact (its existing behaviour);
it is otherwise non-adaptive. The pinned-proposal path ignores hints entirely — the
demo's "LLM keeps proposing the same bad thing" beat depends on this.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from ..agent_loop import RoomPlan, RoomZone, plan_room
# Reuse the same furniture catalog + item builder the MCP design tools use.
# Keeping a single source of truth for furniture dimensions across MCP / HTTP / tests.
from ..mcp_server import FURNITURE_CATALOG, _build_furniture_item
from .ingest import touch


class PinnedProposalNotFound(Exception):
    """Raised when a Case carries a pinned_proposal_id with no matching file."""


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

    def __init__(self, proposals_dir: str | Path | None = None) -> None:
        self.proposals_dir = Path(proposals_dir) if proposals_dir else None

    def propose(
        self,
        case: dict[str, Any],
        *,
        hints: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run a design pass on the Case in place; return the same Case dict.

        Post-state: `design_status` = `compliance_pending` per SPEC section 4.2.
        """
        proposal_id = case.get("pinned_proposal_id")
        if proposal_id:
            new_items = self._load_pinned(proposal_id)
        else:
            new_items = self._deterministic(case, hints=hints)

        case["items"] = new_items
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
