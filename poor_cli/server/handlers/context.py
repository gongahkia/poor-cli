# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ContextHandlersMixin:
    def _context_path(self, path: Any) -> str:
        text = str(path or "").strip()
        if not text:
            raise InvalidParamsError("path required")
        return str(Path(text).expanduser().resolve())

    def _context_pins(self) -> List[str]:
        pins = getattr(self.core, "_context_pinned_files", None)
        if not isinstance(pins, list):
            pins = []
            self.core._context_pinned_files = pins
        return pins

    def _context_drops(self) -> Set[str]:
        drops = getattr(self.core, "_context_dropped_files", None)
        if not isinstance(drops, set):
            drops = set(drops or [])
            self.core._context_dropped_files = drops
        return drops

    @staticmethod
    def _context_iter_paths(paths: Any) -> List[Any]:
        if paths is None:
            return []
        if isinstance(paths, str):
            return [paths]
        if isinstance(paths, list):
            return paths
        return []

    def _context_apply_pins_and_drops(
        self,
        context_files: Any,
        pinned_context_files: Any,
    ) -> Tuple[List[str], List[str]]:
        drops = self._context_drops()
        files = []
        for path in self._context_iter_paths(context_files):
            if not str(path or "").strip():
                continue
            normalized = self._context_path(path)
            if normalized not in drops:
                files.append(normalized)
        pins = []
        seen = set()
        for path in self._context_iter_paths(pinned_context_files) + list(self._context_pins()):
            if not str(path or "").strip():
                continue
            normalized = self._context_path(path)
            if normalized in drops or normalized in seen:
                continue
            pins.append(normalized)
            seen.add(normalized)
        return files, pins

    def _serialize_context_snapshot(self, snapshot: Any) -> Dict[str, Any]:
        pins = set(self._context_pins())
        files = []
        for item in getattr(snapshot, "files", ()) or ():
            path = str(getattr(item, "path", "") or "")
            normalized = str(Path(path).expanduser().resolve()) if path else ""
            reason = str(getattr(item, "reason", "") or "selected")
            pinned = normalized in pins or reason == "pinned"
            files.append({
                "path": path,
                "tokens": int(getattr(item, "tokens", 0) or 0),
                "reason": "pinned" if pinned else reason,
                "compressed": bool(getattr(item, "compressed", False) or getattr(item, "pretokenized", False)),
                "pinned": pinned,
            })
        tokens = getattr(snapshot, "tokens", {}) or {}
        return {
            "turnId": str(getattr(snapshot, "turn_id", "") or ""),
            "budget": int(getattr(snapshot, "budget", 0) or 0),
            "used": int(tokens.get("total", 0) or 0),
            "files": files,
        }

    async def handle_context_snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        snapshot = getattr(self.core, "_last_context_snapshot", None)
        if snapshot is None:
            return await self.handle_context_refresh(params)
        return self._serialize_context_snapshot(snapshot)

    async def handle_context_refresh(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        from poor_cli.context_assembly import ContextAssemblyOrchestrator
        snapshot = getattr(self.core, "_last_context_snapshot", None)
        message = str(params.get("message", "") or getattr(snapshot, "user_prompt", "") or "")
        context_files, pinned_context_files = self._context_apply_pins_and_drops(
            params.get("contextFiles") or (),
            params.get("pinnedContextFiles") or (),
        )
        assembler = getattr(self.core, "_context_assembly", None)
        if assembler is None:
            assembler = ContextAssemblyOrchestrator(self.core)
            self.core._context_assembly = assembler
        snapshot = await assembler.assemble(
            prompt=message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=params.get("contextBudgetTokens"),
            activate_tools=False,
        )
        self.core._last_context_snapshot = snapshot
        return self._serialize_context_snapshot(snapshot)

    async def handle_context_pin(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        path = self._context_path(params.get("path"))
        pins = self._context_pins()
        drops = self._context_drops()
        if path in pins:
            pins.remove(path)
            pinned = False
        else:
            pins.append(path)
            drops.discard(path)
            pinned = True
        result = await self.handle_context_refresh(params)
        result.update({"path": path, "pinned": pinned})
        return result

    async def handle_context_drop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        path = self._context_path(params.get("path"))
        pins = self._context_pins()
        if path in pins:
            pins.remove(path)
        self._context_drops().add(path)
        result = await self.handle_context_refresh(params)
        result.update({"path": path, "dropped": True})
        return result

    async def handle_preview_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Preview backend-owned context selection for a chat turn."""
        self._ensure_initialized()

        context_files, pinned_context_files = self._context_apply_pins_and_drops(
            params.get("contextFiles") or (),
            params.get("pinnedContextFiles") or (),
        )
        return await self.core.preview_context(
            message=str(params.get("message", "")),
            context_files=context_files,
            pinned_context_files=pinned_context_files,
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

@register('context.snapshot')
async def _rpc_context_snapshot(ctx, params):
    return await ctx.handle_context_snapshot(params)

@register('context.refresh')
async def _rpc_context_refresh(ctx, params):
    return await ctx.handle_context_refresh(params)

@register('context.pin')
async def _rpc_context_pin(ctx, params):
    return await ctx.handle_context_pin(params)

@register('context.drop')
async def _rpc_context_drop(ctx, params):
    return await ctx.handle_context_drop(params)

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
