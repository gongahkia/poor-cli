# poor-cli Neovim plugin — feature catalog

A full map of user-facing features. Use this as a manual-test checklist: each bullet is a discrete feature or user journey you can exercise.

Opt-in features are flagged `(opt-in)` — enable via `setup({ ux = { <flag> = true } })`.

Command count: ~150 `PoorCLI*` user commands.

---

## Core interaction

- **Chat panel** — `:PoorCLIChat`. Streaming markdown, 100+ slash commands (`/cost`, `/provider`, `/clear`, etc.), `@path` file mentions, queue-while-streaming, per-turn branches + regen, message search `?` (opt-in `chat_history_search`).
- **Inline completion (FIM)** — ghost text as you type. `<Tab>` accept · `<C-Right>` accept word · `<M-l>` accept line · `<M-]>`/`<M-[>` cycle · `<M-?>` preview in split · `<C-Space>` manual trigger.
- **Plan mode** — `:PoorCLIPlan`. Floating window for architect-style multi-step planning before execution.
- **Chat regen + branches** — rerun any assistant turn with temperature bump; `:PoorCLIBranches` to navigate siblings.

## Editing & review

- **Diff review panel** — auto-opens on staged edits. `ga`/`gr` per-hunk · `gA`/`gR` per-file · `gAA` accept-all (opt-in `diff_accept_all`) · `gc` regen with instruction · `gl` toggle unified/side-by-side · `gn`/`gp` next/prev hunk · `]e`/`[e` next/prev edit · `gf` jump to file.
- **Chat-inline diff highlights** — `+`/`-` colored green/red inside chat code blocks even without treesitter's diff parser.
- **Checkpoints** — `:PoorCLICheckpoints*`. Auto-snapshot before AI edits; rewind on demand.
- **Git-native auto-commit** — opt-in in backend config. Commits tagged `AI: <verb> <N> lines in <path>`.
- **Sessions** — `:PoorCLISessions*`. Save, restore, fork chat state per repo.

## Context control

- **Context panel** — `:PoorCLIContextPanel`. `p` pin · `d` drop · `D` drop all non-pinned (opt-in `context_remove_files`) · `/` filter · `o` open. Over-budget badge when tokens exceed limit.
- **Repo map** — `:PoorCLIRepoMap`. Treesitter-aware semantic map; feeds PageRank file selection.
- **@mentions** — type `@` in chat input → file picker opens directly (Claude Code / Codex style). Other sources: type `@buffer:` or `@lsp:` manually. Configurable via `setup({ mentions = { default_source = "file" | "buffer" | "lsp" | "picker" } })`.

## Model, cost, economy

- **Provider picker** — `:PoorCLIProviders`. All 12 providers (Gemini, OpenAI, Anthropic, OpenRouter, LiteLLM, Ollama, LM Studio, llama-server, vLLM, SGLang, HF TGI, hf_local) with price, capability icons, last-used sort.
- **Provider cost compare** — `:PoorCLIProviderCompare` (opt-in `provider_cost_preview`). Δ vs current rates.
- **Cost dashboard** — `:PoorCLICostDashboard`. Session totals, per-turn sparkline, top-10 tools, cache hit-rate, **per-provider cache breakdown**, projected monthly. `e` exports JSON.
- **Savings dashboard** — `:PoorCLISavingsDashboard`. Compression + cache savings, 30-day history.
- **Budget templates** — `:PoorCLIBudget*`. Economy preset (frugal / balanced / quality).
- **Adaptive history pruning (CB3)** — `:PoorCLIAdaptivePruning {auto|on|off}`.

## Memory

- **Critical memories** — `type in {feedback, user}` auto-injected every turn.
- **Memory picker (MH8)** — `:PoorCLIMemoryPicker`. Sort by hits / recency / name.
- **Memory review queue (MH4)** — `:PoorCLIMemoryReview*`. Accept / reject / bulk.
- **Memory expiry dialog (MH3)** — `:PoorCLIMemoryExpire`. Per-item toggle, batch archive.
- **Semantic search** — hybrid keyword + embedding; rerank strategy via `:PoorCLIRerankerStrategy {mmr|cross_encoder|score_order}`.

## Turn pinning (CB2)

- **Per-turn toggle** — `gp` in chat buffer cycles none → soft → hard. Badges inline.
- **Cross-session viewer** — `:PoorCLIPinsList`. `x` unpin · `X` clear all · `<CR>` jump to turn.

## Permissions, trust, sandbox

- **Permission prompts** — guarded-flow approval UI before risky tool calls.
- **Trust Center** — `:PoorCLITrustCenter`. Workspace boundary, trusted roots, audit log.
- **Policy panel** — `:PoorCLIPolicyPanel`. Sandbox preset + permission rules.
- **Audit log export** — `:PoorCLIAuditExport`.

## Multiplayer / collaboration

- **Collab invite** — `:PoorCLICollabQuick` (copy) / `:PoorCLICollab join <invite>`.
- **Room panel** — `:PoorCLIRoom`.
- **Users panel** — `:PoorCLIUsers`. Members, presence, driver role, typing indicators.
- **Collaborators panel** — `:PoorCLICollaboratorsPanel` (opt-in `multiplayer_presence`). Persistent room view.
- **Voting on diffs** — hunks with vote thresholds require quorum; `va`/`vr`/`vc` in diff review.

## Automation, agents, MCP

- **Automations** — `:PoorCLIAutomations*`. Cron + event + slash triggers.
- **Background agents** — `:PoorCLIAgents*`.
- **Tasks panel** — `:PoorCLITasksPanel`.
- **Custom slash commands** — `:PoorCLICustomCommands*`.
- **Prompt library** — `:PoorCLIPromptLibrary*`.
- **Workflows** — `:PoorCLIWorkflows` picker.
- **Skills** — `:PoorCLISkills*`.
- **MCP registry** — `:PoorCLIMCP*`. Mount custom MCP servers (stdio + HTTP); tools auto-namespaced.

## Info panels

Bulk control via `:PoorCLIPanels {open|close|toggle} [names...]` (opt-in `panels_bulk`).

- Tasks, Agents, History, Checkpoints, Queue, Memory, Sessions, Automations — all `:PoorCLI*Panel`. `q` close · `r` refresh.

## Navigation & discoverability

- **Command palette** — `:PoorCLIPalette` (opt-in `command_palette`). Fuzzy-find every `PoorCLI*`.
- **Home nav** — `:PoorCLIHome` (opt-in `home_nav`). Close all aux panels, return to editor.
- **Onboarding wizard** — `:PoorCLIOnboarding`. 9-step first-run setup.
- **Health check** — `:checkhealth poor-cli`. Version, server, keys, integrations. Action hints when `ux.health_actions = true`.
- **Strategies** — `:PoorCLIStrategies`, `:PoorCLIRerankerStrategy`, `:PoorCLIAdaptivePruning`.

## Statusline & indicators

- **Lualine component** — provider, model, streaming state, inline state, tool-call count, compaction, timeline.
- **Cost component** — session cost + delta (auto-inject with `ux.cost_lualine_auto`).
- **Streaming indicator** — `▶ streaming… press q to cancel` virt_text (opt-in `streaming_indicator`).
- **Animated thinking spinner** — 10-frame braille spinner cycles at 80 ms while the model reasons.

## Editor integrations

Required (poor-cli refuses to load without these):

- **snacks.nvim** — notifications, pickers, and the dashboard tile.
- **trouble.nvim** — `:Trouble poor-cli` surfaces assistant findings.
- **nvim-dap** — `<leader>pb` / `<leader>pB` breakpoint + run shortcuts.
- **neogit** — commit hook for auto-commit.

Optional (feature degrades or silently skips if missing):

- **blink.cmp / nvim-cmp** — completion source.
- **gitsigns** — AI hunk glyph (`✱`) on modified lines.
- **oil.nvim** — file mentions from oil buffers.
- **overseer.nvim** — background-task strategy.
- **lualine** — status-line badges.
- **nvim-treesitter** — richer context extraction; falls back to built-in `vim.treesitter`.

## Timeline & debugging

- **Timeline** — `:PoorCLITimeline`. Live tool-call log; cancel / retry / dismiss.
- **Watch panel** — `:PoorCLIWatch`. File-watch event stream.
- **Diagnostics** — `:PoorCLIDiagnostics`. AI-suggested fixes as nvim diagnostics (opt-in).
- **Status** — `:PoorCLIStatus`. RPC state, provider, token counts.
- **Completion reason** — `:PoorCLICompletionReason` (opt-in `completion_reason`). Why inline completion is or isn't active. `:PoorCLICompletionToggle` flips current filetype.

## Deploy & PR tooling

- **Preview server** — `:PoorCLIPreview*`. Live-reload HTTP server for web projects.
- **Deploy** — `:PoorCLIDeploy*`. Target-based deploy shortcuts.
- **PR review** — backend-side; invokable via `make review-pr PR=123`.

## Safety net

- **API key validity probe** — at server init, backend hits each cloud provider's lightweight endpoint. Invalid keys block chat + inline with a one-line notification pointing to `:PoorCLIApiKey`.
- **Permission engine + sandbox** — risky tools gated by rules + OS capability classes.
- **Harness portability gate** — provider adapters blocked from using stateful-API patterns.

---

## Opt-in UX flags reference

All default `false`. Enable via `require('poor-cli').setup({ ux = { <flag> = true, ... } })`.

| Flag | Feature |
|---|---|
| `command_palette` | `:PoorCLIPalette` fuzzy command picker |
| `streaming_indicator` | Chat buffer streaming virt_text |
| `auto_onboarding` | Surfaces onboarding if no API key detected |
| `panels_bulk` | `:PoorCLIPanels {open/close/toggle}` |
| `inline_cycle_hint` | `i/N (M-]/M-[)` counter on ghost text |
| `cost_lualine_auto` | Auto-register cost component in lualine |
| `diff_accept_all` | `gAA` accept-all in diff review |
| `context_remove_files` | `D` drops all non-pinned + budget warning |
| `multiplayer_presence` | `:PoorCLICollaboratorsPanel` |
| `home_nav` | `:PoorCLIHome` back-to-editor |
| `provider_cost_preview` | `:PoorCLIProviderCompare` |
| `inline_status_lualine` | Real-time inline status refresh |
| `chat_history_search` | `?` search in chat buffer |
| `completion_reason` | `:PoorCLICompletionReason` / `:PoorCLICompletionToggle` |
| `health_actions` | `:checkhealth` actionable command hints |

---

## Manual-test journeys

Minimal matrix to exercise everything with reasonable coverage. Each row is one session.

1. **First-run** — delete state dir, `:PoorCLIOnboarding`, complete wizard, verify `:checkhealth poor-cli` reports `ok`.
2. **Chat happy path** — `:PoorCLIChat` → ask a question → observe spinner, streaming, final response; verify cost component updates; `:PoorCLICost` shows the turn.
3. **Diff review** — ask agent to edit a file; diff panel auto-opens; try `ga`, `gr`, `gAA`, `gc`, `gl`, `gf`.
4. **Inline completion** — open a Python file; type a partial expression; accept with `<Tab>`, cycle with `<M-]>`, preview with `<M-?>`.
5. **Provider swap** — `:PoorCLIProviders`, switch model, send another message, verify new model in statusline.
6. **Pin workflow** — pin a turn with `gp` (soft → hard → off). `:PoorCLIPinsList`, `x` unpin, `<CR>` jump.
7. **Memory review** — let a session end, run `:PoorCLIMemoryReview`, accept/reject items.
8. **Memory picker** — `:PoorCLIMemoryPicker`, cycle sort, open an entry.
9. **Memory expire** — `:PoorCLIMemoryExpire`, toggle items, commit.
10. **Context** — `:PoorCLIContextPanel`, pin a file, drop another, send a chat turn and confirm the included files match.
11. **Permissions** — run a tool call requiring approval; verify the approve/deny modal.
12. **Multiplayer** — terminal A: `:PoorCLICollabQuick`; terminal B: `:PoorCLICollab join <invite>`; both see `:PoorCLIUsers`; pass driver; joiner sends suggestion; both see the event.
13. **MCP** — register an MCP server in `.poor-cli/mcp.json`; verify tools appear namespaced.
14. **Panels bulk** — `:PoorCLIPanels open tasks memory`, `:PoorCLIPanels close`.
15. **Home nav** — open multiple panels, `:PoorCLIHome`.
16. **Strategies** — `:PoorCLIRerankerStrategy cross_encoder` (warns if HF not installed), `:PoorCLIAdaptivePruning on`.
17. **API key invalidation** — revoke a key externally, restart nvim, verify the error notification short-circuits `:PoorCLIChat`.
18. **Cost dashboard** — after a few turns, `:PoorCLICostDashboard`; confirm per-provider section populates.
19. **Automation** — define an `AutomationRule` for a cron trigger; verify it runs.
20. **Checkpoint rewind** — agent edits → rewind to a prior checkpoint → files restored.
21. **Session fork** — `:PoorCLISessionsFork`, continue with new session, switch back.
22. **Layout switch** — `require('poor-cli').setup({ layout = { panels = 'vsplit' } })`; confirm `:PoorCLITasksPanel` now opens as a right-side sidebar instead of a float.
