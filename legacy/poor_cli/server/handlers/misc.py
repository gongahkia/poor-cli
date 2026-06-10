# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class MiscHandlersMixin:
    async def handle_list_runs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List recent run records from the shared run ledger."""
        self._ensure_initialized()
        source_kind = str(params.get("sourceKind", "") or "").strip() or None
        source_id = str(params.get("sourceId", "") or "").strip() or None
        limit = self._clamp_count(params.get("limit"), default=25, min_value=1, max_value=200)
        return {
            "runs": self.core.list_runs(
                source_kind=source_kind,
                source_id=source_id,
                limit=limit,
            )
        }

    async def handle_list_workflows(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List workflow aliases backed by slash-trigger AutomationRules."""
        del params
        self._ensure_initialized()
        workflows = self.core.list_workflow_templates()
        recommended = next(
            (
                workflow.get("name", "")
                for workflow in workflows
                if workflow.get("recommended")
            ),
            "",
        )
        if not recommended and workflows:
            recommended = str(workflows[0].get("name", "") or "")
        return {"workflows": workflows, "recommended": recommended}

    async def handle_get_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a single workflow alias."""
        self._ensure_initialized()
        name = str(params.get("name", "") or "").strip()
        if not name:
            raise InvalidParamsError("Missing workflow name")
        workflow = self.core.get_workflow_template(name)
        if workflow is None:
            raise InvalidParamsError(f"Unknown workflow: {name}")
        return {"workflow": workflow}

    async def handle_latent_compatibility(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from ..research_loader import load_research_module
            latent_communication = load_research_module("latent_communication", getattr(self.core, "config", None))
            if latent_communication is None:
                return {"feasible": False, "reason": "research.latent_communication.enabled is false"}
            return latent_communication.is_latent_compatible()
        except Exception as e:
            return {"feasible": False, "reason": str(e)}

@register('poor-cli/listRuns')
async def _rpc_37(ctx, params):
    return await ctx.handle_list_runs(params)

@register('poor-cli/listWorkflows')
async def _rpc_38(ctx, params):
    return await ctx.handle_list_workflows(params)

@register('poor-cli/getWorkflow')
async def _rpc_39(ctx, params):
    return await ctx.handle_get_workflow(params)

@register('poor-cli/latentCompatibility')
async def _rpc_172(ctx, params):
    return await ctx.handle_latent_compatibility(params)
