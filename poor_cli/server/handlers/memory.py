# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class MemoryHandlersMixin:
    async def handle_memory_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        type_filter = params.get("type") or None
        entries = mgr.list_all(type_filter=type_filter)
        return {"memories": [e.to_dict() for e in entries]}

    async def handle_memory_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.memory import MemoryManager, MemoryEntry
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
        from poor_cli.memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        query = str(params.get("query", "")).strip()
        type_filter = params.get("type") or None
        max_results = int(params.get("maxResults", 10))
        results = mgr.search(query, type_filter=type_filter, max_results=max_results)
        return {"results": [e.to_dict() for e in results]}

    async def handle_memory_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.memory import MemoryManager
        mgr = MemoryManager()
        mgr.load()
        name = str(params.get("name", "")).strip()
        if not name:
            return {"error": "name required"}
        deleted = mgr.delete(name)
        return {"deleted": deleted, "name": name}

    async def handle_memory_review_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MH4: list pending memory candidates awaiting review."""
        from poor_cli.memory import MemoryManager
        from poor_cli.memory_review import list_pending
        mgr = MemoryManager()
        mgr.load()
        entries = list_pending(mgr)
        return {"pending": [e.to_dict() for e in entries]}

    async def handle_memory_review_accept(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MH4: accept a pending memory; optional edited fields override the candidate."""
        from poor_cli.memory import MemoryEntry, MemoryManager
        from poor_cli.memory_review import accept_pending
        mgr = MemoryManager()
        mgr.load()
        filename = str(params.get("filename", "")).strip()
        if not filename:
            return {"error": "filename required"}
        edited = None
        edits = params.get("edits") or {}
        if isinstance(edits, dict) and edits:
            try:
                edited = MemoryEntry(
                    name=str(edits.get("name", filename)).strip() or filename,
                    description=str(edits.get("description", "")).strip(),
                    type=str(edits.get("type", "project")).strip(),
                    content=str(edits.get("content", "")).strip(),
                )
            except Exception as exc:
                return {"error": f"invalid edits: {exc}"}
        result = accept_pending(mgr, filename, edited_entry=edited)
        if result is None:
            return {"accepted": False, "filename": filename}
        return {"accepted": True, "name": result.name, "filename": result.filename}

    async def handle_memory_review_reject(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.memory import MemoryManager
        from poor_cli.memory_review import reject_pending
        mgr = MemoryManager()
        mgr.load()
        filename = str(params.get("filename", "")).strip()
        if not filename:
            return {"error": "filename required"}
        return {"rejected": reject_pending(mgr, filename), "filename": filename}

    async def handle_memory_review_bulk(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Bulk accept-all or reject-all the pending pile."""
        from poor_cli.memory import MemoryManager
        from poor_cli.memory_review import bulk_accept, bulk_reject
        mgr = MemoryManager()
        mgr.load()
        action = str(params.get("action", "")).strip().lower()
        if action == "accept":
            summary = bulk_accept(mgr)
        elif action == "reject":
            summary = bulk_reject(mgr)
        else:
            return {"error": "action must be 'accept' or 'reject'"}
        return summary.to_dict()

    async def handle_memory_expiring(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MH3: list memories due for expiry without mutating anything."""
        from poor_cli.memory import MemoryManager
        from poor_cli.memory_forgetting import MemoryForgetter
        mgr = MemoryManager()
        mgr.load()
        stale = MemoryForgetter(mgr).due_for_expiry()
        return {"expiring": [e.to_dict() for e in stale]}

    async def handle_memory_expire_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """MH3: archive expired memories. dryRun=True returns candidate set only."""
        from poor_cli.memory import MemoryManager
        from poor_cli.memory_forgetting import MemoryForgetter
        mgr = MemoryManager()
        mgr.load()
        dry = bool(params.get("dryRun", False))
        summary = MemoryForgetter(mgr).run_expiry_pass(dry_run=dry)
        return summary.to_dict()


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

@register('poor-cli/memoryReviewList')
async def _rpc_review_list(ctx, params):
    return await ctx.handle_memory_review_list(params)

@register('poor-cli/memoryReviewAccept')
async def _rpc_review_accept(ctx, params):
    return await ctx.handle_memory_review_accept(params)

@register('poor-cli/memoryReviewReject')
async def _rpc_review_reject(ctx, params):
    return await ctx.handle_memory_review_reject(params)

@register('poor-cli/memoryReviewBulk')
async def _rpc_review_bulk(ctx, params):
    return await ctx.handle_memory_review_bulk(params)

@register('poor-cli/memoryExpiring')
async def _rpc_expiring(ctx, params):
    return await ctx.handle_memory_expiring(params)

@register('poor-cli/memoryExpireRun')
async def _rpc_expire_run(ctx, params):
    return await ctx.handle_memory_expire_run(params)
