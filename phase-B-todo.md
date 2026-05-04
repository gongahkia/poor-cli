# Phase B — Token Wins

**Goal:** measurable token reduction. Compete with Aider's ~4.2× advantage. Build directly on Phase A's HUD so wins are immediately visible.

**Order (commit each separately):**
1. Aider-style repo-map compressor
2. Adaptive prompt optimizer
3. Edit-staging two-phase commit (mandatory diff preview)

**Cross-cutting rules:**
- One commit per feature. Same commit format as Phase A.
- Run full pytest after each. No regressions allowed.
- Add a tiny benchmark for B1 and B2 under `bench/` so the win is measurable.

**Dependencies on Phase A:** B1 + B2 should emit `pre_compact`/`post_compact` and `budget_breach` hooks defined in A3, and write summary lines to the HUD via the same controller side-effects.

---

## B1 — Aider-style repo-map compressor

### Goal
A diff-aware skeleton map of the repo that the agent reads instead of opening every file. Target: reduce file-read tool calls by ≥40% on multi-file edits while keeping symbol resolution accurate.

### Verified anchors
- `poor_cli/repo_graph.py` — exists, ~82k lines, has `ParsedFile` and `RepoGraph` classes.
- `poor_cli/code_tokenizer.py` — token counter for code chunks.
- `poor_cli/indexer.py` — repo indexer.
- `poor_cli/context_assembly.py` — main context builder; final stop before prompt.
- `poor_cli/prompt_compressor.py` — prompt-level compression (LLMLingua optional).

### Files to create
- `poor_cli/repo_map.py` — high-level compressor that consumes `RepoGraph` output.
- `poor_cli/tools/repo_map.py` — exposes `repo_map_query` tool to the agent.
- `bench/repo_map_compression.py` — benchmark harness.
- `tests/test_repo_map.py`.

### Files to modify
- `poor_cli/_tool_registry_builder.py` — register `repo_map_query` (search for an existing tool registration and mirror its style).
- `poor_cli/context_assembly.py` — at context-build time, if total file-read tokens projected > threshold, replace least-relevant file bodies with their repo-map skeleton.
- `poor_cli/skills/core.md` — update guidance: prefer `repo_map_query` for cross-file resolution.
- `poor_cli/server/handlers/repo_map.py` — RPC `poor-cli/repoMapSummary` (returns top-N hot symbols + skeleton stats).

### Data model

```python
# poor_cli/repo_map.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SymbolEntry:
    name: str
    kind: str            # function | class | method | const
    path: str
    line: int
    signature: str       # truncated
    docstring: str       # first line only
    tokens: int          # cost to inline this entry


@dataclass(frozen=True)
class FileSkeleton:
    path: str
    language: str
    top_symbols: List[SymbolEntry]
    total_lines: int
    skeleton_tokens: int     # cost of this skeleton
    full_tokens: int         # cost of the full file


class RepoMap:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def skeleton_for(self, path: str) -> Optional[FileSkeleton]: ...
    def hot_symbols(self, query: str, limit: int = 30) -> List[SymbolEntry]: ...
    def diff_relevant_skeletons(self, changed_files: List[str], k_neighbors: int = 5) -> List[FileSkeleton]: ...
    def estimate_savings(self, requested_paths: List[str]) -> Dict[str, int]:
        """Return {pathOrPlaceholder: tokens} for full-vs-skeleton tradeoff."""
```

Implementation reuses `RepoGraph` for symbol/edge data; do not re-parse. PageRank-like scoring already exists (`bench/bench_pagerank_selection.py` — read for reference).

### Tool exposure
`poor_cli/tools/repo_map.py`:
```python
async def repo_map_query(query: str = "", paths: list[str] | None = None, limit: int = 30) -> dict:
    """Return top symbols + file skeletons relevant to query/paths.
    Costs ~10x fewer tokens than reading the files directly.
    """
```

Schema for tool: `{query?: string, paths?: string[], limit?: int}`. Return: `{symbols: SymbolEntry[], skeletons: FileSkeleton[], savings: {tokensIfRead, tokensIfMap}}`.

### Context-assembly hook
In `context_assembly.py`, after current file selection:
1. Sum projected tokens of file bodies in candidate set.
2. If sum > `repo_map_threshold` (config; default 12_000), replace files in the cold tail (lowest score) with their skeletons until budget fits.
3. Tag replaced entries with `via: repo_map` so the model knows it can call `repo_map_query` to expand.
4. Fire `pre_compact` and `post_compact` hooks (from Phase A3) so the swap shows up in audit.

### Benchmark
`bench/repo_map_compression.py`:
- Pick 10 multi-file fixtures from `tests/fixtures/`.
- For each: assemble context with and without repo-map. Print token delta.
- Exit non-zero if average reduction < 40%.

### Test plan
`tests/test_repo_map.py`:
- Skeleton cost < 50% of full cost on a 200-line Python file.
- `hot_symbols("user_auth")` returns symbols whose names contain `user` or `auth`.
- `diff_relevant_skeletons(changed_files=["a.py"])` includes neighbors from import edges.

### Commit
```
feat(context): aider-style repo-map compressor for multi-file edits

Adds RepoMap skeleton renderer over RepoGraph, repo_map_query tool,
and context_assembly hook that swaps cold-tail file bodies for
skeletons when projected tokens exceed threshold. Bench shows ≥40%
reduction on multi-file fixtures. Fires pre/post_compact hooks.
```

### Acceptance
- Bench script reports ≥40% average reduction.
- Pytest green.
- HUD (A1) shows compaction events when repo-map kicks in.

---

## B2 — Adaptive prompt optimizer

### Goal
Use the existing reward signal in `adaptive_budget.py` to auto-shrink the system prompt and active skill bundle when recent turns show high reward at low complexity. DSPy-lite, no extra deps.

### Verified anchors
- `poor_cli/adaptive_budget.py` — `AdaptiveBudgetController`, `AdaptationStats`, reward window already exists.
- `poor_cli/prompts.py` — system prompt assembly (~22k lines).
- `poor_cli/prompt_compressor.py` — existing prompt-level compressor.
- `poor_cli/skills.py` + `poor_cli/skill_surfacer.py` — surfaces relevant skills to the model.
- `poor_cli/budget_logger.py` — per-turn budget log; reward already lands here.

### Files to create
- `poor_cli/prompt_optimizer.py` — adaptive prompt + skill selector.
- `bench/prompt_optimizer_savings.py` — measure tokens saved.
- `tests/test_prompt_optimizer.py`.

### Files to modify
- `poor_cli/prompts.py` — at prompt assembly, ask `PromptOptimizer.choose(...)` for the system-prompt level (full | trim | minimal) and the skill bundle whitelist.
- `poor_cli/skill_surfacer.py` — accept a whitelist override from the optimizer.
- `poor_cli/adaptive_budget.py` — expose `recent_complexity_estimate()` and `recent_success_rate(window)` if not already public; do not change behavior.

### Algorithm

```python
# poor_cli/prompt_optimizer.py
from dataclasses import dataclass
from typing import List, Set
from .adaptive_budget import AdaptiveBudgetController


@dataclass(frozen=True)
class PromptDecision:
    system_prompt_level: str        # "full" | "trim" | "minimal"
    skill_whitelist: List[str]      # subset of available skill names
    reasoning: str                  # short, audit-friendly


class PromptOptimizer:
    """Choose smaller prompt surfaces when the harness is winning recently."""

    def __init__(self, controller: AdaptiveBudgetController):
        self._ctl = controller

    def choose(self, available_skills: Set[str], task_complexity: float) -> PromptDecision:
        stats = self._ctl.stats()
        recent = stats.avg_reward_recent
        # decision tree (deterministic, explainable):
        if task_complexity < 0.3 and recent > 0.7:
            return PromptDecision("minimal", self._minimal_skills(available_skills),
                                  f"low complexity {task_complexity:.2f}, high reward {recent:.2f}")
        if task_complexity < 0.6 and recent > 0.4:
            return PromptDecision("trim", self._trimmed_skills(available_skills),
                                  f"mid complexity {task_complexity:.2f}, ok reward {recent:.2f}")
        return PromptDecision("full", sorted(available_skills),
                              f"complexity {task_complexity:.2f}, reward {recent:.2f}")

    def _minimal_skills(self, available: Set[str]) -> List[str]:
        keep = {"core", "economy", "readonly"}
        return sorted(s for s in available if s in keep)

    def _trimmed_skills(self, available: Set[str]) -> List[str]:
        drop = {"deployment", "review", "debugging"}
        return sorted(s for s in available if s not in drop)
```

System-prompt levels (define once in `prompts.py`):
- `full` — current default.
- `trim` — strip the long-form examples, keep rules and tool list.
- `minimal` — rules + tool names only (~30% of full).

Each level must be regenerated from the same source-of-truth fragments so they cannot drift apart.

### Telemetry
- Log every decision via `budget_logger.py` with key `prompt_decision`.
- Emit a `notification` hook (Phase A3) whenever the optimizer shifts level (so audit trails capture the choice).
- Surface current level on HUD (A1).

### Benchmark
`bench/prompt_optimizer_savings.py`:
- Replay a fixture of 50 historical prompts with a stub controller pre-loaded with positive trend; assert avg system-prompt tokens reduce ≥25% versus always-`full`.

### Test plan
`tests/test_prompt_optimizer.py`:
- Forced-input cases for the three decision branches.
- Whitelist filters preserve only requested skills.
- Empty available-skills set returns empty whitelist (no crash).

### Commit
```
feat(prompts): adaptive optimizer trims system prompt + skills by reward

Selects full/trim/minimal prompt level and skill whitelist per turn
based on adaptive_budget reward trend and task complexity. Decisions
logged via budget_logger and surfaced on HUD. Bench shows ≥25% prompt
token reduction when reward trend is positive.
```

### Acceptance
- Bench reports ≥25% prompt token reduction in the positive-trend regime.
- HUD shows `prompt:<level>` indicator after a few turns.
- Pytest green.

---

## B3 — Edit-staging two-phase commit (mandatory diff preview)

### Goal
Every write tool stages the change first; the operator (or auto-approver in CI) sees a unified diff and approves before the bytes hit disk. Reuses the existing staging surface; flips it from optional to mandatory and cleans the UX.

### Verified anchors
- `poor_cli/edit_staging.py` — `Hunk`, `PendingEdit`, ~11k lines. Already supports staged proposals.
- `poor_cli/diff_preview.py` — diff renderer.
- `poor_cli/permission_engine.py` — central allow/deny gate.
- Write tools: scan `poor_cli/tools_async.py` and `poor_cli/tools/fs.py` for any function that performs file writes.

### Files to modify
- `poor_cli/edit_staging.py` — add `commit_or_reject(edit_id, decision)` and `set_mandatory(True)`.
- `poor_cli/permission_engine.py` — when a tool is in the write-set, route through staging unless `bypass_diff_preview=True` is set in config.
- `poor_cli/tools_async.py` — write-tool implementations call `stage_edit(...)` instead of `Path.write_text(...)`. Locate every direct `write_text`/`write_bytes`/`os.replace` for repo files and replace.
- `poor_cli/tui/textual_app.py` — handle `poor-cli/editStaged` notification: show diff in `#activity`; expose composer commands `/approve <editId>`, `/reject <editId>`, `/diff <editId>`.
- `poor_cli/server/handlers/diff_review.py` — RPC `poor-cli/editApprove`, `poor-cli/editReject`, `poor-cli/editList`.

### New config
- `poor_cli/repo_config.py` — add key `edit.requireDiffPreview` (default `true`). CI auto-approve uses `agentic.auto_approve_edits: true`.

### Approval flow
1. Write tool returns synchronously with `{"status": "staged", "editId": "..."}`.
2. Backend emits `poor-cli/editStaged` notification with the diff.
3. TUI displays diff and waits for `/approve <id>` or `/reject <id>` (or auto-approve if config allows).
4. Backend commits via `commit_or_reject(id, decision)`; fires `pre_edit` + `post_edit` hooks (A3).
5. If rejected: discard staged content; tool returns `{"status": "rejected"}`. Agent sees the rejection and either retries or asks the user.

### CI auto-approve
- `poor-cli exec --auto-approve-edits` flag bypasses prompts but still records every diff in `audit_log` for review.
- Default in CI YAML in README: `agentic.auto_approve_edits: false`.

### Test plan
`tests/test_edit_staging_two_phase.py` (extend if the file exists, otherwise create):
- Staging a write returns `{status: "staged"}` and does not modify disk.
- `commit_or_reject(editId, "approve")` writes the file.
- `commit_or_reject(editId, "reject")` leaves the file untouched.
- Concurrent edits to different paths are independent.
- Mandatory mode rejects a write that bypasses staging.

### Commit
```
feat(safety): mandatory two-phase commit for all write tools

Every write tool stages its diff and emits poor-cli/editStaged. The
operator (or auto-approver in CI) approves via /approve or rejects
via /reject. Bypass requires explicit config edit.requireDiffPreview
= false. Fires pre_edit/post_edit hooks. Audit log captures all
decisions.
```

### Acceptance
- A `write_file` call in TUI surfaces a staged diff and waits for approval.
- CI mode auto-approves silently when `auto_approve_edits: true`.
- All previous write-tool tests still pass (may need to add `auto_approve` fixture).
- Pytest green.

---

## End-of-phase checklist

- [ ] 3 commits on `main`.
- [ ] Two new bench scripts pass their ratio thresholds (`bench/repo_map_compression.py`, `bench/prompt_optimizer_savings.py`).
- [ ] HUD shows `repo-map` and `prompt:<level>` indicators.
- [ ] Two-phase commit demoable in TUI with a sample `write_file` call.
- [ ] Pytest green.
