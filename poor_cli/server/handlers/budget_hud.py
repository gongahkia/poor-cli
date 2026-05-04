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
        return {
            "lastAction": _to_payload(last_action),
            "lastOutcome": _to_payload(last_outcome),
            "adaptation": _adaptation_payload(adapt),
            "projectedCostUsd": round(float(projected_cost or 0.0), 6),
            "ts": _utc_now(),
        }

    async def handle_budget_hud_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        return self._budget_hud_payload()


@register("poor-cli/budgetHudSnapshot")
async def _rpc_budget_hud_snapshot(ctx, params):
    return await ctx.handle_budget_hud_snapshot(params)
