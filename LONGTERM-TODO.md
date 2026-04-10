# Long-Term TODO

---

## Critical — Blocking Adoption

### C1. Validate pip install end-to-end
`pip install poor-cli && poor-cli server --stdio` must work on clean Python 3.11/3.12/3.13/3.14 envs across macOS, Linux, Windows. CI smoke tests exist but need real-world validation on fresh machines. The Neovim plugin should auto-start the server via `poor-cli server --stdio`.

### C2. 60-second demo (asciinema/GIF)
No visual demo exists. Record a screencast showing the Neovim plugin: provider selection → prompt → tool calls → file edit → checkpoint → undo → multiplayer session. Embed in README above the fold.

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
No prospective user will switch from Aider/Claude Code without evidence. Run SWE-bench Lite or Aider's benchmark suite against poor-cli with Gemini, OpenAI, and Anthropic providers. Publish results with methodology. This is the single strongest trust-building action.

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
Multiplayer is the most unique feature. Zero competitors have it. But nobody will try it without seeing it work. Record a 2-minute demo: two Neovim instances in a shared session, hand-off, agenda, role switching. Post to HN/Reddit.

### M2. Cost dashboard in Neovim
The economy system is genuine differentiation. The lualine `component_full()` shows basic cost info. Add a `:PoorCliCostDashboard` command that opens a rich scratch buffer with: cumulative session cost, cost per tool call, model downshift savings, and projected monthly cost at current rate. Make cost visibility the marketing centerpiece.

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
"poor-cli" is memorable but may hurt professional/enterprise adoption. The name suggests "inferior" rather than "economical." Worth considering if targeting broader adoption beyond power users.

### L6. README rewrite
Update README to reflect Neovim-only focus. Remove TUI screenshots, TUI usage instructions, Telegram mentions. Add Neovim setup as the primary getting-started path, lualine config examples, command palette usage.
