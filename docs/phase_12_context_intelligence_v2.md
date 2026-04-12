# Phase 12: Context Intelligence v2

**Priority:** High — second-generation context management built on top of the Phase 1 quick-wins and the repo-graph/semantic-cache work already landed.
**Estimated agents:** 6 (mostly parallel — see collision note below).
**Dependencies:** PRD 001 (provider capability flags), PRD 018 (context assembly contract), PRD 020 (provider capability probing) should be landed or stubbed before 12D. 12B depends on PRD 018.
**Philosophy:** Stop re-reading, re-paying, and re-shipping the same bytes. Consolidate the file watcher, rank files by graph centrality, honor the AGENTS.md open standard, cache at the block level, let tools declare their own output filters, and finally ship the pre-tokenizer that's been sitting in research.

---

## File scope matrix

| Agent | Theme | Creates | Modifies | Deletes |
|-------|-------|---------|----------|---------|
| 12A | File watcher consolidation | `poor_cli/file_watcher.py`, `tests/test_file_watcher.py` | every importer of `watch`/`ide_watch` | `poor_cli/watch.py`, `poor_cli/ide_watch.py` |
| 12B | PageRank file selection | `tests/test_pagerank_selection.py` | `poor_cli/repo_graph.py`, `poor_cli/context_assembly.py`, `poor_cli/context_engine.py` | — |
| 12C | AGENTS.md support | `poor_cli/agent_rules.py`, `tests/test_agent_rules_loader.py` | `poor_cli/instructions.py`, `poor_cli/memory.py`, `poor_cli/auto_memory.py` | — |
| 12D | Block-level prompt caching | `poor_cli/block_cache.py`, `tests/test_block_cache.py` | `poor_cli/providers/anthropic_provider.py`, `poor_cli/providers/openai_provider.py`, `poor_cli/context_assembly.py`, `poor_cli/semantic_cache.py` | — |
| 12E | Tool-output schema filters | `tests/test_tool_output_schema_filter.py` | `poor_cli/tool_output_filter.py`, `poor_cli/tools_async.py` | — |
| 12F | Safe pre-tokenization ship | `tests/test_safe_pretokenization.py` | `poor_cli/code_tokenizer.py`, `poor_cli/context_assembly.py`, `poor_cli/economy.py` | — |

### File-scope collision notes

**`poor_cli/context_assembly.py` is touched by 12B, 12D, and 12F.** This is the central context-assembly module and cannot be split cleanly. Recommended sub-wave ordering:

- **Sub-wave 12.1 (parallel):** 12A, 12C, 12E — fully disjoint.
- **Sub-wave 12.2 (serialized, in order):** 12B → 12D → 12F — each touches `context_assembly.py` for a different concern (scoring hook, block-cache emission, pretokenization hook). Landing them sequentially avoids merge conflicts and lets each rebase cleanly on the previous. Alternative: one human integrator rebases 12D and 12F onto 12B's branch.

No other files collide. 12D's narrow edit to `semantic_cache.py` does not conflict with any other Phase 12 agent.

---

## Agent 12A: File Watcher Consolidation

**Pain points addressed:** Duplicate watcher implementations (LONGTERM-TODO L2, LEARNING §1.6) — bugs fixed in one don't fix the other.
**Expected outcome:** One watcher, one API, two consumption patterns (async-generator + callback) backed by a single event queue.

### What to build

Replace `poor_cli/watch.py` (~31 lines, async-generator) and `poor_cli/ide_watch.py` (~150 lines, callback) with a single `poor_cli/file_watcher.py`. Take `ide_watch.py` as the surviving base (richer, newer). Port the async-generator consumption pattern from `watch.py` as an `__aiter__` method so legacy call sites keep working.

### Implementation details

1. **Survivor selection.** Copy `ide_watch.py` contents to `poor_cli/file_watcher.py`; rename the class to `FileWatcher`.
2. **Dual consumption API.** Keep the callback pattern (`.on_change(cb)`, `.start()`, `.stop()`) and add `async def __aiter__(self) -> AsyncIterator[FileEvent]` for the legacy `async for evt in watcher` pattern. Both share one event queue.
3. **Signature shape.**
   ```python
   class FileWatcher:
       def __init__(self, root: Path, *, debounce_ms: int = 150, ignore: list[str] | None = None): ...
       def on_change(self, callback: Callable[[FileEvent], None]) -> None: ...
       def start(self) -> None: ...
       def stop(self) -> None: ...  # idempotent
       async def __aiter__(self) -> AsyncIterator[FileEvent]: ...
   ```
4. **Call-site migration.** Grep sweep: `from poor_cli.watch|from poor_cli.ide_watch|import watch\b|import ide_watch\b` across `poor_cli/`, `nvim-poor-cli/`, `tests/`. Every hit switches to `from poor_cli.file_watcher import FileWatcher`.
5. **Delete originals.** Remove `poor_cli/watch.py` and `poor_cli/ide_watch.py` only after every importer is migrated and `make test` passes.
6. **Parity only.** Do not add new event types (create/rename/etc.) or new cross-platform logic — unify, don't expand.

### Files to create/modify
- **Create:** `poor_cli/file_watcher.py`, `tests/test_file_watcher.py`
- **Modify:** every importer of the two deleted modules (grep sweep).
- **Delete:** `poor_cli/watch.py`, `poor_cli/ide_watch.py`

### Acceptance criteria
- [ ] `poor_cli/watch.py` and `poor_cli/ide_watch.py` are gone.
- [ ] `poor_cli/file_watcher.py` exists with tests: `test_callback_pattern_receives_events`, `test_async_generator_pattern_receives_events`, `test_gitignore_respected`, `test_stop_is_idempotent`, `test_debounce_coalesces_rapid_changes`.
- [ ] `make lint && make test` clean, no `ImportError`.
- [ ] `poor-cli watch` CLI and `/watch` Neovim slash command still work manually.

### Rollback / risk
Low. If a caller still uses the old generator pattern and we missed it, we get an `ImportError` at runtime. Mitigate by grep-sweep before commit.

---

## Agent 12B: PageRank-Weighted File Selection

**Pain points addressed:** Hub files ranked the same as leaf files in context selection (LEARNING §2.1, §2.2). PageRank is already computed in `repo_graph.py` (~1,717 lines) and persisted in `.poor-cli/repo_graph.db`, but never consulted during selection.
**Expected outcome:** Aider-style file ranking — hubs surface earlier than leaves for the same recency.

### What to build

Expose a narrow `pagerank_score(path) -> float` API on `repo_graph.py`, consume it in `context_assembly`, and compose a combined score `alpha*recency + beta*pagerank + gamma*import_distance` with configurable weights.

### Implementation details

1. **Narrow API on repo_graph.**
   ```python
   def pagerank_score(self, path: str | Path) -> float:   # 0..1, 0 if unindexed
   def top_k(self, k: int = 50) -> list[tuple[str, float]]:
   ```
   Do not touch indexer internals or `repo_graph.db` schema.
2. **Scoring in assembly.**
   ```python
   SCORE_WEIGHTS = {"recency": 0.4, "pagerank": 0.4, "import_distance": 0.2}
   def score(c: FileCandidate) -> float:
       return (SCORE_WEIGHTS["recency"] * recency_score(c)
             + SCORE_WEIGHTS["pagerank"] * repo_graph.pagerank_score(c.path)
             + SCORE_WEIGHTS["import_distance"] * import_distance_score(c))
   ```
3. **Config.** `context.selection_weights` overridable in `preferences.json`. Setting `pagerank=0` disables cleanly.
4. **Cold-start fallback.** `_ensure_repo_graph` is async. If PageRank unavailable within 100 ms, fall back to `{"recency": 0.6, "pagerank": 0, "import_distance": 0.4}` so turns don't stall on first run.
5. **Benchmark.** Pick a small open-source repo, run a handful of canned prompts with and without PageRank weighting, include the before/after file-pick comparison in the PR description.

### Files to create/modify
- **Create:** `tests/test_pagerank_selection.py`
- **Modify:** `poor_cli/repo_graph.py` (narrow export only), `poor_cli/context_assembly.py` (scoring hook), `poor_cli/context_engine.py` (integrate scoring)

### Acceptance criteria
- [ ] `pagerank_score` and `top_k` exported with unit tests.
- [ ] `test_top_k_returns_sorted`, `test_assembly_prefers_pagerank_hubs_over_leaves`, `test_cold_start_fallback_when_graph_missing` all pass.
- [ ] Benchmark in PR shows hub files surface earlier for hub-related prompts.
- [ ] Cold-start path is never blocked on graph build.
- [ ] `pagerank=0` fully disables the influence.

### Rollback / risk
Low. Weights configurable; setting `pagerank=0` disables the influence entirely without removing the code path.

### Out-of-scope
- Do not re-implement PageRank or add a new graph source.
- Do not change the schema of `repo_graph.db` or touch indexer internals.
- Do not add visual output (covered by a separate graph-visualization effort).

---

## Agent 12C: AGENTS.md Support (CLAUDE.md fallback)

**Pain points addressed:** AGENTS.md is the Linux-Foundation-stewarded open standard across Cursor, OpenAI, Google, Sourcegraph, Factory. Users rotating between tools shouldn't have to duplicate rules into a poor-cli-specific format (LEARNING §4.2).
**Expected outcome:** Repo rules read from AGENTS.md by default; CLAUDE.md honored for backward compat; `/memory` writes to AGENTS.md.

### What to build

A new `poor_cli/agent_rules.py` module that discovers rule sources in precedence order, honors YAML frontmatter, and merges them into one string for the context layer.

### Implementation details

1. **Precedence order** (highest first):
   1. `AGENTS.md` in cwd.
   2. `AGENTS.md` in any ancestor directory (closest wins, hierarchical — supports monorepos).
   3. `CLAUDE.md` (back-compat).
   4. `.poor-cli/memory/*.md` entries (existing).
   5. User global `~/.poor-cli/AGENTS.md`.
2. **Loader shape.**
   ```python
   @dataclass
   class RuleSource:
       path: Path
       content: str
       precedence: int
       kind: Literal["agents_md","claude_md","poor_memory","user_global"]

   def load_rules(cwd: Path) -> list[RuleSource]: ...
   def merge(sources: list[RuleSource]) -> str: ...  # dedupes identical paragraphs
   ```
3. **YAML frontmatter** (if present at top of AGENTS.md):
   ```yaml
   ---
   apply_to: ["**/*.py", "!tests/**"]
   priority: 10
   ---
   ```
   Global sources default to `apply_to: ["**/*"]`, `priority: 0`.
4. **Context integration.** `context_assembly.assemble()` calls `agent_rules.load_rules()` and places the merged string in `ContextSnapshot.rules`.
5. **/memory write path.** If `AGENTS.md` exists in repo root, append. Otherwise prompt once: create AGENTS.md? If yes, create and append. If no, fall back to the existing `.poor-cli/memory/` path.
6. **Non-goals.** Do not migrate existing CLAUDE.md content. Do not implement the speculative full AGENTS.md spec — target v1 (markdown + optional frontmatter).

### Files to create/modify
- **Create:** `poor_cli/agent_rules.py`, `tests/test_agent_rules_loader.py`
- **Modify:** `poor_cli/instructions.py` (delegate loading), `poor_cli/memory.py` (route writes through `agent_rules.append`), `poor_cli/auto_memory.py` (same)

### Acceptance criteria
- [ ] `test_agents_md_hierarchy_closest_wins` passes.
- [ ] `test_claude_md_read_when_agents_md_absent` passes.
- [ ] `test_frontmatter_apply_to_globs_respected` passes.
- [ ] `test_memory_write_prefers_agents_md` passes.
- [ ] Hierarchical search works in monorepos (verified by the hierarchy test).

### Rollback / risk
Low. Purely additive — existing CLAUDE.md and `.poor-cli/memory/` paths remain functional as fallbacks.

### Reference
- AGENTS.md open standard: https://agents.md/

---

## Agent 12D: Block-Level Prompt Caching

**Pain points addressed:** Prompt caching only hits on prefix matches today. Re-reading the same file later in a session pays full prefill cost (LEARNING §2.2, PAIN-POINTS #15).
**Expected outcome:** Each context file is its own cache block with its own `cache_control` marker. Re-reading the same file hits cache even if position shifted.

### What to build

A `block_cache.py` utility that annotates the outgoing provider message array with per-block cache markers, plus provider-specific wiring for Anthropic (`cache_control: ephemeral`) and OpenAI (reorder + telemetry).

### Implementation details

1. **Block decomposition.** In `ContextSnapshot`, each file becomes a separate cache block in the outgoing message array. Rules and tool schemas can optionally be their own blocks too.
2. **Anthropic integration (concrete, ship first).** Set `cache_control = {"type": "ephemeral"}` on each file content block. 5-minute TTL per block. Gate via `PROMPT_CACHING_BLOCK` capability flag (PRD 020) — skip silently if unsupported.
3. **OpenAI integration (heuristic).** OpenAI auto-caches prefixes ≥1,024 tokens. Restructure message order so frequently-reused blocks sit near the start. Add telemetry on observed hit rate via response metadata where available.
4. **Telemetry.** Expose cache-hit rate via `/costSummary` (PRD 016). Record per-block hit/miss counts.
5. **Semantic-cache integration.** Narrow touch on `semantic_cache.py`: ensure block-cache markers don't invalidate semantic-cache keys (the semantic cache hashes content, not the cache_control annotations).
6. **Test fixture.** Multi-turn fixture that re-reads the same three files across 5 turns. Measure hit rate before/after.
7. **Non-goals.** Do not implement cross-session caching beyond what providers already offer. Do not cache agent outputs (PRD 004 handles semantic response cache). Do not extend KV cache (research module).

### Files to create/modify
- **Create:** `poor_cli/block_cache.py`, `tests/test_block_cache.py`
- **Modify:** `poor_cli/providers/anthropic_provider.py`, `poor_cli/providers/openai_provider.py`, `poor_cli/context_assembly.py` (emit block markers), `poor_cli/semantic_cache.py` (narrow — stay compatible with block markers)

### Acceptance criteria
- [ ] `test_anthropic_block_cache_marker_emitted` passes.
- [ ] `test_file_reuse_within_session_records_cache_hit` shows hit on second read of same file.
- [ ] `test_unsupported_provider_silently_skips` — no errors on providers without block caching.
- [ ] Measurable hit-rate rise on the 5-turn rework fixture.
- [ ] Anthropic rejects no requests (malformed `cache_control` is the main risk — covered by a negative test).

### Current state reference
Anthropic `cache_control` is currently used only on the system prompt. OpenAI's automatic prefix caching is taken for what it gives. This agent extends caching to per-file blocks.

### Rollback / risk
Medium. Anthropic rejects malformed `cache_control` markers — negative test required. If block caching misbehaves, the capability flag (`PROMPT_CACHING_BLOCK`) can be forced off to revert to prefix-only behavior.

---

## Agent 12E: Per-Tool Output Schema Filter

**Pain points addressed:** Every tool dumps full output into context; MCP and `gh`/`git` responses in particular bloat by nature (PAIN-POINTS #2, LEARNING §2.2).
**Expected outcome:** Built-in tools declare the JSONPath fields (or keep-lines regex) worth preserving; the dispatcher strips the rest before the model sees it. Full output stays reachable via timeline expansion.

### What to build

Extend the `@tool` decorator in `tools_async.py` to accept an `output_filter` argument; extend `tool_output_filter.py` with a `FilterResult` protocol and a set of built-in filters for the noisiest tools; wire the dispatcher to apply the filter post-execution, pre-context.

### Implementation details

1. **Declaration.**
   ```python
   @tool(name="git_status", output_filter=GitStatusFilter())
   async def git_status(...): ...
   ```
2. **Filter protocol.**
   ```python
   class OutputFilter(Protocol):
       def apply(self, raw: str) -> FilterResult: ...

   @dataclass
   class FilterResult:
       output: str
       original_size: int
       filtered_size: int
       dropped_paths: list[str]
   ```
3. **Built-in filters to ship.**
   - `gh_pr_view` → keep `number, title, state, labels, assignees, body, latestReviewDecision`.
   - `git_log` → keep `hash, author_short, date, subject`.
   - `gh_issue_list` → keep `number, title, state, labels, author`.
   - `dependency_inspect` → drop transitive deps unless explicitly requested.
4. **Dispatcher hook.** Apply filter in the post-execution, pre-context stage. Record original/filtered sizes so the timeline can show "filtered from X KB to Y KB".
5. **Full-output retrieval.** Expose raw output via a `poor-cli/toolFullOutput` RPC so the timeline (PRD 015) can fetch it on demand when the user expands a tool call.
6. **Non-goals.** Do not filter user-inspected output (expansion always shows full). Do not filter MCP tool outputs — that's PRD 024's territory (MCP server owns those schemas). Do not change `tool_output_filter.py`'s existing API beyond what's strictly needed.

### Files to create/modify
- **Create:** `tests/test_tool_output_schema_filter.py`
- **Modify:** `poor_cli/tool_output_filter.py`, `poor_cli/tools_async.py` (decorator + per-tool declarations)

### Acceptance criteria
- [ ] Every built-in mutating/read tool has a declared filter (or explicit `output_filter=None` opt-out).
- [ ] `test_git_status_default_filter_drops_advisory_text` passes.
- [ ] `test_filter_stats_populated` passes.
- [ ] `test_full_output_retrievable_via_rpc` passes.
- [ ] Measurable token reduction on a fixture of 10 real tool outputs.

### Current state reference
`tool_output_filter.py` already exists with JSONPath capability but is opt-in per call. No per-tool defaults exist. This agent makes filters declarative and applied by default.

### Rollback / risk
Low. Per-tool opt-out via `output_filter=None`. Full output remains retrievable via RPC so nothing is permanently lost.

---

## Agent 12F: Ship Safe Pre-Tokenization

**Pain points addressed:** `docs/CODE_TOKENIZER_RESEARCH.md` and `bench_safe_pretok.py` show ~6.4% token savings at 99% parseability — but the module has been sitting unshipped (LEARNING §2.2, §1.5).
**Expected outcome:** Opt-in config flag (`context.safe_pretokenization`) runs code files through the safe pretokenizer before adding them to context; savings recorded in economy telemetry. Default off in v1, flip to on in v2 after real-world data.

### What to build

Expose `safe_pretokenize(text, language_hint) -> str` from `code_tokenizer.py`, call it from `context_assembly` when writing file content into the snapshot, and record per-file `original_tokens`/`compressed_tokens` on each `ContextFile` so `economy.py` can surface session-level savings.

### Implementation details

1. **Public API.** Expose `code_tokenizer.safe_pretokenize(text: str, language_hint: str) -> str`. On any failure, return the original text (fail-safe).
2. **Feature flag.** `context.safe_pretokenization = false` default v1. Document plan to flip default to `true` in v2 after observing real-world parseability in the wild.
3. **Assembly integration.** In `context_assembly`, if the flag is on and the file has a recognized language hint, run content through `safe_pretokenize` before adding to the snapshot. Record `original_tokens` and `compressed_tokens` on the resulting `ContextFile`.
4. **Economy tracking.** `economy.py` aggregates per-session `saved_tokens` from the delta and surfaces it in `/costSummary`.
5. **Non-goals.** Do not ship the aggressive mode. Do not re-benchmark — the existing `bench_safe_pretok.py` is the evidence. Do not relocate the module out of `poor_cli/` to `research/`.

### Files to create/modify
- **Create:** `tests/test_safe_pretokenization.py`
- **Modify:** `poor_cli/code_tokenizer.py` (expose `safe_pretokenize`), `poor_cli/context_assembly.py` (opt-in hook), `poor_cli/economy.py` (track savings)

### Acceptance criteria
- [ ] `test_pretokenize_preserves_parseability` passes on fixture.
- [ ] `test_pretokenize_reduces_tokens_by_at_least_5pct` passes on fixture.
- [ ] Feature flag off by default; turning it on end-to-end works without errors.
- [ ] Failure path (e.g. malformed input) returns original content — never crashes context assembly.
- [ ] `/costSummary` reports per-session saved tokens when flag is on.

### Evidence & current state
The `code_tokenizer` module exists; `bench_safe_pretok.py` and `docs/CODE_TOKENIZER_RESEARCH.md` document ~6.4% token savings at 99% parseability. Not yet integrated into context assembly — this agent wires it through behind a feature flag.

### Rollback / risk
Low. Opt-in flag defaults off in v1. Failure path returns original content so context assembly never crashes on malformed input.

---

## Integration checklist for the phase

- [ ] Sub-wave 12.1 (12A, 12C, 12E) landed in parallel — fully disjoint file scopes.
- [ ] Sub-wave 12.2 (12B → 12D → 12F) landed serially, each rebased onto the previous, to avoid `context_assembly.py` conflicts.
- [ ] `make lint && make test` green after each agent lands.
- [ ] `/costSummary` surfaces: block-cache hit rate (12D), tool-output filter savings (12E), pretokenization savings (12F).
- [ ] Neovim `/watch`, `/memory`, and slash-command flows manually smoke-tested post-12A and post-12C.
