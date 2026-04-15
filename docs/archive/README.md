# docs/archive/

Historical roadmap and research docs for work that has already shipped. Kept for archaeological reference; not load-bearing for current users or contributors.

Live user/contributor docs stay under `docs/` (one level up):
- `AUTO_COMMIT.md`, `AUTOMATIONS.md`, `COMMANDS.md` (generated), `ECONOMY.md`, `HARNESS_PORTABILITY.md`, `kv_cache_setup.md`, `LATENT_COMMUNICATION.md`, `M5_LATENT_BRIDGE.md`, `MCP.md`, `MULTIPLAYER.md`, `PROVIDERS.md`, `SANDBOX.md`, `quickstart.md`, `troubleshooting.md`, and `phase_20/063_outcome.md` (the single strategic decision with a still-open gating deliverable).

Repo-root reference docs: `README.md`, `ARCHITECTURE.md`, `POOR.md`, `NORTH_STAR.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `TODO.md`, `LONGTERM-TODO.md`.

## Contents

### Roadmap + implementation PRDs

`implementation_waves.md` is the master roadmap; every phase under it was either shipped (tracked in `LONGTERM-TODO.md`) or deliberately deferred (tracked in `TODO.md`).

| File | Status |
|---|---|
| `implementation_waves.md` | master roadmap; all waves shipped or flagged |
| `phase_01_quick_wins.md` | shipped (RTK, edit formats, compaction, terse mode) |
| `phase_02_context_intelligence.md` | shipped (repo map, tool filter, prompt cache) |
| `phase_03_smart_loading.md` | shipped (skill loading, lazy tools, history pruning) |
| `phase_04_caching_routing.md` | shipped (semantic cache, model router, structured output) |
| `phase_05_advanced_compression.md` | shipped (LLMLingua wiring, AST chunking, failure amnesia) |
| `phase_06_memory_architecture.md` | shipped (working memory; KV cache gated) |
| `phase_07_adaptive_optimization.md` | shipped (budget controller; thinking budgets) |
| `phase_08_research_frontier.md` | shipped + research docs archived |
| `phase_09_repo_cleanup.md` | shipped (stubs purged, research gated, README rewrite) |
| `phase_10_core_refactor.md` | shipped (core decomposition, handler partition) |
| `phase_11_security_hardening.md` | shipped (rate limit, audit rotation, keyring, trust center) |
| `phase_12_context_intelligence_v2.md` | shipped (file_watcher, PageRank selection, AGENTS.md, block cache) |
| `phase_13_protocol_streaming.md` | shipped (MCP 2026, streaming, RTK-lite shell filters) |
| `phase_14_nvim_observability_panels.md` | shipped (diff review, timeline, cost HUD, context, savings, watch) |
| `phase_15_nvim_navigator_panels.md` | shipped (plan board, prompts, workflows, MCP registry, room, repo map, branches) |
| `phase_16_nvim_pickers_onboarding.md` | shipped (picker adapter, onboarding, model picker) |
| `phase_17_chat_interactions.md` | shipped (regen backend, codeblocks, slash autocomplete, mentions, polish) |
| `phase_18_inline_suggestions.md` | shipped (accept-line, cycle, syntax filter) |
| `phase_19_plugin_integrations.md` | shipped (trouble, gitsigns, snacks, oil, overseer, neogit, dap) |
| `phase_20_strategic_decisions.md` | all four decisions recorded (059 ship, 061 keep, 062 hobbyists, 063 commit) |
| `phase_21_testing_benchmarks.md` | 21B Lua tests shipped; 21A SWE-bench run pending — tracked in TODO.md |

### Phase 20 outcome records

`phase_20/059_outcome.md` — Latent communication: ship scoped to `hf_local`.
`phase_20/061_outcome.md` — Rename: keep `poor-cli`.
`phase_20/062_outcome.md` — Audience + metric: cost-conscious hobbyists + `median_usd_per_completion`.

`phase_20/063_outcome.md` stays in `docs/phase_20/` (not archived) because the 2-minute demo video is a gating deliverable that's still pending.

### Research snapshots

Each doc closed out its research question and informed a shipped feature or a deliberate non-ship.

| File | Outcome |
|---|---|
| `LATENT_REASONING.md` | Coconut/Quiet-STaR/CODI all infeasible; `thinking_budget.py` shipped as practical fallback |
| `NEURAL_CODE_EMBEDDINGS.md` | Full neural embeddings not pursued; neural retrieval shipped via `neural_code_encoder.py` |
| `CODE_TOKENIZER_RESEARCH.md` | Aggressive code-tokenizer rewrites shelved; safe pre-tokenizer shipped via Phase 12F |

### Migration + investigation

| File | Outcome |
|---|---|
| `core_pre_slice_placement_map.md` | PRD 017 decomposition map; `core.py` now at 865 LOC, decomposition complete |
| `CACHE_AUDIT.md` | One-shot cache-consolidation audit; recommendations flagged low-priority, kept for future PRD reference |
| `PAIN-POINTS.md` | Pain-point analysis that informed the 2026-Q1 sweep; all entries now captured in `LONGTERM-TODO.md` "Done" sections |
| `SOLUTIONS.md` | Companion to PAIN-POINTS.md with per-problem solution design; all shipped (Phase 01–19) or explicitly rejected (CB6, L5) |

### Go TUI (deprecated 2026-04-15)

The Go Bubble Tea client (`gocli-poor`) is archived at `../archived/go-tui/` (repo root `archived/go-tui/`). It is not built or tested. Phase docs (`phase_go_00` through `phase_go_10`), BENCHMARKS.md, keybindings.md, config.md, orchestration.md, perceived_latency.md, and visual_audit.md live there. See `archived/go-tui/README.md` for the rebuild path.

## Why archive instead of delete?

Archived docs capture intent and trade-offs at decision time. Git history carries the same info, but an archive folder is easier to navigate when a future contributor asks "why did we not do X" or "what did Phase 8C actually try". Archival is ~free; the load-bearing reads stay in `docs/`.

Two docs were deleted outright rather than archived:
- `docs/MULTIPLAYER_DECISION.md` — superseded by `phase_20/063_outcome.md` (two sources of truth invite drift).
