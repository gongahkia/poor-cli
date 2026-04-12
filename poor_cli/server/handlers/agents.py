# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class AgentsHandlersMixin:
    async def handle_create_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        prompt = str(params.get("prompt", "")).strip()
        if not prompt:
            return {"error": "prompt required"}
        agent = mgr.create_agent(
            prompt=prompt,
            sandbox_preset=str(params.get("sandboxPreset", "workspace-write")),
            source=str(params.get("source", "rpc")),
            use_worktree=bool(params.get("useWorktree", True)),
            max_runtime=int(params.get("maxRuntime", 3600)),
            max_cost_usd=float(params.get("maxCostUsd", 5.0)),
            auto_start=bool(params.get("autoStart", False)),
        )
        return {"agent": agent.to_dict()}

    async def handle_list_agents(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        statuses = params.get("statuses") or None
        agents = mgr.list_agents(statuses=statuses)
        return {"agents": [a.to_dict() for a in agents]}

    async def handle_get_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        agent = mgr.get_agent(agent_id)
        if not agent:
            return {"error": f"unknown agent: {agent_id}"}
        return {"agent": agent.to_dict()}

    async def handle_start_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        agent = mgr.start_agent(agent_id)
        return {"agent": agent.to_dict()}

    async def handle_cancel_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        agent = mgr.cancel_agent(agent_id)
        return {"agent": agent.to_dict()}

    async def handle_get_agent_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        tail = int(params.get("tail", 100))
        return {"logs": mgr.get_logs(agent_id, tail=tail)}

    async def handle_get_agent_result(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..agent_runner import AgentManager
        mgr = AgentManager()
        agent_id = str(params.get("agentId", "")).strip()
        return {"result": mgr.get_result(agent_id)}

@register('poor-cli/createAgent')
async def _rpc_141(ctx, params):
    return await ctx.handle_create_agent(params)

@register('poor-cli/listAgents')
async def _rpc_142(ctx, params):
    return await ctx.handle_list_agents(params)

@register('poor-cli/getAgent')
async def _rpc_143(ctx, params):
    return await ctx.handle_get_agent(params)

@register('poor-cli/startAgent')
async def _rpc_144(ctx, params):
    return await ctx.handle_start_agent(params)

@register('poor-cli/cancelAgent')
async def _rpc_145(ctx, params):
    return await ctx.handle_cancel_agent(params)

@register('poor-cli/getAgentLogs')
async def _rpc_146(ctx, params):
    return await ctx.handle_get_agent_logs(params)

@register('poor-cli/getAgentResult')
async def _rpc_147(ctx, params):
    return await ctx.handle_get_agent_result(params)
