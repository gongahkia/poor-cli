# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register

_DEFAULT_TOP_N = 50
_MAX_TOP_N = 50


class RepoMapHandlersMixin:
    async def _repo_map_graph(self) -> Any:
        self._ensure_initialized()
        graph = getattr(self.core, "_repo_graph", None)
        if graph is None:
            from poor_cli.repo_graph import RepoGraph

            graph = RepoGraph(getattr(self.core, "_repo_root", Path.cwd()))
            self.core._repo_graph = graph
        ensure = getattr(self.core, "_ensure_repo_graph", None)
        if callable(ensure):
            result = ensure(timeout=5.0)
            if asyncio.iscoroutine(result):
                await result
        stats = graph.get_stats() if hasattr(graph, "get_stats") else {"files": 1}
        if not int(stats.get("files", 0) or 0) and hasattr(graph, "build_index"):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, graph.build_index)
        return graph

    def _repo_map_limit(self, params: Dict[str, Any]) -> int:
        raw = params.get("limit", params.get("topN", params.get("top_n", _DEFAULT_TOP_N)))
        try:
            value = int(raw or _DEFAULT_TOP_N)
        except (TypeError, ValueError):
            value = _DEFAULT_TOP_N
        return max(0, min(_MAX_TOP_N, value))

    def _repo_map_path(self, params: Dict[str, Any]) -> str:
        path = str(params.get("path") or params.get("file") or "").strip()
        if not path:
            raise InvalidParamsError("path required")
        return path

    async def handle_repo_map_top(self, params: Dict[str, Any]) -> Dict[str, Any]:
        graph = await self._repo_map_graph()
        limit = self._repo_map_limit(params)
        if hasattr(graph, "repo_map_top"):
            files = graph.repo_map_top(limit)
        else:
            files = [
                {"path": path, "relative_path": path, "language": "", "score": score, "reason": "pagerank-hub"}
                for path, score in graph.top_k(limit)
            ]
        return {"limit": limit, "files": files}

    async def handle_repo_map_expand(self, params: Dict[str, Any]) -> Dict[str, Any]:
        graph = await self._repo_map_graph()
        path = self._repo_map_path(params)
        if hasattr(graph, "repo_map_expand"):
            return graph.repo_map_expand(path)
        return {"path": path, "imports": [], "imported_by": []}

    async def handle_repo_map_symbols(self, params: Dict[str, Any]) -> Dict[str, Any]:
        graph = await self._repo_map_graph()
        path = self._repo_map_path(params)
        limit = self._repo_map_limit(params)
        if hasattr(graph, "repo_map_symbols"):
            return graph.repo_map_symbols(path, limit=limit)
        return {"path": path, "symbols": []}


@register("repo_map.top")
@register("poor-cli/repoMapTopK")
async def _rpc_repo_map_top(ctx, params):
    return await ctx.handle_repo_map_top(params)


@register("repo_map.expand")
@register("poor-cli/repoMapExpand")
async def _rpc_repo_map_expand(ctx, params):
    return await ctx.handle_repo_map_expand(params)


@register("repo_map.symbols")
@register("poor-cli/repoMapSymbols")
async def _rpc_repo_map_symbols(ctx, params):
    return await ctx.handle_repo_map_symbols(params)
