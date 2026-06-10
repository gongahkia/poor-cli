"""MH5 retrieval mode switch: always-injected vs tool-driven.

Mirrors how humans work: ambient context for beliefs/preferences (always
injected into system prompt), explicit recall for episodic facts (fetched on
demand via a ``recall_memory`` tool call).

Partitioning rule (default):
- Always-injected when ALL of:
    * ``type in ("feedback", "user")``
    * ``content`` is <= ``ALWAYS_INJECT_LINE_LIMIT`` lines (default 10)
    * ``derivation_depth <= 1`` (raw or one-pass distilled; deeper summaries
      go tool-driven so the agent can decide whether to pull the provenance)
- Tool-driven: everything else.

Rules are overridable via ``RetrievalModeConfig``; the partition function
stays the single entry point so UI and instruction-stack callers see one API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .memory import MemoryEntry

ALWAYS_INJECT_LINE_LIMIT = 10
ALWAYS_INJECT_TYPES = frozenset({"feedback", "user"})
ALWAYS_INJECT_MAX_DERIVATION_DEPTH = 1


@dataclass
class RetrievalModeConfig:
    line_limit: int = ALWAYS_INJECT_LINE_LIMIT
    always_inject_types: frozenset = ALWAYS_INJECT_TYPES
    max_derivation_depth: int = ALWAYS_INJECT_MAX_DERIVATION_DEPTH


def is_critical(entry: MemoryEntry, config: RetrievalModeConfig | None = None) -> bool:
    """Return True when the entry qualifies for always-injected ambient context."""
    cfg = config or RetrievalModeConfig()
    if entry.type not in cfg.always_inject_types:
        return False
    if entry.derivation_depth > cfg.max_derivation_depth:
        return False
    lines = entry.content.count("\n") + (1 if entry.content else 0)
    return lines <= cfg.line_limit


def partition(
    entries: Sequence[MemoryEntry],
    config: RetrievalModeConfig | None = None,
) -> Tuple[List[MemoryEntry], List[MemoryEntry]]:
    """Split entries into (always_injected, tool_driven) lists.

    Order within each list is preserved from the input.
    """
    cfg = config or RetrievalModeConfig()
    always: List[MemoryEntry] = []
    tool_driven: List[MemoryEntry] = []
    for entry in entries:
        (always if is_critical(entry, cfg) else tool_driven).append(entry)
    return always, tool_driven


def render_always_injected(entries: Sequence[MemoryEntry]) -> str:
    """Render always-injected memories as a compact prompt prefix block."""
    always, _ = partition(entries)
    if not always:
        return ""
    lines = ["## Critical Memories"]
    for entry in always:
        lines.append(f"- **{entry.name}** ({entry.type}): {entry.description}")
        for line in entry.content.strip().splitlines():
            if line.strip():
                lines.append(f"  {line.rstrip()}")
    return "\n".join(lines)


async def recall_memory(
    query: str,
    *,
    manager=None,
    k: int = 5,
    hybrid: bool = True,
) -> List[MemoryEntry]:
    """Tool-facing recall: agent calls this when it needs episodic memory.

    Runs hybrid retrieval (semantic + keyword) when ``hybrid=True`` and the
    embedding provider is available; falls back to keyword search otherwise.
    Returns tool-driven candidates only — always-injected entries are already
    in the prompt prefix.
    """
    from .memory import MemoryManager
    from .memory_semantic import hybrid_search

    mgr = manager or MemoryManager()
    mgr.load()
    if hybrid:
        candidates = await hybrid_search(mgr, query, max_results=k * 2)
    else:
        candidates = mgr.search(query, max_results=k * 2)
    _, tool_driven = partition(candidates)
    return tool_driven[:k]
