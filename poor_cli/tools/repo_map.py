from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from poor_cli.repo_map import RepoMap
from poor_cli.tool_blocks import TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


async def handle_repo_map_query(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    repo_root = Path(str(getattr(ctx, "cwd", "") or Path.cwd())).resolve()
    repo_map = RepoMap(repo_root)
    query = str(args.get("query") or "")
    raw_paths = args.get("paths")
    paths = [str(path) for path in raw_paths] if isinstance(raw_paths, list) else []
    limit = max(1, min(100, int(args.get("limit", 30) or 30)))
    symbols = repo_map.hot_symbols(query, limit=limit)
    skeletons = []
    for path in paths:
        skeleton = repo_map.skeleton_for(path)
        if skeleton:
            skeletons.append(skeleton)
    savings = repo_map.estimate_savings(paths)
    return ToolResult(
        ok=True,
        content=[
            TextBlock(text=f"repo map: {len(symbols)} symbols, {len(skeletons)} skeletons"),
            TableBlock(
                columns=["kind", "name", "path", "line"],
                rows=[[s.kind, s.name, s.path, str(s.line)] for s in symbols[:limit]],
            ),
        ],
        metadata={
            "symbols": [symbol.to_dict() for symbol in symbols],
            "skeletons": [skeleton.to_dict() for skeleton in skeletons],
            "savings": savings,
        },
    )


async def repo_map_query(
    query: str = "",
    paths: List[str] | None = None,
    limit: int = 30,
) -> Dict[str, Any]:
    repo_map = RepoMap(Path.cwd())
    symbols = repo_map.hot_symbols(query, limit=limit)
    skeletons = [skeleton for path in (paths or []) if (skeleton := repo_map.skeleton_for(path))]
    return {
        "symbols": [symbol.to_dict() for symbol in symbols],
        "skeletons": [skeleton.to_dict() for skeleton in skeletons],
        "savings": repo_map.estimate_savings(paths or []),
    }


register_tool(
    name="repo_map_query",
    description=(
        "Return top symbols and file skeletons relevant to a query or paths. "
        "Use before opening many files; it costs far fewer tokens than reading full files."
    ),
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": ""},
            "paths": {"type": "array", "items": {"type": "string"}, "default": []},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
        },
        "additionalProperties": False,
    },
    handler=handle_repo_map_query,
    cacheable=True,
    cache_ttl_s=30.0,
    circuit_disabled=True,
)
