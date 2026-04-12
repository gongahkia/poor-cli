# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class MemoryHandlersMixin:
    async def handle_memory_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        type_filter = params.get("type") or None
        entries = mgr.list_all(type_filter=type_filter)
        return {"memories": [e.to_dict() for e in entries]}

    async def handle_memory_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager, MemoryEntry
        mgr = MemoryManager(repo_root=Path.cwd(), prefer_agent_rules=True)
        mgr.load()
        name = str(params.get("name", "")).strip()
        mtype = str(params.get("type", "project")).strip()
        description = str(params.get("description", "")).strip()
        content = str(params.get("content", "")).strip()
        if not name:
            return {"error": "name required"}
        existing = mgr.get(name)
        if existing:
            mgr.update(name, content=content, description=description, type_=mtype)
            return {"status": "updated", "name": name}
        entry = MemoryEntry(name=name, description=description, type=mtype, content=content)
        mgr.save(entry)
        return {"status": "saved", "name": name}

    async def handle_memory_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        query = str(params.get("query", "")).strip()
        type_filter = params.get("type") or None
        max_results = int(params.get("maxResults", 10))
        results = mgr.search(query, type_filter=type_filter, max_results=max_results)
        return {"results": [e.to_dict() for e in results]}

    async def handle_memory_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        name = str(params.get("name", "")).strip()
        if not name:
            return {"error": "name required"}
        deleted = mgr.delete(name)
        return {"deleted": deleted, "name": name}

@register('poor-cli/memoryList')
async def _rpc_153(ctx, params):
    return await ctx.handle_memory_list(params)

@register('poor-cli/memorySave')
async def _rpc_154(ctx, params):
    return await ctx.handle_memory_save(params)

@register('poor-cli/memorySearch')
async def _rpc_155(ctx, params):
    return await ctx.handle_memory_search(params)

@register('poor-cli/memoryDelete')
async def _rpc_156(ctx, params):
    return await ctx.handle_memory_delete(params)
