# ruff: noqa: F403,F405
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_payload(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return dict(asdict(value))
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _adaptation_payload(adapt: Any) -> Dict[str, Any]:
    if adapt is None:
        return {}
    stats = getattr(adapt, "stats", None)
    if callable(stats):
        stats = stats()
    to_dict = getattr(stats, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return _to_payload(stats)


def _retuning_payload(core: Any) -> Dict[str, Any]:
    if core is None:
        return {}
    try:
        from poor_cli.budget_retuning import load_latest_tuning
    except Exception:
        return {}
    repo_root = Path(getattr(core, "_repo_root", Path.cwd())).resolve()
    try:
        payload = load_latest_tuning(repo_root / ".poor-cli")
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return {"available": False}
    return {
        "available": True,
        "generatedAt": payload.get("generated_at") or payload.get("date") or "",
        "records": int(payload.get("total_records_analyzed", 0) or 0),
        "estimatedSavingsPct": float(payload.get("estimated_savings_pct", 0.0) or 0.0),
        "budgets": dict(payload.get("budgets", {})) if isinstance(payload.get("budgets"), dict) else {},
    }


class BudgetHudHandlersMixin:
    def _budget_hud_payload(self) -> Dict[str, Any]:
        maybe_core = getattr(self, "_maybe_core", None)
        core = maybe_core() if callable(maybe_core) else getattr(self, "core", None)
        adapt = getattr(core, "_adaptive_budget", None) if core else None
        last_action = getattr(core, "_last_budget_action", None) if core else None
        if last_action is None and core is not None:
            last_action = getattr(core, "_budget_action", None)
        last_outcome = getattr(core, "_last_turn_outcome", None) if core else None
        projected_cost = getattr(core, "_task_cost_usd", 0.0) if core else 0.0
        repo_map = getattr(core, "_last_repo_map_summary", {}) if core else {}
        prompt_decision = getattr(core, "_last_prompt_decision", {}) if core else {}
        compaction = core.get_compaction_status() if core and hasattr(core, "get_compaction_status") else {}
        return {
            "lastAction": _to_payload(last_action),
            "lastOutcome": _to_payload(last_outcome),
            "adaptation": _adaptation_payload(adapt),
            "retuning": _retuning_payload(core),
            "compaction": dict(compaction) if isinstance(compaction, dict) else {},
            "projectedCostUsd": round(float(projected_cost or 0.0), 6),
            "repoMap": dict(repo_map) if isinstance(repo_map, dict) else {},
            "prompt": dict(prompt_decision) if isinstance(prompt_decision, dict) else {},
            "ts": _utc_now(),
        }

    async def handle_budget_hud_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        return self._budget_hud_payload()


@register("poor-cli/budgetHudSnapshot")
async def _rpc_budget_hud_snapshot(ctx, params):
    return await ctx.handle_budget_hud_snapshot(params)
