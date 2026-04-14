# Long-Term TODO

Phase 20 decision: primary audience is (A) cost-conscious hobbyists; north-star is `median_usd_per_completion`. Prioritize cost telemetry, budget guardrails, savings dashboards, model routing, local-provider cost reduction, and first-class multiplayer. Ship latent communication only through `hf_local`; keep Ollama, vLLM, llama-server, SGLang, HF TGI, LM Studio, and cloud providers on text unless they expose hidden-state access.

---

## Critical — Blocking Adoption

### C1. Validate pip install end-to-end
`pip install poor-cli && poor-cli server --stdio` must work on clean Python 3.11/3.12/3.13/3.14 envs across macOS, Linux, Windows. CI smoke tests exist but need real-world validation on fresh machines. The Neovim plugin should auto-start the server via `poor-cli server --stdio`.

### C2. 60-second demo (asciinema/GIF)
No visual demo exists. Record a screencast showing the Neovim plugin: provider selection, budget guardrail, prompt, tool calls, file edit, cost/savings dashboard, checkpoint, undo, chat Share, quick invite, room panel, and driver handoff. Embed in README above the fold.

### C3. Decompose core.py
`core.py` is 4,470 lines — a monolith owning provider orchestration, tool dispatch, permission checks, context management, plan mode, checkpoints, economy, architect mode, and the agentic loop. Split into:
- `core.py` — session lifecycle + orchestration (~500 lines)
- `agent_loop.py` — streaming request/response/tool cycle
- `permission_engine.py` — sandbox enforcement + approval gates
- `context_engine.py` — context budget, compression, file tracking
Target: no file over 1,000 lines. Raise test coverage to 70%+ (currently 40%).

### C4. Add litellm as fallback provider
5 hand-written provider adapters don't scale. litellm unlocks 100+ models and any OpenAI-compatible endpoint. Add `litellm_provider.py` in `providers/` using the existing `BaseProvider` interface. Keep native adapters for Gemini/OpenAI/Anthropic (they have provider-specific features like prompt caching), but use litellm as the catch-all for everything else.

---

## High — Significant Competitive Advantage

### H1. Neovim inline tab completion (FIM) — DONE
Wired through JSON-RPC server. `inline.lua` has ghost-text, `blink.lua`/`cmp.lua` provide completion sources. Verify edge cases: multi-line completions, partial accept, language-specific prompt tuning.

### H2. Git-native auto-commit mode
Config field `auto_commit: bool` exists on `AgenticConfig` but the implementation is thin. Aider's approach — auto-commit after every AI file mutation with a descriptive message — is simpler than the checkpoint system and gives free undo via `git revert`. Make this the recommended default, ensure it works cleanly with worktree-isolated tasks, and document the workflow.

### H3. Publish benchmark data
No prospective user will switch from Aider/Claude Code without evidence. Run SWE-bench Lite or Aider's benchmark suite against poor-cli with Gemini, OpenAI, and Anthropic providers. Publish pass@1 with cost per completion and methodology. This is a trust benchmark, not the north-star.

### H4. Comprehensive user documentation
README-only docs are insufficient. Write a docs site (or `docs/` markdown files) covering:
- Provider setup (each of 5 providers, with screenshots)
- Economy mode tuning (when to use frugal vs quality)
- Multiplayer setup (signaling server, ngrok, invite flow)
- Neovim plugin config (lazy.nvim, keymaps, telescope integration, lualine)
- Sandbox presets (when to use each, Docker sandbox setup)
- Memory system (types, lifecycle, auto-distillation)
- Automation scheduling (cron patterns, timezone handling)
- Task/agent management (worktree isolation, approval gates)
- Command palette and all 95+ commands

### H5. Neovim plugin as primary marketing surface
The Neovim plugin is now the sole frontend. Polish it to best-in-class:
- Plan mode floating window with step-by-step progress (DONE)
- Command palette via Telescope (DONE)
- Enhanced lualine with provider/sandbox/cost/checkpoints/users (DONE)
- Prompt queue for sequential execution (DONE)
- Verify all 95+ commands work end-to-end through Neovim

---

## Medium — Differentiators

### M1. Multiplayer demo video
Gating deliverable for PRD 063 commit. Record a 2-minute flow: host opens `:PoorCLIChat`, presses `S`, invite copies, joiner runs `:PoorCLICollab join <invite>`, room panel shows both members, host passes driver, joiner sends a suggestion, and both sides see the room event stream.

### M2. Cost dashboard in Neovim
The economy system is the primary differentiation. The lualine `component_full()` shows basic cost info. Add a `:PoorCLICostDashboard` command that opens a rich scratch buffer with: cumulative session cost, cost per tool call, model downshift savings, and projected monthly cost at current rate. Make cost visibility the marketing centerpiece.

### M3. Deepen MCP integration
`mcp_client.py` is ~200 lines, single-server, stdio-only. MCP is becoming the standard for tool extensibility. Add:
- SSE transport support
- Multiple concurrent MCP servers
- Tool namespacing (prefix tools with server name)
- Server discovery from `.poor-cli/mcp.json` config
- Prompt and resource protocol support

### M4. Improve architect mode
Current implementation is ~117 lines with heuristic plan detection. Add:
- Structured plan format contract with the architect model
- Plan validation before passing to editor
- Cost reporting (architect call cost vs editor call cost)
- Configurable architect/editor model pairs per provider

### M5. Custom latent bridge for local inference servers
`hf_local` is the only latent-capable provider today because poor-cli runs Transformers in-process and can access hidden states directly. vLLM, llama-server, SGLang, HF TGI, LM Studio, and Ollama should stay text-only until a backend-specific server extension exists. For each backend considered:
- Add custom endpoints for latent encode/generate handoff, not just OpenAI-compatible text.
- Define tensor serialization for hidden states, `inputs_embeds`, and KV-cache handles, with dtype/device metadata.
- Enforce same model/tokenizer/embedding-space checks before any latent transfer.
- Prove quality and token/cost reduction against text handoff benchmarks before declaring `ProviderCapability.LATENT_COMMUNICATION`.
- Start with one backend, likely vLLM or SGLang; do not attempt all runtimes in one pass.

---

## Low — Polish

### L1. Preview server live reload
`RELOAD_SCRIPT` (SSE-based) is defined but never injected into served HTML. The file watcher sets `_reload_pending` flag but no SSE endpoint serves it. Replace `python3 -m http.server` with a custom asyncio HTTP handler that injects the reload script and serves an SSE endpoint.

### L2. Consolidate watch.py and ide_watch.py
Two different `FileWatcher` classes coexist: `watch.py` (older, async generator pattern) and `ide_watch.py` (newer, callback pattern). Consolidate into one module or clearly document which is canonical.

### L3. Browser tool JS safety
`browser_evaluate()` runs arbitrary JS in page context with no sandboxing. Add CSP-aware evaluation, output size limits, and a denylist for dangerous APIs (localStorage clearing, cookie manipulation, etc.).

### L4. ARCHITECTURE.md + contribution guide
Bus factor = 1. An architecture doc explaining: core engine → JSON-RPC → Neovim plugin, provider abstraction, tool registry, sandbox model, and the checkpoint/session lifecycle would signal openness to contributors.

### L5. Naming consideration
Resolved by PRD 061: the project was renamed from `poor-cli` to `poor-cli`, with legacy aliases retained for one release cycle minimum.

### L6. README rewrite
Update README to reflect Neovim-only focus. Remove TUI screenshots, TUI usage instructions, Telegram mentions. Add Neovim setup as the primary getting-started path, lualine config examples, command palette usage.

---

## Memory & Harness — Open Ownership

These items operationalize the analysis of the memory-system axes (what's stored, when derived, how retrieved, curator, forgetting, provenance) and the "open harness" thesis (if your harness is closed/stateful/API-backed, you don't own your memory). poor-cli is strongly aligned with the open side — this work tightens that alignment and closes known gaps.

### MH1. Memory provenance trail — DONE 2026-04-14
`MemoryEntry` frontmatter now carries `source_session_id`, `source_turn_id`, `source_message_hash` (16-char SHA-256 prefix), `extractor` (`heuristic|llm|user|unknown`), and `derivation_depth` (0 for raw, 1+ for LLM-distilled; `MAX_DERIVATION_DEPTH=2`). `extract_memories_from_history` + `extract_memories_with_llm` + `auto_save_session_memories` accept `source_session_id` kwarg and populate the fields. Round-trip tested in `tests/test_memory_provenance.py`. Unlocks: (a) "where did I learn this?" queries, (b) cascading deletes via MH3, (c) source-aware audit trails.

### MH2. Semantic memory retrieval — DONE 2026-04-14
`poor_cli/memory_semantic.py` ships `semantic_search` and `hybrid_search` on top of `MemoryManager`. Embeddings are cached in `<memory_dir>/embeddings.sqlite3` keyed by filename + content hash; stale caches invalidate on content change. Hybrid retrieval = union of top-K keyword + top-K semantic, deduped, semantic-first ordering. Falls back cleanly to keyword-only when no embedding provider is configured. Tested end-to-end with a deterministic token-overlap fake provider in `tests/test_memory_semantic.py` (6 tests). Integrates with MH8 hit-tracking by reusing `MemoryManager._record_retrieval`. MH7 reranker composes on top of the raw semantic list.

### MH3. Forgetting policy with cascading deletes — DONE 2026-04-14
`poor_cli/memory_forgetting.py` ships `ForgettingPolicy` (per-type TTL: feedback=∞, user=365d, project=180d, reference=90d) and `MemoryForgetter` with `due_for_expiry`, `archive`, `purge_source(session_id)`, `run_expiry_pass`. Archive target: `<memory_dir>/archive/<YYYY>-<MM>/` — no destructive deletes, just moves. Recency boost extends TTL by `recency_boost_days=60` when `hit_count >= 1` (composes with MH8). Cascade: `purge_source(session_id)` archives all memories with matching `source_session_id` (composes with MH1). Dry-run mode on all mutating paths. Tested in `tests/test_memory_forgetting.py` (8 tests). User-confirmable end-of-session UX is a Neovim surface (queued separately).

### MH4. In-loop memory review UX
`auto_memory.py` runs at session end, distills, and silently persists. That is convenient but the curator is fully automated — there is no user-in-loop approval step. Ship:
- After `auto_save_session_memories` proposes candidates, persist them to `~/.poor-cli/memory/_pending/` instead of main directory.
- Neovim command `:PoorCLIMemoryReview` opens a scratch buffer with: one memory per section, accept/edit/reject actions keyed to `a`/`e`/`r`, bulk-accept via `A`.
- A CLI equivalent (`poor-cli memory review`) for non-Neovim surfaces.
- Gate the UX behind `memory.review.mode = "auto" | "prompt"`; default to `"auto"` for hobbyists to keep zero-friction flow.

### MH5. Retrieval mode switch (always-injected vs tool-driven) — DONE 2026-04-14
`poor_cli/memory_retrieval_mode.py` ships `is_critical(entry)`, `partition(entries)`, `render_always_injected(entries)`, and `recall_memory(query)`. Default policy: always-inject when `type in {feedback, user}` AND `content <= 10 lines` AND `derivation_depth <= 1`; everything else is tool-driven. Overridable via `RetrievalModeConfig`. `recall_memory(query, hybrid=True)` composes MH2 + MH1+MH8 partitioning: returns only tool-driven candidates (always-injected ones are already in the system prompt prefix). Tested in `tests/test_memory_retrieval_mode.py` (10 tests). Wiring into `instructions.py` system-prompt composition is the remaining integration step (queued — backend is ready).

### MH6. Harness-portability audit test — DONE 2026-04-14
`tests/test_harness_portability.py` scans every provider adapter for stateful-API patterns (`store=True`, `previous_response_id=`, `managed_agent`, `assistant_id=`, `thread_id=`) + persistent server-session attributes (`self._remote_session`, `self._server_session`, `self._stateful`). Any unguarded pattern fails CI. `docs/HARNESS_PORTABILITY.md` documents the stance, the enforcement catalog, and the opt-in flow for users who want stateful APIs. The audit for Anthropic `cache_control` — confirmed as prefix cache hint (safe), not session-state lookup — is captured in the doc. No provider adapter currently uses stateful APIs, so this lands as pure regression protection.

### MH7. Post-retrieval reranker — DONE 2026-04-14
`poor_cli/memory_reranker.py` ships `mmr(query_vec, candidates, lambda_=0.7, k=5)` and `rerank_semantic_hits(query_vec, hits, embeddings, strategy, ...)`. MMR trades relevance (`lambda_=1.0`) against diversity (`lambda_=0.0`) using cosine sim across existing vectors — no new dependencies. Default 0.7 slightly favors relevance while injecting diversity to dodge the near-duplicate trap. Cross-encoder strategy is stubbed via the `strategy` param (currently falls back to score-order); wiring the HF cross-encoder stays a config-gated follow-up. Tested in `tests/test_memory_reranker.py` (8 tests).

### MH8. Memory access-recency telemetry — DONE 2026-04-14
`MemoryEntry.hit_count` and `last_accessed_at` now live in frontmatter (backward-compatible: missing fields default to `0` / `created_at`). `MemoryManager.search()` and `MemoryManager.get()` take a `record_hit`/`record_hits` flag (default true) that calls `entry.touch()` and persists the updated frontmatter to disk. `list_all()` stays read-only so enumeration doesn't inflate counts. Tested in `tests/test_memory_provenance.py`. Feeds into MH3's decay policy and the eventual `:PoorCLIMemory` picker sort-by-hits UX.

### MH9. Stateful-API portability gate — DONE 2026-04-14
`poor_cli/providers/portability.py` ships `enforce_portability(provider, feature, config)` and `PortabilityViolation`. `Config.providers_portability.strict` defaults to `True`; `allowed_stateful_features` maps provider → opt-in feature codes. Catalog of known non-portable feature codes: `openai_responses_stateful`, `anthropic_managed_agents`, `codex_encrypted_compaction`, `provider_side_memory`. Tested in `tests/test_portability_gate.py`. Provider adapters should call `enforce_portability()` before using any server-side-state path — the gate is now plumbed, future adapters just need to call it.

---

## Compression & Budget Alternatives

These items came out of the alternative-defaults audit for `prompt_compressor.py`, `history_pruning.py`, `token_budget_controller.py`. The CHEAP items that did not block on other work have already shipped (aggressive filler strip in frugal mode). The rest are queued here.

### CB1. Diff-of-diff file context caching
When the agent re-reads the same file across turns, poor-cli currently re-sends the full compressed text each time. Instead, hash the last compressed version per `(file_path, hash(pinned_context))` and on re-read send only the diff since last send, with a `[... N lines unchanged ...]` placeholder for static spans. Estimated token savings: 10–15% on repeated file context (common in long refactor sessions). Implementation: `poor_cli/context/diff_cache.py`, integrate in `ContextAssemblyOrchestrator`.

### CB2. History pruning soft-pin protection — DONE 2026-04-14
`PruningPolicy.soft_pin_evict_factor` (default 1.05) gates soft-pin eviction: turns with `pinned: "soft"` enter the eviction pool only when `current_tokens > target * 1.05`. Legacy `pinned: true` keeps hard-pin semantics. `ScoredTurn.soft_protected` is surfaced on both the dataclass and the annotated metadata. Tested in `tests/test_history_soft_pin.py`. Chat keymap to toggle soft-pin interactively is the remaining Neovim surface and a small follow-up — backend is ready.

### CB3. Per-tool-success adaptive history pruning
Augment the pruner's tool-success weight with historical data: track per-tool success rate in `.poor-cli/tool_success_cache.json`. Tools with >90% success rate get lower pruning-priority (preserve them — they worked); tools with <50% get higher pruning-priority (their results likely aren't load-bearing for the next turn). Self-tuning, no user config. Ship behind `history_pruning.adaptive_tool_scoring = true` opt-in first, flip to default-on after two release cycles of telemetry.

### CB4. Per-session reward moving-average budget adaptation
Current `token_budget_controller.py` uses a static rule-based decision tree. Add session-local adaptation: maintain a rolling buffer of the last 10 turn rewards (`compute_reward`). If trend is negative (tasks getting worse), bump thinking budget +10% and lower compression ratio; if positive, relax both. No offline training; self-contained learning within a session. Integrates with Phase 7A budget controller.

### CB5. Offline weekly budget retuning job
`thinking_budget.py` already has `ThinkingBudgetOptimizer.analyze()` that can re-derive per-task-type budgets from `.poor-cli/budget_logs.jsonl`. Schedule it weekly via an AutomationRule (`0 3 * * 1` — Monday 03:00), dump results into `.poor-cli/budget_tunings/<date>.json`, hotload into running server without restart. No new dependency; just wiring.

### CB6. LLMLingua-2 — explicit NOT-SHIPPING rationale
Leaving this line in the TODO as an archaeological note: LLMLingua-2 was evaluated in Phase 5A. A ~110MB BERT-based compressor for <5% quality delta vs. heuristic is the wrong trade for the cost-conscious-hobbyist audience. If a future audience shift changes this, revisit. Current heuristic path (esp. with MH7 aggressive filler in frugal mode) is sufficient.

---

## Ship-Blocking Partials (from implementation sweep 2026-04-14)

These are the remaining PARTIAL items surfaced by a full audit of every phase in `docs/implementation_waves.md` against the codebase. All are narrow, well-scoped gaps in otherwise-shipped phases.

### SBP1. Phase 2C — Prompt caching parity across providers — DONE 2026-04-14
Documented the caching matrix across all 11 providers in `poor_cli/providers/base.py` module docstring. Anthropic stays the only provider with explicit `cache_control` markers; others rely on their native server-side caches (OpenAI implicit prefix, Gemini `cachedContent` opt-in, vLLM/SGLang/TGI automatic). Follow-up work is gated on telemetry signals showing non-Anthropic cache hit rate materially affects `median_usd_per_completion`.

### SBP2. Phase 4C — Structured output parity (Ollama / OpenRouter)
`poor_cli/structured_output.py` supports `response_format` on Anthropic + OpenAI. Ollama's `/api/chat` supports a `format: "json"` field; OpenRouter routes transparently to the underlying provider. Audit `tool_translator.py` for coverage, add structured output passthrough for both, extend `tests/test_structured_output.py` with 1 case per provider. Estimated ~1 day.

### SBP3. Phase 14A — Diff Review regenerate action — DONE (verified present 2026-04-14)
False positive from the earlier audit. `diff_review.lua:162` binds `gc` to `regen_hunk`, `diff_review.lua:234-238` posts to `diff.regen`; server handler at `poor_cli/server/handlers/diff_review.py:120-121` registers both `diff.regen` and `poor-cli/regenerateHunk`; implementation in `edit_staging.py::regenerate_hunk`. No further action required.

### SBP4. Phase 15E / Phase 20D — Multiplayer 2-minute demo video
Per `docs/phase_20/063_outcome.md`, recording the demo is a hard gating deliverable before using multiplayer as launch-ready marketing proof. Needs a clean Neovim config, two terminals (host + joiner), and ~10 minutes of recording + trim. Not automatable. Owner must record. Already tracked in M1; this entry just restates the block.

### SBP5. Phase 21A — SWE-bench Lite citable number
`bench/swe_bench_lite/run.py`, `make bench-swe`, `tests/test_swe_bench_lite_runner.py`, and `docs/BENCHMARKS.md` are all shipped. BENCHMARKS.md line 20 says "pending / not run". To publish a citable pass@1:
- Owner runs `make bench-swe` with `ARGS="--model gemini-2.5-flash"` (or choice of primary) — the Makefile requires typed confirmation due to API cost.
- Full 300-task suite: budget ~4-12 USD depending on model choice. Owner previously confirmed "start with SWE-bench pending" so this stays queued.
- After the run, publish pass@1 + total cost + timestamp in BENCHMARKS.md + README badge.

---

## Done (recent)

- **2026-04-14** — Per-provider model tier table (Phase 4B #7): `provider_catalog.json` now declares explicit `cheap`/`balanced`/`quality` tiers for all 11 providers; `model_router._build_default_routing_table` honors explicit tier labels with cost fallback.
- **2026-04-14** — POOR.md rule file recognized by `agent_rules.py` + `instructions.py` alongside AGENTS.md/CLAUDE.md; user-global `~/.poor-cli/POOR.md` supported.
- **2026-04-14** — `docs/MCP.md` ships as the full custom-MCP-server guide; README links to it.
- **2026-04-14** — Aggressive filler strip added to `prompt_compressor._compress_heuristic` stage 2b, fires only when ratio ≤ 0.35 (frugal mode).
- **2026-04-14** — `tools_async.py` refactor: 4704 → 3735 LOC via extraction of `_register_tools` body into `_tool_registry_builder.py`.
- **2026-04-14** — `core_turn_lifecycle.py` refactor: 2737 → ≤2700 LOC via extraction of `_save_transcript` + `_save_pruning_sidecar` into `_turn_transcripts.py`.
- **2026-04-14** — Tests fixes: `test_completion_parity.py` (hyphen filenames), `test_research_relocation.py` (module name), `test_run_diagnostics.py` (kwargs drift), `tests/__init__.py` (package marker). Full suite: 1184 passed / 0 failed.
- **2026-04-14** — `docs/phase_20/061_outcome.md` recorded: "Keep poor-cli" decision extracted from inline strategic doc into its own outcome file for consistency with 059/062/063.
- **2026-04-14** — Line-budget caps ratcheted down: `tools_async.py` 4300 → 3800 to lock in the `_tool_registry_builder` extraction gain and prevent regression.
