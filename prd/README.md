# `poor-cli` PRD Pack

This directory holds the Product / Engineering Requirements Documents that operationalize the findings in [`LEARNING.md`](../LEARNING.md). Every recommendation in that audit has a PRD here.

**Who reads these:** a coding agent (or a human) picking up a single task. Each PRD is self-contained — it states the problem, points at the exact files and line ranges involved, explains the design, lists acceptance criteria, and draws the boundary so two agents working on adjacent PRDs don't collide.

**👉 Starting out?** Read [`GETTING-STARTED.md`](GETTING-STARTED.md) — it lists which PRDs are ready to claim today, gives the copy-paste prompt template for spawning an agent, and documents the decision/claim/merge workflow.

**Read order for an agent:**
1. Your assigned PRD, top to bottom.
2. Check the `Blocked by` field — if any blocker is unresolved, stop and ask.
3. Check the `Out-of-scope & boundary` section — do not touch files outside your PRD's scope, even if they look related.
4. Ask the PRD owner (the human who assigned you) for clarification on any `DECISION REQUIRED` block before writing code.

---

## Global conventions

- **Python test command:** `make test` (= `python3 -m pytest tests/ -x -q --cov=poor_cli --cov-report=term-missing`). Tests live in `tests/` as `test_*.py`.
- **Python lint:** `make lint` (= `ruff check poor_cli/`).
- **Pre-commit:** ruff (check + format), `luac5.4 -p` for Lua files. Do not bypass with `--no-verify`.
- **CI:** `.github/workflows/tests.yml` runs on Python 3.12 and 3.14. Keep both green.
- **Lua tests:** the project does not ship a Lua test framework today. Any PRD that modifies `nvim-poor-cli/lua/**/*.lua` must add `plenary.nvim` to dev deps and ship `plenary.busted` specs under `nvim-poor-cli/tests/`. (See PRD 068 for the bootstrap.)
- **Git workflow:** one branch per PRD, one PR per branch, PR title starts with `prd-NNN:`. Close PRDs by deleting their file or moving them to `prd/_done/`.
- **Commits:** conventional style, mention the PRD number (e.g., `prd-001: introduce TokenCounter`). Do not amend shared commits.
- **TDD:** preferred. Write the failing test first when the change is behavioral. Document in the PRD's Testing section.

---

## PRD index

Legend — **Wave**: execution wave (1 = start now, 4 = last). **Status**: `draft` / `ready` / `claimed` / `in-progress` / `review` / `done`. **Conflicts**: files this PRD mutates heavily; PRDs touching the same file must serialize.

### Wave 1 — P0 correctness fixes (start immediately, mostly parallel)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 001 | [Unify token counting](001-token-counter-unification.md) | ready | — | 017, 018 (core.py) |
| 002 | [Async-only permission callback](002-async-only-permission-callback.md) | ready | — | 017 (core.py) |
| 003 | [Schema-version persisted state](003-schema-version-persisted-state.md) | ready | — | — |
| 004 | [Fix semantic cache key to hash file contents](004-semantic-cache-content-hash.md) | ready | — | — |
| 005 | [Consolidate `watch.py` and `ide_watch.py`](005-file-watcher-consolidation.md) | ready | — | — |

### Wave 1 — Dead code & repo hygiene (parallel)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 006 | [Remove `_archived/` retired front-ends](006-remove-archived-frontends.md) | ready | — | — |
| 007 | [Decide and execute on stub modules (docker_sandbox / speculative_decoding / rtk_integration)](007-dead-stub-modules-decision.md) | decision | — | — |
| 008 | [Move research modules to `poor_cli/research/`](008-research-module-relocation.md) | ready | 007 | 017 |
| 009 | [README rewrite & stale screenshot purge](009-readme-rewrite-screenshot-purge.md) | ready | — | — |

### Wave 1 — Security posture (parallel, mostly new files)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 010 | [Rate-limit the RPC surface](010-rpc-rate-limiting.md) | ready | — | 019 (runtime.py) |
| 011 | [Audit log rotation, archival, and export](011-audit-log-rotation.md) | ready | — | — |
| 012 | [Keyring-backed credential storage](012-keyring-credential-storage.md) | ready | — | — |
| 013 | [Sandbox the `browser_evaluate` tool](013-browser-tool-js-sandbox.md) | ready | — | — |

### Wave 1 — The three big UX wins (parallel, mostly new Lua files)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 014 | [Diff Review panel with hunk-level accept/reject](014-diff-review-panel.md) | ready | — | — |
| 015 | [Agent Timeline panel (live tool-call visualization)](015-agent-timeline-panel.md) | ready | 025 | — |
| 016 | [Cost HUD — lualine badge, per-turn badges, dashboard](016-cost-hud.md) | ready | — | — |

### Wave 2 — Structural refactors (serialized chain on monoliths)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 017 | [Pre-slice `core.py` into empty section modules](017-core-pre-slice.md) | ready | 001, 002 | everything that touches core.py |
| 018 | [Extract `ContextAssemblyOrchestrator`](018-context-assembly-orchestrator.md) | ready | 017 | 001 |
| 019 | [Partition `server/runtime.py` into `handlers/` packages](019-server-handlers-partition.md) | ready | 010 | anything touching runtime.py |
| 020 | [Introduce `ProviderCapability` enum](020-provider-capability-enum.md) | ready | 017 | — |
| 021 | [CI gate: pin `core.py` under 1,000 lines](021-core-line-count-ci-gate.md) | ready | 017, 018 | — |

### Wave 2 — Backend differentiators (parallel after Wave 2 structural)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 022 | [Wire repo-graph PageRank into file selection](022-pagerank-file-selection.md) | ready | 018 | — |
| 023 | [AGENTS.md support (with CLAUDE.md fallback)](023-agents-md-support.md) | ready | — | — |
| 024 | [MCP 2026 compliance: streamable-HTTP, multi-server, registry](024-mcp-2026-compliance.md) | ready | — | — |
| 025 | [Streaming tool output with backpressure](025-streaming-tool-output.md) | ready | 019 | — |
| 026 | [RTK-lite: Python-side shell output filter (start with `git status`)](026-rtk-lite-shell-filter.md) | ready | — | — |
| 027 | [Non-prefix / block-level prompt caching](027-block-level-prompt-caching.md) | ready | 020 | — |
| 028 | [Per-tool schema-declared output filter](028-tool-output-schema-filter.md) | ready | — | — |

### Wave 3 — Neovim new panels (mostly parallel, new files)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 029 | [Context Explainer panel upgrade](029-context-explainer-panel.md) | ready | 018 | — |
| 030 | [Provider/Model Picker modal](030-provider-model-picker.md) | ready | 020 | — |
| 031 | [Plan Board (kanban for multi-step plans)](031-plan-board-kanban.md) | ready | — | — |
| 032 | [Prompt Library Browser picker](032-prompt-library-picker.md) | ready | 055 | — |
| 033 | [Workflow Starter picker](033-workflow-starter-picker.md) | ready | 055 | — |
| 034 | [Trust Center interactive upgrade](034-trust-center-interactive.md) | ready | — | — |
| 035 | [MCP Registry browser](035-mcp-registry-browser.md) | ready | 024 | — |
| 036 | [Policy Inspector panel](036-policy-inspector-panel.md) | ready | — | — |
| 037 | [Multiplayer Room full-screen](037-multiplayer-room-fullscreen.md) | ready | 064 | — |
| 038 | [Repo Map visualizer](038-repo-map-visualizer.md) | ready | 022 | — |
| 039 | [Conversation Branch Tree](039-conversation-branch-tree.md) | ready | 043 | — |
| 040 | [Onboarding rerun + guided tour](040-onboarding-rerun-tour.md) | ready | — | — |
| 041 | [Savings Dashboard](041-savings-dashboard.md) | ready | 016 | — |
| 042 | [Watch Status panel](042-watch-status-panel.md) | ready | 005 | — |

### Wave 3 — Chat UX (serialized on `chat.lua`)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 043 | [Chat: regenerate + branch tree](043-chat-regenerate-branch-tree.md) | ready | — | 044, 045, 046, 047 |
| 044 | [Chat: copy and apply code-block actions](044-chat-codeblock-actions.md) | ready | 043 | 045, 046, 047 |
| 045 | [Chat: slash command autocomplete](045-chat-slash-autocomplete.md) | ready | 044 | 046, 047 |
| 046 | [Chat: `@`-mention picker (file, image, LSP)](046-chat-mention-picker.md) | ready | 045, 055 | 047 |
| 047 | [Chat: polish bundle — edit/resend, per-message cost badges, export](047-chat-polish-bundle.md) | ready | 046 | — |

### Wave 3 — Inline completion (serialized on `inline.lua`)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 048 | [Inline: accept-line key + preview split](048-inline-accept-line-preview.md) | ready | — | 049 |
| 049 | [Inline: cycle alternatives + syntax-region filter](049-inline-cycle-syntax-filter.md) | ready | 048 | — |

### Wave 3 — Ecosystem integrations (parallel, new adapter files)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 050 | [`trouble.nvim` integration](050-trouble-integration.md) | ready | — | — |
| 051 | [`gitsigns.nvim` bridge for AI-authored hunks](051-gitsigns-ai-hunks.md) | ready | 014 | — |
| 052 | [`snacks.nvim` notifications & dashboard](052-snacks-integration.md) | ready | — | — |
| 053 | [`oil.nvim` file-mention integration](053-oil-file-mention.md) | ready | 046 | — |
| 054 | [`overseer.nvim` long-task integration](054-overseer-integration.md) | ready | — | — |
| 055 | [Picker adapter layer (Telescope / fzf-lua / Snacks)](055-picker-adapter-layer.md) | ready | — | — |
| 056 | [`neogit` integration for commit review](056-neogit-integration.md) | ready | — | — |
| 057 | [`nvim-dap` integration: bug → breakpoint](057-nvim-dap-integration.md) | ready | — | — |

### Wave 3 — Research & benchmarks (parallel)

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 058 | [Ship safe pre-tokenization end-to-end](058-safe-pretokenization-ship.md) | ready | — | — |
| 059 | [Latent communication: ship for Ollama or archive](059-latent-communication-decision.md) | decision | 008 | — |
| 060 | [Publish SWE-bench Lite score](060-swe-bench-lite-publish.md) | ready | — | — |

### Wave 4 — Strategic decision docs

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 061 | [Rename the project](061-rename-decision.md) | decision | — | — |
| 062 | [Pick target audience + single north-star metric](062-audience-north-star.md) | decision | — | — |
| 063 | [Multiplayer: commit or cut](063-multiplayer-commit-or-cut.md) | decision | — | — |
| 064 | [Consolidate extension model (skills / commands / workflows / automation)](064-extension-model-consolidation.md) | decision | — | — |

### Cross-cutting / infra

| # | Title | Status | Blocked by | Conflicts with |
|---|---|---|---|---|
| 065 | [Lua testing infrastructure (plenary.busted + CI)](065-lua-testing-infrastructure.md) | ready | — | — |

---

## Dependency graph (text DAG)

```
P0 fixes (001–005) ──┐
                     ├──► 017 (core pre-slice) ──► 018 (ContextAssembly) ──► 022 (PageRank)
                     │                          ├──► 020 (ProviderCapability) ──► 027, 030
                     │                          └──► 021 (core line-count gate)
                     │
010 (rate limit) ────┼──► 019 (runtime partition) ──► 025 (streaming tool output) ──► 015
                     │
007 (stub decision) ─┴──► 008 (research/ move) ──► 059 (latent decision)

014 (Diff Review) ──► 051 (gitsigns bridge)
016 (Cost HUD) ─────► 041 (Savings Dashboard)
055 (Picker adapter) ──► 032, 033, 046, 053
024 (MCP 2026) ─────► 035 (MCP Registry)
043 ──► 044 ──► 045 ──► 046 ──► 047  (chat serial chain)
048 ──► 049                         (inline serial chain)
```

## Template

New PRDs should start from [`TEMPLATE.md`](TEMPLATE.md) so tooling and agents can rely on a consistent shape.

---

*Generated as part of the LEARNING.md follow-through. Questions about scope or priority: contact the human who assigned this PRD to you.*
