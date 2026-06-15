from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import run_artifact_dir
from .store import RunStore

FUSION_ROLES = {"planner", "reviewer", "researcher"}


class FusionRouteError(RuntimeError):
    pass


@dataclass(frozen=True)
class FusionCheck:
    enabled: bool
    reason: str = ""
    fallback: dict[str, str] | None = None
    params: dict[str, Any] | None = None


def route_uses_fusion(profile: dict[str, Any] | None, route: dict[str, Any] | None) -> bool:
    route = route or {}
    profile = profile or {}
    marker = route.get("fusion")
    explicit = bool(marker.get("enabled")) if isinstance(marker, dict) else bool(marker)
    return explicit or (str(profile.get("kind") or "") == "openrouter" and "fusion" in str(route.get("model") or "").lower())


def fusion_summary(profile: dict[str, Any] | None, route: dict[str, Any] | None, role: str) -> dict[str, Any]:
    enabled = route_uses_fusion(profile, route)
    params = fusion_params(route or {}) if enabled else {}
    return {"enabled": enabled, "role_allowed": role in FUSION_ROLES, "params": params}


def validate_fusion_route(
    config: dict[str, Any],
    role: str,
    route: dict[str, Any],
    *,
    allow_expensive_router: bool = False,
) -> FusionCheck:
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    profile_id = str(route.get("profile") or "")
    profile = providers.get(profile_id) if isinstance(providers, dict) else {}
    if not route_uses_fusion(profile if isinstance(profile, dict) else {}, route):
        return FusionCheck(False)
    if role not in FUSION_ROLES:
        return _blocked("Fusion is allowed only for planner, reviewer, or researcher routes", route)
    if not isinstance(profile, dict) or str(profile.get("kind") or "") != "openrouter":
        return _blocked("Fusion requires an OpenRouter profile", route)
    if "fusion" not in str(route.get("model") or "").lower():
        return _blocked("Fusion route must use openrouter/fusion or an explicit Fusion tool path", route)
    if not allow_expensive_router and not route.get("max_cost_usd"):
        return _blocked("Fusion review requires --allow-expensive-router or routes.reviewer.max_cost_usd", route)
    fallback_profile = str(route.get("fallback_profile") or "")
    fallback_model = str(route.get("fallback_model") or "")
    if fallback_profile:
        fallback = providers.get(fallback_profile) if isinstance(providers, dict) else None
        if isinstance(fallback, dict) and route_uses_fusion(fallback, {"model": fallback_model or _first_model(fallback)}):
            return _blocked("Fusion fallback cannot resolve to Fusion", route)
    return FusionCheck(True, params=fusion_params(route))


def fusion_params(route: dict[str, Any]) -> dict[str, Any]:
    tool: dict[str, Any] = {"type": "openrouter:fusion"}
    parameters: dict[str, Any] = {}
    analysis = route.get("analysis_models")
    if isinstance(analysis, list) and analysis:
        parameters["analysis_models"] = [str(item) for item in analysis[:8]]
    judge = route.get("judge_model") or route.get("model_for_judge")
    if judge:
        parameters["model"] = str(judge)
    if parameters:
        tool["parameters"] = parameters
    params: dict[str, Any] = {"tools": [tool]}
    if route.get("force_tool"):
        params["tool_choice"] = "required"
    return params


def normalize_fusion_payload(content: str, raw: dict[str, Any]) -> dict[str, Any]:
    loaded = _load_json(content)
    source = raw.get("fusion") if isinstance(raw.get("fusion"), dict) else loaded
    source = source if isinstance(source, dict) else {}
    fields = {
        "consensus": _string_list(source.get("consensus")),
        "contradictions": _string_list(source.get("contradictions")),
        "coverage_gaps": _string_list(source.get("coverage_gaps") or source.get("gaps")),
        "unique_insights": _string_list(source.get("unique_insights")),
        "blind_spots": _string_list(source.get("blind_spots")),
        "panel_models": _string_list(source.get("panel_models") or source.get("analysis_models")),
        "judge_model": str(source.get("judge_model") or source.get("model") or ""),
    }
    return {
        "schema_version": "poor-cli-fusion-v1",
        **fields,
        "raw_response_hash": hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest(),
    }


def write_fusion_artifact(store: RunStore, run_id: str, role: str, payload: dict[str, Any]) -> None:
    rel = Path(role) / "FUSION.json"
    path = run_artifact_dir(store, run_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    store.put_artifact(run_id=run_id, kind="artifact.fusion", data=text)


def _blocked(reason: str, route: dict[str, Any]) -> FusionCheck:
    fallback_profile = str(route.get("fallback_profile") or "")
    fallback_model = str(route.get("fallback_model") or "")
    fallback = {"profile": fallback_profile, "model": fallback_model} if fallback_profile else None
    return FusionCheck(True, reason=reason, fallback=fallback)


def _first_model(profile: dict[str, Any]) -> str:
    models = profile.get("models")
    return str(models[0]) if isinstance(models, list) and models else ""


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]
