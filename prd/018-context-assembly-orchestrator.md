# PRD 018: Extract `ContextAssemblyOrchestrator`

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** large (2–3w)
- **Blocks:** 022, 029
- **Blocked by:** 001, 017
- **Files it mutates:**
  - `poor_cli/context.py`
  - `poor_cli/context_engine.py`
  - `poor_cli/context_optimizer.py`
  - `poor_cli/context_compressor.py`
  - `poor_cli/history_pruning.py`
  - `poor_cli/core.py` (narrow — replace scattered calls with orchestrator calls)
- **New files it adds:**
  - `poor_cli/context_assembly.py`
  - `tests/test_context_assembly.py`

## 1. Problem

Context assembly is currently scattered across `context.py`, `context_engine.py`, `context_optimizer.py`, `context_compressor.py`, `history_pruning.py`, `repo_graph.py`, and glue in `core.py`. No single class owns the end-to-end pipeline. Fragile to refactor; hard to test; impossible to cache coherently. LEARNING.md §2.1: "No `ContextAssemblyOrchestrator` owns the full pipeline."

## 2. Current state

From `core.py` during a turn: select files → prune history → compress if over budget → count tokens → assemble into a prompt. Each step is a separate function in a separate module, with `core.py` being the only place they come together.

## 3. Goal & non-goals

**Goal:** one class — `ContextAssemblyOrchestrator` — with a `.assemble(turn_input) -> ContextSnapshot` method. Every other module keeps its existing responsibility but is *called by* the orchestrator. Enables the repo-state caching in PRD 022.

**Non-goals:**
- Do not rewrite the selection / compression logic.
- Do not change what content enters context — only how it's assembled.
- Do not remove the existing modules.

## 4. Design

### 4.1 Types

```python
# poor_cli/context_assembly.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ContextFile:
    path: Path
    content: str
    tokens: int
    reason: str   # e.g. "imported-by-target", "pagerank-top-10", "recent-open"
    compressed: bool

@dataclass(frozen=True)
class ContextSnapshot:
    system_prompt: str
    rules: str                      # merged AGENTS.md / CLAUDE.md
    files: list[ContextFile]
    history: list[dict]             # previous turn messages (already pruned)
    tool_schemas: list[dict]
    tokens: dict[str, int]          # breakdown: system, rules, files, history, tools, total
    budget: int                     # target token budget for this turn
    provider: str
    model: str
    key: str                        # hash used for caching (PRD 022)

class ContextAssemblyOrchestrator:
    def __init__(self, core: "PoorCLICore"): ...
    async def assemble(self, *, prompt: str, turn_id: str) -> ContextSnapshot: ...
    def invalidate(self, *, reason: str) -> None: ...
```

### 4.2 Pipeline inside `assemble()`

1. Resolve provider / model / budget via economy config.
2. Select files via `context_engine` (which may later incorporate PageRank via PRD 022).
3. Prune history via `history_pruning`.
4. Assemble rules from AGENTS.md / CLAUDE.md (PRD 023 supplies this; fallback to CLAUDE.md alone for now).
5. Resolve tool schemas.
6. If total tokens > budget, call `context_optimizer` (tiered compaction) then `context_compressor` (LLMLingua) if still over.
7. Count with `TokenCounter` (PRD 001). Write breakdown.
8. Compute `key` = hash of (rules + files content + history hash + tool schemas + provider/model).
9. Return `ContextSnapshot`.

### 4.3 core.py integration

```python
# core.py (after)
async def run_turn(self, prompt, **kw):
    snapshot = await self._context_assembly.assemble(prompt=prompt, turn_id=new_turn_id())
    return await self._agent_loop.run(snapshot, **kw)
```

## 5. Files to create / modify / delete

**Create**
- `poor_cli/context_assembly.py`
- `tests/test_context_assembly.py`

**Modify**
- `poor_cli/core.py` — narrow: use orchestrator; do not refactor anything else.
- `poor_cli/context.py` — expose needed functions; no behavior change.
- `poor_cli/context_engine.py`, `context_optimizer.py`, `context_compressor.py`, `history_pruning.py` — keep; orchestrator calls them.

## 6. Implementation plan

1. Land `context_assembly.py` with types + empty orchestrator.
2. Move glue logic from `core.py::run_turn` into `assemble()`. Behavior-preserving.
3. Replace scattered count-calls with `TokenCounter` (PRD 001) via orchestrator.
4. Write tests that assemble on a fixture repo and assert snapshot shape.
5. Run `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_assemble_returns_snapshot_with_all_fields`
- `test_budget_respected_when_over_calls_optimizer`
- `test_key_stable_when_inputs_unchanged`
- `test_key_changes_when_file_content_changes`

**Done criterion**
- [ ] Orchestrator wired.
- [ ] `core.py::run_turn` uses orchestrator.
- [ ] Snapshot key fit for PRD 022 cache.

## 8. Rollback / risk

Medium. Behavior-preserving; full tests must pass.

## 9. Out-of-scope & boundary

- 🚫 Do not introduce new context sources.
- 🚫 Do not remove `context.py` etc.
- 🚫 Do not integrate PageRank — PRD 022 does that.

## 10. Related PRDs & references

- PRD 001, 017. Enables 022, 029.
- LEARNING.md §2.1.
