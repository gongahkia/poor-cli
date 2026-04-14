# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class CostHandlersMixin:
    async def handle_get_session_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return session token/cost totals."""
        self._ensure_initialized()
        return self.core.get_session_cost_summary()

    async def handle_cost_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return session, per-turn, tool, cache, and projection cost summary."""
        self._ensure_initialized()
        return self.core.get_session_summary()

    async def handle_get_economy_savings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return accumulated economy savings metrics."""
        self._ensure_initialized()
        return self.core.get_economy_savings()

    async def handle_savings_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return savings dashboard snapshot."""
        self._ensure_initialized()
        days = int(params.get("days", 30) or 30)
        return self.core.get_savings_summary(days)

    async def handle_savings_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return savings dashboard history."""
        self._ensure_initialized()
        days = int(params.get("days", 30) or 30)
        return self.core.get_savings_history(days)

    async def handle_set_economy_preset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Switch economy preset (frugal | balanced | quality)."""
        self._ensure_initialized()
        preset = str(params.get("preset", "balanced")).strip()
        return self.core.set_economy_preset(preset)

    async def handle_export_cost_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Export full session cost report for accounting/auditing."""
        self._ensure_initialized()
        return self.core.export_cost_report()

    async def handle_get_tokens_visualization(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return text-based context window visualization."""
        self._ensure_initialized()
        return self.core.get_tokens_visualization()

    async def handle_apply_budget_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a named budget template to cost guardrails."""
        self._ensure_initialized()
        template = str(params.get("template", "")).strip()
        return self.core.apply_budget_template(template)

    async def handle_list_budget_templates(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available budget templates."""
        from ..core import PoorCLICore
        return {"templates": PoorCLICore.list_budget_templates()}

    async def handle_get_cost_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return historical session cost data."""
        from ..core import PoorCLICore
        limit = int(params.get("limit", 50))
        entries = PoorCLICore.get_cost_history(limit)
        total_cost = sum(e.get("cost_usd", 0) for e in entries)
        return {"entries": entries, "count": len(entries), "total_cost_usd": round(total_cost, 6)}

    async def handle_get_cache_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return tool cache + response cache + semantic cache stats."""
        self._ensure_initialized()
        return self.core.get_cache_stats()

    async def handle_clear_semantic_cache(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Clear the semantic response cache."""
        self._ensure_initialized()
        return self.core.clear_semantic_cache()

    async def handle_get_context_pressure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return context window utilization metrics."""
        self._ensure_initialized()
        return self.core.get_context_pressure()

    async def handle_get_context_breakdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return token breakdown by category: system, history, tool results."""
        self._ensure_initialized()
        return self.core.get_context_breakdown()

    async def handle_estimate_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate token cost of a message before sending."""
        self._ensure_initialized()
        message = str(params.get("message", ""))
        return self.core.estimate_cost(message)

    async def handle_compare_model_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compare cost between current model and a target model."""
        self._ensure_initialized()
        provider = str(params.get("provider", "")).strip()
        model = str(params.get("model", "")).strip()
        return self.core.compare_model_cost(provider, model)

@register('poor-cli/getSessionCost')
async def _rpc_109(ctx, params):
    return await ctx.handle_get_session_cost(params)

@register('poor-cli/costSummary')
async def _rpc_cost_summary(ctx, params):
    return await ctx.handle_cost_summary(params)

@register('cost.snapshot')
async def _rpc_cost_snapshot(ctx, params):
    return await ctx.handle_cost_summary(params)

@register('cost.history')
async def _rpc_cost_history(ctx, params):
    return await ctx.handle_get_cost_history(params)

@register('poor-cli/getEconomySavings')
async def _rpc_115(ctx, params):
    return await ctx.handle_get_economy_savings(params)

@register('poor-cli/savingsSummary')
async def _rpc_savings_summary(ctx, params):
    return await ctx.handle_savings_summary(params)

@register('savings.snapshot')
async def _rpc_savings_snapshot(ctx, params):
    return await ctx.handle_savings_summary(params)

@register('savings.history')
async def _rpc_savings_history(ctx, params):
    return await ctx.handle_savings_history(params)

@register('poor-cli/setEconomyPreset')
async def _rpc_116(ctx, params):
    return await ctx.handle_set_economy_preset(params)

@register('poor-cli/getCacheStats')
async def _rpc_117(ctx, params):
    return await ctx.handle_get_cache_stats(params)

@register('poor-cli/clearSemanticCache')
async def _rpc_118(ctx, params):
    return await ctx.handle_clear_semantic_cache(params)

@register('poor-cli/getContextPressure')
async def _rpc_119(ctx, params):
    return await ctx.handle_get_context_pressure(params)

@register('poor-cli/getContextBreakdown')
async def _rpc_120(ctx, params):
    return await ctx.handle_get_context_breakdown(params)

@register('poor-cli/estimateCost')
async def _rpc_121(ctx, params):
    return await ctx.handle_estimate_cost(params)

@register('poor-cli/compareModelCost')
async def _rpc_122(ctx, params):
    return await ctx.handle_compare_model_cost(params)

@register('poor-cli/exportCostReport')
async def _rpc_123(ctx, params):
    return await ctx.handle_export_cost_report(params)

@register('poor-cli/getTokensVisualization')
async def _rpc_124(ctx, params):
    return await ctx.handle_get_tokens_visualization(params)

@register('poor-cli/getCostHistory')
async def _rpc_125(ctx, params):
    return await ctx.handle_get_cost_history(params)

@register('poor-cli/applyBudgetTemplate')
async def _rpc_126(ctx, params):
    return await ctx.handle_apply_budget_template(params)

@register('poor-cli/listBudgetTemplates')
async def _rpc_127(ctx, params):
    return await ctx.handle_list_budget_templates(params)
