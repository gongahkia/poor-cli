# Long-Term TODO

Phase 20 decision: primary audience is (A) cost-conscious hobbyists; north-star is `median_usd_per_completion`. Prioritize cost telemetry, budget guardrails, savings dashboards, model routing, local-provider cost reduction, and first-class multiplayer. Ship latent communication only through `hf_local`; keep Ollama, vLLM, llama-server, SGLang, HF TGI, LM Studio, and cloud providers on text unless they expose hidden-state access.

---

## Critical — Blocking Adoption

### C1. Validate pip install end-to-end
`pip install poor-cli && poor-cli server --stdio` must work on clean Python 3.11/3.12/3.13/3.14 envs across macOS, Linux, Windows. CI smoke tests exist but need real-world validation on fresh machines. The Neovim plugin should auto-start the server via `poor-cli server --stdio`.

### C2. 60-second demo (asciinema/GIF)
No visual demo exists. Record a screencast showing the Neovim plugin: provider selection, budget guardrail, prompt, tool calls, file edit, cost/savings dashboard, checkpoint, undo, chat Share, quick invite, room panel, and driver handoff. Embed in README above the fold.

### C3. Decompose core.py — DONE 2026-04-14 (verified)
`core.py` now 865 LOC (≤1000 target). Split already shipped across `core_agent_loop.py` (1578), `core_tool_dispatch.py` (1611), `core_turn_lifecycle.py` (2668, within temporary cap), `permission_engine.py` (214), `context_engine.py` (241). Line-budget CI gate (PRD 021) protects the decomposition from regression. Further slimming of `core_turn_lifecycle.py` is queued (temporary cap still 2700) but out of scope for C3 proper.

### C4. Add litellm as fallback provider — DONE 2026-04-14
`poor_cli/providers/litellm_provider.py` ships the `LiteLLMProvider` adapter implementing the full BaseProvider surface: `initialize`, `send_message` (with structured_output passthrough + tool-call extraction), `send_message_stream`, `clear_history`, `get_history`, `set_history`, `get_capabilities`, `format_tool_results`. Models follow litellm's `<vendor>/<model>` naming (e.g. `groq/llama-3.1-70b-versatile`, `cohere/command-r-plus`, `mistral/mistral-large-latest`, `bedrock/anthropic.claude-3-sonnet-*`). Tracked in `PROVIDER_CAPABILITIES["litellm"]`, registered in `ProviderFactory`, declared in `provider_catalog.json` with 4 model tiers. Optional dep via `pip install 'poor-cli[litellm]'`. Tested in `tests/test_litellm_provider.py` (10 tests, all passing). Portability gate still active — stateful-API backends are blocked unless opted in. README + catalog updated.

---

## High — Significant Competitive Advantage

### H1. Neovim inline tab completion (FIM) — DONE
Wired through JSON-RPC server. `inline.lua` has ghost-text, `blink.lua`/`cmp.lua` provide completion sources. Verify edge cases: multi-line completions, partial accept, language-specific prompt tuning.

### H2. Git-native auto-commit mode — DONE 2026-04-14
Implementation upgraded: `_maybe_auto_commit` in `tools_async.py` now stages first, checks `git diff --cached --shortstat` to skip no-op writes, detects new-file vs update via `git log`, and produces descriptive commit messages in the form `AI: <verb> <N> lines in <rel_path>`. Gitignored files still skip. Tests in `tests/test_auto_commit.py` cover the flow. Workflow doc added at `docs/AUTO_COMMIT.md` covering enable, message format, worktree interaction, revert patterns, and when-NOT-to-enable. Default stays `false` since auto-committing to a user's dirty tree is destructive — enabling is a conscious opt-in.

### H3. Publish benchmark data
No prospective user will switch from Aider/Claude Code without evidence. Run SWE-bench Lite or Aider's benchmark suite against poor-cli with Gemini, OpenAI, and Anthropic providers. Publish pass@1 with cost per completion and methodology. This is a trust benchmark, not the north-star.

### H4. Comprehensive user documentation — DONE 2026-04-14
Full set now lives under `docs/`:
- `PROVIDERS.md` — all 11 providers, setup, tiers, troubleshooting.
- `MCP.md` — custom MCP servers, transport, allow/deny.
- `HARNESS_PORTABILITY.md` — anti-lock-in stance + enforcement.
- `MULTIPLAYER.md` — protocol, invites, host setup.
- `AUTO_COMMIT.md` — git-native auto-commit workflow.
- `ECONOMY.md` — frugal/balanced/quality preset deep-dive + savings dashboard tour.
- `SANDBOX.md` — preset matrix, capability declarations, OS-level layers, permission rules, audit log.
- `AUTOMATIONS.md` — AutomationRule shape, cron/event/slash triggers, examples.
- `COMMANDS.md` — generated full reference for all 122 slash commands.
- `M5_LATENT_BRIDGE.md` — research bridge spec (open upstream work).
- `BENCHMARKS.md` — pending pass@1 tracking.
- `kv_cache_setup.md` — self-hosted KV cache setup.
- `ARCHITECTURE.md`, `POOR.md`, `NORTH_STAR.md` at repo root.
`scripts/generate_command_docs.py` regenerates COMMANDS.md from the manifest so it never drifts.

### H5. Neovim plugin as primary marketing surface — DONE 2026-04-14 (verified)
All listed surfaces shipped. Plan mode floating window, Telescope command palette, enhanced lualine (cost/savings/provider/sandbox/users badges), prompt queue, inline completion, diff review, timeline, context panel, Savings dashboard, Watch status panel, Trust Center, Policy inspector, multiplayer room — all present in `nvim-poor-cli/lua/poor-cli/`. Command end-to-end verification is a manual QA pass, queued as part of C1 pip-install validation.

---

## Medium — Differentiators

### M1. Multiplayer demo video
Gating deliverable for PRD 063 commit. Record a 2-minute flow: host opens `:PoorCLIChat`, presses `S`, invite copies, joiner runs `:PoorCLICollab join <invite>`, room panel shows both members, host passes driver, joiner sends a suggestion, and both sides see the room event stream.

### M2. Cost dashboard in Neovim — DONE 2026-04-14 (verified)
`:PoorCLICostDashboard` (commands.lua:593) opens `panels/cost_dashboard.lua` rich buffer. Surfaces match PRD 016 spec: session totals + delta, $/turn sparkline, top-10 tools by cost, cache hit-rate / hits / read+write tokens, daily-rate-projected monthly cost. Exports to `<state>/exports/cost-dashboard-*.json` via `e` keymap. Backed by `cost.snapshot` + `cost.history` RPC (`server/handlers/cost.py`). Tests in `tests/test_observability.py` (9 cost cases pass). PRD 047 chat virtual-text badges + lualine HUD also shipped.

### M3. Deepen MCP integration — DONE 2026-04-14 (verified)
Shipped via PRD 024 (Phase 13A). `poor_cli/mcp/` package with stdio + Streamable HTTP transports, multi-server orchestration, tool namespacing (`<server>:<tool>`), discovery from `.poor-cli/mcp.json`, optional registry autodiscover (off by default). `docs/MCP.md` documents custom server loading. `tests/test_mcp_{multi_server,transport,scaffold,rpc}.py` cover the protocol surface.

### M4. Improve architect mode — DONE 2026-04-14
`poor_cli/architect_mode.py` now ships:
- **Named preset pairs** (`PRESET_PAIRS`): `anthropic-gemini`, `openai-gemini`, `anthropic-ollama`, `all-local-hf`. `ArchitectConfig.apply_preset(name)` swaps all four fields at once.
- **Structured plan contract** (`ARCHITECT_PLAN_SCHEMA`) with `ArchitectPlan` + `ArchitectPlanStep` dataclasses and `validate_plan(raw)` that accepts dict or JSON string (including ```json-wrapped). Renders clean `render_prefix` for the editor.
- **Plan validation** before handing to editor: `switch_to_editor` parses + validates; falls back to free-text for unstructured plans; logs soft errors. `parsed_plan` surfaces the validated structure.
- **Per-phase cost tracking**: `record_cost(phase, tokens, usd)` buckets architect vs editor; `cost_breakdown()` exposes total + architect share. Added to `format_status`.

Tested in `tests/test_architect_mode_v2.py` (17 new tests, all passing).

### M5. Custom latent bridge for local inference servers — research DONE 2026-04-14
Research + client-side protocol shipped in `poor_cli/research/latent_bridge.py`:
- `LatentTensorSpec` — wire format with sha256 checksum verification.
- `LatentBridgeConfig` — architect/editor agreement struct with `identity_hash()`.
- `compatibility_check(architect, editor)` — enforces same-model/tokenizer/embedding-space before any transfer; returns mismatch reasons.
- `LatentBackend` abstract interface with `encode` / `generate_from_latent` / `health_check`.
- `VLLMLatentBackend` concrete stub — health check works; encode/generate raise `NotImplementedError` pointing to the server-side patch spec.
- `build_backend(name, config)` factory; `benchmark_note_for_backend` gives per-backend feasibility TL;DR.

Full server-side patch spec + protocol flow + compatibility rules + safety posture documented in `docs/M5_LATENT_BRIDGE.md`. Feasibility ranking: vLLM (v1 target, 1-2 weeks of server patch), SGLang (close second), HF TGI (uncertain), llama-server/Ollama/LM Studio (not recommended), hf_local (already shipped in-process). 17 tests in `tests/test_latent_bridge.py` cover the protocol + compatibility checks + factory. Server-side vLLM patch is explicitly out of scope for poor-cli; a contributor would land that upstream before latent mode for vLLM gets promoted to a ProviderCapability.

---

## Low — Polish

### L1. Preview server live reload — DONE (verified 2026-04-14)
`poor_cli/preview_server.py` already ships a custom asyncio HTTP handler that injects `RELOAD_SCRIPT` into HTML responses and serves `/__poor-cli_reload` as an SSE endpoint. The file watcher bumps `_ReloadState.version` on any change to watched extensions; active SSE clients wake and push a reload event. `tests/test_preview_mode.py` (6 tests) exercises the full loop. Earlier LONGTERM-TODO claim that this was unimplemented was stale.

### L2. Consolidate watch.py and ide_watch.py — DONE 2026-04-14 (verified)
Consolidation shipped via PRD 005. Both legacy files are gone; `poor_cli/file_watcher.py` (15 KB) is the canonical `FileWatcher`. Supports both async-generator (`__aiter__`) and callback (`on_change`) consumers. `tests/test_file_watcher.py` covers both patterns.

### L3. Browser tool JS safety — DONE 2026-04-14 (verified)
Shipped via PRD 013 (Phase 11D). `browser_evaluate` now has size + timeout caps, static denylist scan, JSON-serializable output guard, and audit-log events. `tests/test_browser_tool_sandbox.py` covers allow/deny cases (6 tests pass, 6 skipped for missing Playwright).

### L4. ARCHITECTURE.md + contribution guide — DONE 2026-04-14
`ARCHITECTURE.md` at repo root documents topology, both sides (Lua plugin + Python server), key module map, request lifecycle, provider abstraction, tool registry, sandbox/policy, memory + rules split, sessions/checkpoints, cost telemetry, multiplayer, contributing patterns, and non-obvious conventions (shims, research gating, archival notes). Bus factor improved.

### L5. Naming consideration
Resolved by PRD 061: the project was renamed from `poor-cli` to `poor-cli`, with legacy aliases retained for one release cycle minimum.

### L6. README rewrite — DONE 2026-04-14 (verified)
Shipped via PRD 009 (Phase 9D). README.md opens with Neovim-first pitch, provider table, MCP + multiplayer sections, architecture.png diagram, and links to docs/. No TUI or Telegram residue. Further README polish (asciinema, badges) queued separately.

---

## Memory & Harness — Open Ownership

These items operationalize the analysis of the memory-system axes (what's stored, when derived, how retrieved, curator, forgetting, provenance) and the "open harness" thesis (if your harness is closed/stateful/API-backed, you don't own your memory). poor-cli is strongly aligned with the open side — this work tightens that alignment and closes known gaps.

### MH1. Memory provenance trail — DONE 2026-04-14
`MemoryEntry` frontmatter now carries `source_session_id`, `source_turn_id`, `source_message_hash` (16-char SHA-256 prefix), `extractor` (`heuristic|llm|user|unknown`), and `derivation_depth` (0 for raw, 1+ for LLM-distilled; `MAX_DERIVATION_DEPTH=2`). `extract_memories_from_history` + `extract_memories_with_llm` + `auto_save_session_memories` accept `source_session_id` kwarg and populate the fields. Round-trip tested in `tests/test_memory_provenance.py`. Unlocks: (a) "where did I learn this?" queries, (b) cascading deletes via MH3, (c) source-aware audit trails.

### MH2. Semantic memory retrieval — DONE 2026-04-14
`poor_cli/memory_semantic.py` ships `semantic_search` and `hybrid_search` on top of `MemoryManager`. Embeddings are cached in `<memory_dir>/embeddings.sqlite3` keyed by filename + content hash; stale caches invalidate on content change. Hybrid retrieval = union of top-K keyword + top-K semantic, deduped, semantic-first ordering. Falls back cleanly to keyword-only when no embedding provider is configured. Tested end-to-end with a deterministic token-overlap fake provider in `tests/test_memory_semantic.py` (6 tests). Integrates with MH8 hit-tracking by reusing `MemoryManager._record_retrieval`. MH7 reranker composes on top of the raw semantic list.

### MH3. Forgetting policy with cascading deletes — DONE 2026-04-14
`poor_cli/memory_forgetting.py` ships `ForgettingPolicy` (per-type TTL: feedback=∞, user=365d, project=180d, reference=90d) and `MemoryForgetter` with `due_for_expiry`, `archive`, `purge_source(session_id)`, `run_expiry_pass`. Archive target: `<memory_dir>/archive/<YYYY>-<MM>/` — no destructive deletes, just moves. Recency boost extends TTL by `recency_boost_days=60` when `hit_count >= 1` (composes with MH8). Cascade: `purge_source(session_id)` archives all memories with matching `source_session_id` (composes with MH1). Dry-run mode on all mutating paths. Tested in `tests/test_memory_forgetting.py` (8 tests). User-confirmable end-of-session UX is a Neovim surface (queued separately).

### MH4. In-loop memory review UX — DONE 2026-04-14 (backend)
`poor_cli/memory_review.py` ships the full lifecycle: `stage_pending_memories`, `list_pending`, `accept_pending` (with optional `edited_entry` override), `reject_pending`, `clear_pending`, `bulk_accept`, `bulk_reject`. `auto_save_session_memories(..., review_mode="prompt")` now stages to `<memory_dir>/_pending/` instead of writing live. Provenance (MH1) preserved round-trip through pending → live. Tested in `tests/test_memory_review.py` (9 tests). Neovim `:PoorCLIMemoryReview` scratch buffer and CLI `poor-cli memory review` are thin wrappers queued as Neovim/CLI surface follow-ups — backend is ready.

### MH5. Retrieval mode switch (always-injected vs tool-driven) — DONE 2026-04-14
Backend in `poor_cli/memory_retrieval_mode.py` (`is_critical`, `partition`, `render_always_injected`, `recall_memory`). Default policy: always-inject when `type in {feedback, user}` AND `content <= 10 lines` AND `derivation_depth <= 1`; everything else is tool-driven. **Wiring complete (2026-04-14)**: `instructions._load_critical_memories` injects the always-injected subset as a `Critical Memories` source in every snapshot. Tested in `tests/test_memory_retrieval_mode.py` + `tests/test_critical_memories_injection.py`.

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

### CB1. Diff-of-diff file context caching — DONE 2026-04-14
`poor_cli/context/diff_cache.py` ships `DiffCache` with JSON-backed persistence at `.poor-cli/context/diff_cache.json`. Key = `hash(file_path + pinned_context_hash)`. `ensure_entry(key, current_text)` returns either full text (first time or hash match) or a diff-mode `DiffEmission` with unchanged runs of >= 5 lines collapsed to `[... N lines unchanged ...]` placeholders. Rough tokens-saved estimate included for economy dashboard. TTL default 6 hours, configurable. Tested in `tests/test_diff_cache.py` (12 tests). Integration into `ContextAssemblyOrchestrator.assemble` is the remaining wiring step — the emission API is ready to drop in.

### CB2. History pruning soft-pin protection — DONE 2026-04-14
`PruningPolicy.soft_pin_evict_factor` (default 1.05) gates soft-pin eviction: turns with `pinned: "soft"` enter the eviction pool only when `current_tokens > target * 1.05`. Legacy `pinned: true` keeps hard-pin semantics. `ScoredTurn.soft_protected` is surfaced on both the dataclass and the annotated metadata. Tested in `tests/test_history_soft_pin.py`. Chat keymap to toggle soft-pin interactively is the remaining Neovim surface and a small follow-up — backend is ready.

### CB3. Per-tool-success adaptive history pruning — DONE 2026-04-14
`poor_cli/tool_success_tracker.py` ships `ToolSuccessTracker` with a JSON-backed rolling counter at `.poor-cli/tool_success_cache.json`. `tool_weight_multiplier(name, min_samples=5)` maps rolling success rate to a multiplier in `[0.5, 1.5]`; neutral (1.0) before `min_samples` observations. `HistoryPruner(tool_success_tracker=...)` applies the multiplier only when `PruningPolicy.adaptive_tool_scoring=True`. Default off to keep legacy behavior; flip on after two release cycles of telemetry. Tested in `tests/test_tool_success_tracker.py` (12 tests). Call-site wiring into the turn lifecycle that feeds success/failure to the tracker is a tiny follow-up — tracker + integration are both ready.

### CB4. Per-session reward moving-average budget adaptation — DONE 2026-04-14
`poor_cli/adaptive_budget.py` ships `AdaptiveBudgetController` that composes with `RuleBasedController`. Rolling window of the last 10 rewards drives trend detection: negative trend (<= -0.1) bumps thinking budget +10% and relaxes compression; positive trend (>= 0.1) tightens both. Neutral trend = no change. Requires at least 4 samples before any adjustment. All safety clamps from `token_budget_controller` preserved. Tested in `tests/test_adaptive_budget.py` (9 tests). Thompson sampling was evaluated and deferred — moving-average adaptation is cheap, bounded, explainable, matches the hobbyist audience.

### CB5. Offline weekly budget retuning job — DONE 2026-04-14
`poor_cli/budget_retuning.py` ships `run_retuning(base)`, `list_tunings`, `load_latest_tuning`, `apply_tuning_to_optimizer`. `run_retuning` runs `ThinkingBudgetOptimizer.analyze()` and persists the resulting profile to `.poor-cli/budget_tunings/<YYYY-MM-DD>.json` atomically. `apply_tuning_to_optimizer` hot-loads a saved tuning into a running optimizer — no server restart needed. Idempotent: running twice on the same day overwrites the day's file. Registering the `0 3 * * 1` AutomationRule is a one-line config add in user land (documented at the top of the module). Tested in `tests/test_budget_retuning.py` (10 tests).

### CB6. LLMLingua-2 — explicit NOT-SHIPPING rationale
Leaving this line in the TODO as an archaeological note: LLMLingua-2 was evaluated in Phase 5A. A ~110MB BERT-based compressor for <5% quality delta vs. heuristic is the wrong trade for the cost-conscious-hobbyist audience. If a future audience shift changes this, revisit. Current heuristic path (esp. with MH7 aggressive filler in frugal mode) is sufficient.

---

## Ship-Blocking Partials (from implementation sweep 2026-04-14)

These are the remaining PARTIAL items surfaced by a full audit of every phase in `docs/implementation_waves.md` against the codebase. All are narrow, well-scoped gaps in otherwise-shipped phases.

### SBP1. Phase 2C — Prompt caching parity across providers — DONE 2026-04-14
Documented the caching matrix across all 11 providers in `poor_cli/providers/base.py` module docstring. Anthropic stays the only provider with explicit `cache_control` markers; others rely on their native server-side caches (OpenAI implicit prefix, Gemini `cachedContent` opt-in, vLLM/SGLang/TGI automatic). Follow-up work is gated on telemetry signals showing non-Anthropic cache hit rate materially affects `median_usd_per_completion`.

### SBP2. Phase 4C — Structured output parity (Ollama / OpenRouter) — DONE 2026-04-14
Audit findings: Ollama was already wiring `format: "json"` via `_build_chat_request` when `structured_output` was set (confirmed in `ollama_provider.py:97-98`); OpenRouter inherits the full `response_format` path from `OpenAIProvider` via subclassing and declares `supports_structured_output=True`. Gap was test coverage only. `tests/test_structured_output_parity.py` adds 7 parity cases covering the Ollama format sentinel, the `should_use_structured_output` gate, Ollama's capability declaration, the Ollama request body shape, and OpenRouter's inheritance + capability.

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
