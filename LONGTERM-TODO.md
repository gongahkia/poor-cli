# Long-Term TODO

---

## Critical — Blocking Adoption

### C1. Validate pip install end-to-end
`pip install poor-cli && poor-cli` must work on clean Python 3.11/3.12/3.13/3.14 envs across macOS, Linux, Windows. CI smoke tests exist but need real-world validation on fresh machines. The Rust TUI binary bundling into wheels (`setup.py` custom build) is the fragile point.

### C2. 60-second demo (asciinema/GIF)
No visual demo exists. New users have zero idea what the TUI looks like or how the agent loop works. Record an asciinema showing: provider selection → prompt → tool calls → file edit → checkpoint → undo. Embed in README above the fold.

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

### H1. Neovim inline tab completion (FIM)
The #1 most-used AI coding feature across all competitors. `core.py` already has `build_fim_prompt()` and `inline_complete()`. The Neovim plugin has `inline.lua` (19KB) with ghost-text infrastructure. Wire the FIM endpoint through the JSON-RPC server and connect to Neovim's completion framework (blink.lua/cmp.lua already exist). This makes the Neovim plugin competitive with Copilot/Continue/Cline.

### H2. Git-native auto-commit mode
Config field `auto_commit: bool` exists on `AgenticConfig` but the implementation is thin. Aider's approach — auto-commit after every AI file mutation with a descriptive message — is simpler than the checkpoint system and gives free undo via `git revert`. Make this the recommended default, ensure it works cleanly with worktree-isolated tasks, and document the workflow.

### H3. Publish benchmark data
No prospective user will switch from Aider/Claude Code without evidence. Run SWE-bench Lite or Aider's benchmark suite against poor-cli with Gemini, OpenAI, and Anthropic providers. Publish results with methodology. This is the single strongest trust-building action.

### H4. Comprehensive user documentation
README-only docs are insufficient. Write a docs site (or `docs/` markdown files) covering:
- Provider setup (each of 5 providers, with screenshots)
- Economy mode tuning (when to use frugal vs quality)
- Multiplayer setup (signaling server, ngrok, invite flow)
- Neovim plugin config (lazy.nvim, keymaps, telescope integration)
- Sandbox presets (when to use each, Docker sandbox setup)
- Memory system (types, lifecycle, auto-distillation)
- Automation scheduling (cron patterns, timezone handling)
- Task/agent management (worktree isolation, approval gates)

---

## Medium — Differentiators

### M1. Multiplayer demo video
Multiplayer is the most unique feature. Zero competitors have it. But nobody will try it without seeing it work. Record a 2-minute demo: two terminals (or TUI + Neovim) in a shared session, hand-off, agenda, role switching. Post to HN/Reddit.

### M2. Cost dashboard with projections
The economy system is genuine differentiation. Add a `/cost` TUI overlay showing: cumulative session cost, cost per tool call, model downshift savings, and projected monthly cost at current rate. Make cost visibility the marketing centerpiece.

### M3. Deepen MCP integration
`mcp_client.py` is ~200 lines, single-server, stdio-only. MCP is becoming the standard for tool extensibility. Add:
- SSE transport support
- Multiple concurrent MCP servers
- Tool namespacing (prefix tools with server name)
- Server discovery from `.poor-cli/mcp.json` config
- Prompt and resource protocol support

### M4. Thin VS Code extension
The JSON-RPC server already exists. A thin VS Code extension connecting to it (same protocol as Neovim plugin) would unlock the VS Code audience without changing core architecture. The `_archived/vscode-poor-cli/` has prior art.

### M5. Improve architect mode
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

### L3. Wire remaining 6 Rust TUI slash commands
6 RPC wrappers are fully plumbed but lack a TUI slash command trigger:
- `rpc_get_agent_blocking` → `/agent show <id>`
- `rpc_get_trust_status_blocking` → `/trust status`
- `rpc_trust_repo_blocking` → `/trust add`
- `rpc_untrust_repo_blocking` → `/trust remove`
- `rpc_vector_search_blocking` → `/search vector <query>`
- `rpc_hybrid_search_blocking` → `/search hybrid <query>`

### L4. Browser tool JS safety
`browser_evaluate()` runs arbitrary JS in page context with no sandboxing. Add CSP-aware evaluation, output size limits, and a denylist for dangerous APIs (localStorage clearing, cookie manipulation, etc.).

### L5. Telegram bot zero-config setup
Currently requires manual BotFather setup + env var configuration. A `poor-cli telegram-setup` wizard that guides through token creation and writes `.env` would lower the barrier.

### L6. ARCHITECTURE.md + contribution guide
Bus factor = 1. An architecture doc explaining: core engine → JSON-RPC → frontends, provider abstraction, tool registry, sandbox model, and the checkpoint/session lifecycle would signal openness to contributors.

### L7. Naming consideration
"poor-cli" is memorable but may hurt professional/enterprise adoption. The name suggests "inferior" rather than "economical." Worth considering if targeting broader adoption beyond power users.

---

## Telegram Multiplayer

Multi-user collaborative coding sessions over Telegram, building on existing WebRTC multiplayer infrastructure.

### Vision

Allow multiple Telegram users to join a shared PoorCLICore session with role-based access, replicating the TUI/Neovim multiplayer experience over Telegram's messaging layer.

### Requirements

- **Room-based sessions** — a Telegram group or thread becomes a "room" backed by a single PoorCLICore instance
- **Role system** — mirror existing roles (viewer, prompter, driver) from `multiplayer_session.py`
- **Message relay** — prompts from any participant routed through the shared core, responses broadcast to all
- **Hand-raise queue** — users request driver access via inline keyboard; current driver approves/denies
- **Agenda tracking** — shared agenda items visible to all participants
- **Session lifecycle** — `/collab start`, `/collab join <invite>`, `/collab leave`, `/collab pass`

### Architecture

```
Telegram Group
  |
  v
PoorCLITelegramBot
  |
  v
MultiplayerBridge (poor_cli/telegram/multiplayer_bridge.py)
  |
  v
CollaborationSession (poor_cli/multiplayer_session.py)
  |
  v
PoorCLICore (shared instance)
```

### Key Challenges

1. **Concurrency** — multiple users sending prompts to one core; need request queuing per room
2. **State sync** — all participants must see tool calls, file edits, and outputs in real-time
3. **Permission escalation** — driver role must be exclusive; Telegram callback buttons for hand-off
4. **Session persistence** — rooms must survive bot restarts; store state in `.poor-cli/telegram_rooms/`
5. **Invite flow** — generate invite links that map to Telegram group join mechanics

### Existing Infrastructure

- `multiplayer_bridge.py` already exists in `poor_cli/telegram/` with basic bridge scaffolding
- `CollaborationSession` in `multiplayer_session.py` handles role management, agenda, hand-raise
- `/pair` command in `commands/workflows.py` has placeholder multiplayer logic
- TUI multiplayer (`poor-cli-tui/src/multiplayer.rs`) is a reference implementation

### Implementation Phases

1. **Phase 1**: Single-room, single-group. One user starts, others join via `/collab join`. Roles are viewer-only initially.
2. **Phase 2**: Add prompter role — queued prompts with driver approval.
3. **Phase 3**: Full driver hand-off, agenda system, hand-raise queue.
4. **Phase 4**: Multi-room support, cross-group collaboration, invite links.
