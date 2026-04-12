# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ContextHandlersMixin:
    async def handle_preview_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview backend-owned context selection for a chat turn."""
        self._ensure_initialized()

        return await self.core.preview_context(
            message=str(params.get("message", "")),
            context_files=params.get("contextFiles"),
            pinned_context_files=params.get("pinnedContextFiles"),
            context_budget_tokens=params.get("contextBudgetTokens"),
        )

    async def handle_preview_mutation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview a mutating file tool without writing to disk."""
        self._ensure_initialized()

        return await self.core.preview_mutation(
            tool_name=str(params.get("toolName", "")),
            arguments=params.get("toolArgs") or {},
        )

    async def handle_compact_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply context management strategy.
        Params: strategy - one of 'auto', 'compact', 'gentle', 'aggressive', 'compress', 'handoff'
        Returns: strategy, summary, messages_before, messages_after"""
        self._ensure_initialized()
        strategy = params.get("strategy", "compact")
        return await self.core.compact_context(strategy)

    async def handle_get_context_explain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Alias for previewContext using context-explanation naming."""
        return await self.handle_preview_context(params)

    async def handle_semantic_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        query = str(params.get("query", "")).strip()
        if not query:
            return {"error": "query required"}
        max_results = int(params.get("maxResults", 10))
        file_filter = params.get("fileFilter") or None
        results = indexer.search(query, max_results=max_results, file_filter=file_filter)
        return {"results": [r.to_dict() for r in results]}

    async def handle_index_codebase(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        force = bool(params.get("force", False))
        stats = indexer.index(force=force)
        return {"stats": stats.to_dict()}

    async def handle_get_index_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        return {"stats": indexer.get_stats().to_dict()}

    async def handle_index_embeddings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        from ..embeddings import get_embedding_provider
        indexer = CodebaseIndexer()
        preferred = params.get("provider") or None
        provider = get_embedding_provider(preferred)
        force = bool(params.get("force", False))
        result = await indexer.index_embeddings(provider=provider, force=force)
        return {"result": result}

    async def handle_vector_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        query = str(params.get("query", "")).strip()
        if not query:
            return {"error": "query required"}
        results = await indexer.vector_search(
            query,
            max_results=int(params.get("maxResults", 10)),
            file_filter=params.get("fileFilter") or None,
        )
        return {"results": [r.to_dict() for r in results]}

    async def handle_hybrid_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..indexer import CodebaseIndexer
        indexer = CodebaseIndexer()
        query = str(params.get("query", "")).strip()
        if not query:
            return {"error": "query required"}
        results = await indexer.hybrid_search(
            query,
            max_results=int(params.get("maxResults", 10)),
            file_filter=params.get("fileFilter") or None,
        )
        return {"results": [r.to_dict() for r in results]}

@register('poor-cli/compactContext')
async def _rpc_32(ctx, params):
    return await ctx.handle_compact_context(params)

@register('poor-cli/previewContext')
async def _rpc_33(ctx, params):
    return await ctx.handle_preview_context(params)

@register('poor-cli/getContextExplain')
async def _rpc_34(ctx, params):
    return await ctx.handle_get_context_explain(params)

@register('poor-cli/previewMutation')
async def _rpc_35(ctx, params):
    return await ctx.handle_preview_mutation(params)

@register('poor-cli/semanticSearch')
async def _rpc_135(ctx, params):
    return await ctx.handle_semantic_search(params)

@register('poor-cli/indexCodebase')
async def _rpc_136(ctx, params):
    return await ctx.handle_index_codebase(params)

@register('poor-cli/getIndexStats')
async def _rpc_137(ctx, params):
    return await ctx.handle_get_index_stats(params)

@register('poor-cli/indexEmbeddings')
async def _rpc_138(ctx, params):
    return await ctx.handle_index_embeddings(params)

@register('poor-cli/vectorSearch')
async def _rpc_139(ctx, params):
    return await ctx.handle_vector_search(params)

@register('poor-cli/hybridSearch')
async def _rpc_140(ctx, params):
    return await ctx.handle_hybrid_search(params)
