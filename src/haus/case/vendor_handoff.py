"""Vendor/Handoff Agent v0 for the Stage-1 Case flow.

The goal is deliberately thin: prove that an approved design can be packaged
for contractor handoff without making the recorded demo depend on live search.
Cache hits are deterministic; cache misses fall back to an explicit live-search
stub that can be replaced by TinyFish/Serper later.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ingest import touch
from .revise_loop import InvalidStateTransition


DEFAULT_VENDOR_CACHE_KEY = "demo_hdb_renovation"


class VendorCacheError(Exception):
    """Raised when a vendor cache file is malformed."""


class VendorHandoffAgent:
    """Cache-first handoff packet generator.

    vendor_cache_dir:
        Directory containing `{vendor_cache_key}.json` files. The v0 schema is:
        {
          "cache_key": "demo_hdb_renovation",
          "vendors": [
            {
              "vendor_id": "vendor_haus_001",
              "vendor_name": "Keystone HDB Renovation Pte Ltd",
              "packet_template": "Coordinate HDB-compliant renovation handoff.",
              ...
            }
          ]
        }

    handoff_root:
        Directory where per-case `packet.zip` files are written.
    """

    def __init__(
        self,
        *,
        vendor_cache_dir: str | Path | None = None,
        handoff_root: str | Path | None = None,
    ) -> None:
        self.vendor_cache_dir = Path(vendor_cache_dir) if vendor_cache_dir else None
        self.handoff_root = Path(handoff_root).expanduser() if handoff_root else Path.home() / ".haus" / "handoffs"

    def create_handoff(
        self,
        case: dict[str, Any],
        *,
        vendor_cache_key: str | None = None,
        vendor_id: str | None = None,
    ) -> dict[str, Any]:
        """Populate `case["vendor_handoff"]` and transition approved -> handoff_complete."""
        if case.get("design_status") != "approved":
            raise InvalidStateTransition(
                f"handoff requires design_status == 'approved', got {case.get('design_status')!r}"
            )

        key = vendor_cache_key or case.get("vendor_cache_key") or DEFAULT_VENDOR_CACHE_KEY
        vendor, cached = self._resolve_vendor(str(key), vendor_id=vendor_id, case=case)
        packet_uri = self._write_packet(case, vendor=vendor, cached=cached, vendor_cache_key=str(key))

        case["vendor_cache_key"] = str(key)
        case["vendor_handoff"] = {
            "vendor_id": vendor["vendor_id"],
            "vendor_name": vendor["vendor_name"],
            "packet_uri": packet_uri,
            "cached": cached,
            "vendor_cache_key": str(key),
            "source": vendor.get("source", "cache" if cached else "live_search_fallback"),
            "fallback_reason": None if cached else vendor.get("fallback_reason", "vendor_cache_miss"),
            "contact": vendor.get("contact", {}),
            "specialties": vendor.get("specialties", []),
        }
        case["design_status"] = "handoff_complete"
        touch(case)
        return case

    def _resolve_vendor(
        self,
        vendor_cache_key: str,
        *,
        vendor_id: str | None,
        case: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        cached_payload = self._load_cache(vendor_cache_key)
        if cached_payload:
            vendors = cached_payload.get("vendors")
            if not isinstance(vendors, list) or not vendors:
                raise VendorCacheError(f"Vendor cache {vendor_cache_key!r} must contain a non-empty vendors array.")
            candidates = [v for v in vendors if isinstance(v, dict)]
            if vendor_id:
                candidates = [v for v in candidates if v.get("vendor_id") == vendor_id]
            if not candidates:
                raise VendorCacheError(
                    f"Vendor cache {vendor_cache_key!r} has no vendor matching {vendor_id!r}."
                )
            return self._normalise_vendor(candidates[0]), True

        return self._live_search_stub(vendor_cache_key, case), False

    def _load_cache(self, vendor_cache_key: str) -> dict[str, Any] | None:
        if self.vendor_cache_dir is None:
            return None
        path = self.vendor_cache_dir / f"{vendor_cache_key}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise VendorCacheError(f"Malformed vendor cache JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise VendorCacheError(f"Vendor cache root must be an object: {path}")
        return payload

    def _normalise_vendor(self, vendor: dict[str, Any]) -> dict[str, Any]:
        vendor_id = vendor.get("vendor_id")
        vendor_name = vendor.get("vendor_name")
        if not isinstance(vendor_id, str) or not vendor_id:
            raise VendorCacheError("Cached vendor is missing vendor_id.")
        if not isinstance(vendor_name, str) or not vendor_name:
            raise VendorCacheError("Cached vendor is missing vendor_name.")
        return {
            **vendor,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "contact": vendor.get("contact") if isinstance(vendor.get("contact"), dict) else {},
            "specialties": vendor.get("specialties") if isinstance(vendor.get("specialties"), list) else [],
            "packet_template": (
                vendor.get("packet_template")
                if isinstance(vendor.get("packet_template"), str)
                else "Coordinate the approved HDB renovation handoff package."
            ),
        }

    def _live_search_stub(self, vendor_cache_key: str, case: dict[str, Any]) -> dict[str, Any]:
        flat_type = str(case.get("brief", {}).get("flat_type") or "HDB flat")
        return {
            "vendor_id": "live_search_stub",
            "vendor_name": "Live Search Fallback Renovation Partner",
            "contact": {},
            "specialties": ["HDB renovation", flat_type, "compliance handoff"],
            "packet_template": (
                "Live vendor search is not configured in Stage 1; this stub marks "
                "where TinyFish or Serper results will be inserted."
            ),
            "source": "live_search_stub",
            "fallback_reason": "vendor_cache_miss",
            "requested_cache_key": vendor_cache_key,
        }

    def _write_packet(
        self,
        case: dict[str, Any],
        *,
        vendor: dict[str, Any],
        cached: bool,
        vendor_cache_key: str,
    ) -> str:
        case_id = str(case.get("case_id"))
        packet_dir = self.handoff_root / f"case_{case_id}"
        packet_dir.mkdir(parents=True, exist_ok=True)
        packet_path = packet_dir / "packet.zip"
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        handoff_json = {
            "case_id": case_id,
            "generated_at": generated_at,
            "vendor_cache_key": vendor_cache_key,
            "cached": cached,
            "vendor": vendor,
            "brief": case.get("brief", {}),
            "approval_state": case.get("approval_state"),
            "compliance_findings": case.get("compliance_findings", []),
            "layout_summary": {
                "rooms": len(case.get("rooms", [])),
                "items": len(case.get("items", [])),
                "walls": len([it for it in case.get("items", []) if it.get("type") == "wall"]),
            },
        }
        summary_md = self._render_summary_markdown(handoff_json)

        with zipfile.ZipFile(packet_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("handoff.json", json.dumps(handoff_json, indent=2, sort_keys=True))
            zf.writestr("summary.md", summary_md)

        return packet_path.resolve().as_uri()

    def _render_summary_markdown(self, handoff: dict[str, Any]) -> str:
        vendor = handoff["vendor"]
        brief = handoff["brief"]
        findings = handoff["compliance_findings"]
        lines = [
            f"# Renovation Handoff - Case {handoff['case_id']}",
            "",
            f"Generated: {handoff['generated_at']}",
            f"Vendor: {vendor['vendor_name']} ({vendor['vendor_id']})",
            f"Cache: {'hit' if handoff['cached'] else 'fallback'} ({handoff['vendor_cache_key']})",
            "",
            "## Brief",
            f"- Flat type: {brief.get('flat_type', 'unspecified')}",
            f"- Household size: {brief.get('household_size', 'unspecified')}",
            f"- Style: {brief.get('style_prompt', 'unspecified')}",
            "",
            "## Compliance",
            f"- Findings included: {len(findings)}",
            f"- Approval decision: {handoff.get('approval_state', {}).get('decision', 'unknown')}",
            "",
            "## Packet Template",
            str(vendor.get("packet_template", "")),
            "",
        ]
        return "\n".join(lines)


def step_handoff(
    case: dict[str, Any],
    *,
    handoff_agent: VendorHandoffAgent,
    vendor_cache_key: str | None = None,
    vendor_id: str | None = None,
) -> dict[str, Any]:
    """Stage-1 handoff transition: approved -> handoff_complete."""
    return handoff_agent.create_handoff(
        case,
        vendor_cache_key=vendor_cache_key,
        vendor_id=vendor_id,
    )
