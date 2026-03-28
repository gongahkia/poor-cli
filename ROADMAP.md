# poor-cli — Audit, Feature Parity & Implementation Roadmap

> Generated 2026-03-28. Comparative analysis against Claude Code, Codex CLI, Cursor, Windsurf, Aider, GitHub Copilot CLI, Continue.dev.

---

## Table of Contents

1. [Architecture Assessment](#1-architecture-assessment)
2. [CLI vs Desktop Parity](#2-cli-vs-desktop-parity)
3. [Industry Feature Comparison](#3-industry-feature-comparison)
4. [Gap Analysis](#4-gap-analysis)
5. [Implementation Roadmap](#5-implementation-roadmap)

---

## 1. Architecture Assessment

### 1.1 What poor-cli seeks to do

poor-cli is a **multi-provider, multi-platform agentic AI coding assistant** with the following design goals:

- **Provider-agnostic**: Support Gemini, OpenAI, Anthropic/Claude, and Ollama from a single interface
- **Multi-surface**: CLI TUI (Rust/Ratatui), Desktop (Tauri), Neovim plugin, Emacs plugin — all sharing one Python backend via JSON-RPC
- **Agentic coding**: Autonomous multi-step tool-calling loop (read, edit, execute, git)
- **Collaborative**: P2P multiplayer via WebRTC with roles (viewer, prompter, driver)
- **Safe**: Capability-based sandbox, permission modes, encrypted API key storage, command validation
- **Cost-conscious**: Economy mode with model downshifting, terse prompts, cost guardrails
- **Extensible**: MCP support, custom skills, custom commands, workflow templates

### 1.2 Does it achieve this?

**Yes, to a significant degree.** The architecture is sound:

| Aspect | Verdict | Notes |
|--------|---------|-------|
| Provider abstraction | ✅ Strong | Factory pattern, lazy loading, tool translation layer, fallback chains |
| Shared backend | ✅ Strong | Single `PoorCLICore` engine consumed by all frontends via JSON-RPC |
| Agentic loop | ✅ Strong | Max-iteration cap, tool calling, permission callbacks, confidence scoring |
| Security model | ✅ Strong | 4 sandbox presets, capability-based enforcement, PBKDF2 key encryption, command validation |
| Multiplayer | ✅ Ambitious | WebRTC DataChannels, signed invites, role-based permissions — rare among competitors |
| Economy mode | ✅ Unique | Model downshifting, context compression, savings tracking — no competitor has this |
| MCP support | ✅ Present | Tool discovery, execution, health checking |
| Editor plugins | ⚠️ Present | Neovim and Emacs plugins exist, but not IDE-grade (no inline suggestions) |

**Key strengths over competitors:**
- Multi-provider support (most competitors lock to one provider)
- Multiplayer collaboration (unique — no competitor has P2P coding sessions)
- Economy mode with cost guardrails (unique)
- Ollama/local model support as first-class citizen

**Key weaknesses:**
- No persistent memory system across sessions
- No background/cloud agent execution
- No inline code suggestions (autocomplete)
- No conversation forking
- No automated PR review agent
- No live preview / visual editing
- No voice input

### 1.3 Codebase health

| Metric | Value | Assessment |
|--------|-------|------------|
| Python backend | ~250K LOC | Large but well-structured |
| Rust TUI | ~200K LOC | Comprehensive terminal UI |
| Desktop (Tauri) | ~3K LOC JS + Rust | Lightweight, no framework dependencies |
| Test coverage | Unit tests for core modules | Could be expanded |
| CI/CD | GitHub Actions (multi-platform) | Solid |

---

## 2. CLI vs Desktop Parity

Both surfaces share the same Python backend via JSON-RPC, so core AI capabilities are identical. Differences are in UX and presentation.

### 2.1 Feature matrix

| Feature | CLI (TUI) | Desktop (Tauri) | Parity? |
|---------|-----------|-----------------|---------|
| Chat interface | ✅ Terminal UI | ✅ Rich HTML/CSS | ✅ |
| Multi-session | ✅ Session switching | ✅ Tab bar | ✅ |
| Slash commands | ✅ 250+ commands | ✅ 100+ via autocomplete | ⚠️ CLI has more |
| Tool execution | ✅ Full | ✅ Full | ✅ |
| Permission prompts | ✅ Terminal prompt | ✅ Modal dialog | ✅ |
| Streaming responses | ✅ | ✅ | ✅ |
| Markdown rendering | ⚠️ TUI markdown | ✅ Rich HTML rendering | Desktop better |
| Command palette | ❌ | ✅ Cmd/Ctrl+P | Desktop only |
| Themes | ⚠️ Config-based | ✅ 8 built-in + fonts | Desktop better |
| Task management | ✅ CLI commands | ✅ Full CRUD UI | Desktop better |
| Checkpoint preview | ✅ CLI output | ✅ Visual diff | Desktop better |
| Git integration | ✅ CLI commands | ✅ 4-tab visual (status/log/diff/branches) | Desktop better |
| File changes panel | ❌ | ✅ Visual diff with stats | Desktop only |
| Collaboration panel | ✅ CLI commands | ✅ Dedicated right panel | Desktop better |
| Automation management | ✅ CLI commands | ✅ Full CRUD UI | Desktop better |
| Workflow templates | ✅ | ✅ Visual cards | Desktop better |
| Diagnostics | ✅ CLI output | ✅ Categorized UI | Desktop better |
| Settings UI | ✅ Config files | ✅ Categorized settings page | Desktop better |
| API key management | ✅ Env vars | ✅ GUI with show/hide | Desktop better |
| Context @file syntax | ✅ | ✅ with autocomplete | Desktop better |
| Keyboard shortcuts | ✅ Vim-style | ⚠️ Limited (Enter, Cmd+P, Esc) | CLI better |
| Mouse support | ⚠️ Basic | ✅ Full | Desktop better |
| Export | ✅ | ✅ (md/json/txt) | ✅ |

### 2.2 Verdict

The **desktop app is more user-friendly** for discovery and visual tasks (git, checkpoints, settings, file changes). The **CLI is more powerful** for keyboard-driven workflows and has access to more slash commands. Both are usable for the core use case of agentic coding.

**Gaps to close:**
- [ ] CLI: Add command palette equivalent (fuzzy command search)
- [ ] Desktop: Expose all 250+ slash commands (currently ~100)
- [ ] Desktop: Add richer keyboard shortcuts (vim-style navigation, split panes)
- [ ] CLI: Add visual file changes summary after mutations

---

## 3. Industry Feature Comparison

### 3.1 Comparison matrix

Legend: ✅ = present, ⚠️ = partial/basic, ❌ = missing, 🔵 = unique/superior

| Feature | poor-cli | Claude Code | Codex CLI | Cursor | Windsurf | Aider | Copilot CLI |
|---------|----------|-------------|-----------|--------|----------|-------|-------------|
| **Core** | | | | | | | |
| Agentic coding loop | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| File read/edit/write | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Shell execution | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Streaming responses | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multi-step tool calling | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Providers** | | | | | | | |
| Multi-provider | 🔵 4 providers | ❌ Claude only | ❌ OpenAI only | ✅ Multiple | ✅ Multiple | ✅ Multiple | ❌ OpenAI/GitHub |
| Local models (Ollama) | 🔵 First-class | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Model switching | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Economy/cost mode | 🔵 Unique | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Provider fallback | 🔵 Chain | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Context** | | | | | | | |
| Project instructions | ✅ .poor-cli/ | ✅ CLAUDE.md | ✅ AGENTS.md | ✅ Rules | ✅ Rules | ❌ | ✅ Custom instructions |
| Hierarchical instructions | ✅ | ✅ 3-tier | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ |
| Context compaction | ✅ | ✅ /compact | ✅ /compact | ✅ | ✅ | ❌ | ❌ |
| Token-aware context | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| @file references | ✅ | ✅ | ✅ @mention | ✅ | ✅ | ✅ | ✅ |
| Codebase indexing | ⚠️ Import analysis | ⚠️ | ⚠️ | ✅ Semantic | ✅ Deep | ✅ Repo-map | ⚠️ |
| **Memory** | | | | | | | |
| Persistent memory | ❌ | ✅ File-based | ❌ | ✅ Memories | ✅ Auto-memory | ❌ | ✅ |
| Cross-session recall | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |
| **Security** | | | | | | | |
| Sandbox presets | ✅ 4 presets | ✅ | ✅ 3 modes | ⚠️ | ⚠️ | ❌ | ⚠️ |
| Permission callbacks | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Encrypted key storage | 🔵 PBKDF2+Fernet | ❌ Env vars | ❌ | N/A | N/A | ❌ | OAuth |
| Command validation | ✅ Risk classify | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ |
| Trust model (untrusted repos) | ❌ | ⚠️ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Git** | | | | | | | |
| Git status/diff/log | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auto-commit workflow | ✅ | ✅ | ⚠️ | ✅ | ✅ | 🔵 Every edit | ✅ |
| PR creation | ✅ (gh CLI) | ✅ (gh CLI) | ⚠️ | ✅ | ⚠️ | ❌ | ✅ |
| PR review agent | ❌ | ⚠️ | ⚠️ /review | ✅ BugBot | ❌ | ❌ | ✅ Coding agent |
| Branch-per-session | ❌ | ❌ | ❌ | ⚠️ | ❌ | ✅ | ❌ |
| **Agents & Parallelism** | | | | | | | |
| Sub-agents | ⚠️ Basic | ✅ Specialized | ✅ | ✅ | ✅ | ❌ | ✅ Auto-delegate |
| Parallel agents | ❌ | ✅ | ✅ | ✅ 8 parallel | ❌ | ❌ | ❌ |
| Background/cloud agents | ❌ | ✅ GitHub-triggered | ✅ Codex Cloud | ✅ Cloud agents | ❌ | ❌ | ✅ Coding agent |
| Worktree isolation | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Sessions** | | | | | | | |
| Multi-session | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Conversation forking | ❌ | ❌ | ✅ /fork | ❌ | ❌ | ❌ | ❌ |
| Session resume | ✅ | ✅ | ✅ /resume | ✅ | ✅ | ❌ | ✅ |
| Session export | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Collaboration** | | | | | | | |
| Multiplayer/P2P | 🔵 WebRTC | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Role-based collab | 🔵 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| External integrations | ❌ | ❌ | ❌ | ✅ Slack, Linear | ✅ MCP-based | ❌ | ✅ GitHub native |
| **IDE / Editor** | | | | | | | |
| Inline autocomplete | ❌ | ❌ | ❌ | ✅ Tab | ✅ Supercomplete | ❌ | ✅ |
| Visual editor | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Live preview | ❌ | ❌ | ❌ | ✅ Browser | ✅ | ❌ | ❌ |
| Neovim plugin | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Emacs plugin | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| VS Code extension | ❌ | ✅ | ❌ | ✅ (is VS Code) | ✅ (is VS Code) | ❌ | ✅ |
| JetBrains extension | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Advanced** | | | | | | | |
| MCP support | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Hooks/policies | ✅ | ✅ | ⚠️ | ✅ | ❌ | ❌ | ❌ |
| Plan mode | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ Structured | ✅ |
| Extended thinking | ✅ (Claude) | ✅ | ✅ (xhigh) | ✅ | ⚠️ | ❌ | ⚠️ |
| Vision/images | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| PDF reading | ❌ | ✅ Paginated | ❌ | ❌ | ❌ | ❌ | ❌ |
| Jupyter support | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Web search | ✅ (Brave) | ⚠️ MCP | ✅ Cached+live | ⚠️ | ⚠️ | ✅ | ⚠️ |
| Voice input | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Auto lint+test loop | ⚠️ Manual tools | ⚠️ | ⚠️ | ✅ | ✅ | ✅ Auto | ⚠️ |
| Checkpoints/undo | 🔵 Full system | ❌ | ❌ | ⚠️ Git | ❌ | ✅ Git | ❌ |
| Cost tracking | ✅ | ✅ /cost | ⚠️ /status | ❌ | ❌ | ❌ | ❌ |
| Profiles/presets | ⚠️ Economy presets | ❌ | ✅ --profile | ❌ | ❌ | ❌ | ❌ |
| Desktop app | ✅ Tauri | ✅ Web app | ❌ | ✅ (is desktop) | ✅ (is desktop) | ❌ | ❌ |
| Docker support | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

### 3.2 Summary

**poor-cli's unique advantages:**
1. 🔵 Multi-provider (4 providers + Ollama local) — no competitor matches this
2. 🔵 Multiplayer collaboration — completely unique
3. 🔵 Economy mode + cost guardrails — unique
4. 🔵 Checkpoint/undo system — most comprehensive
5. 🔵 Encrypted key storage — strongest security
6. 🔵 Provider fallback chains — unique resilience
7. 🔵 Desktop + CLI + Editor plugins from one backend

**poor-cli's critical gaps vs industry:**
1. ❌ No persistent memory system (Cursor, Windsurf, Copilot, Claude Code all have this)
2. ❌ No background/cloud agents (Cursor, Codex, Copilot all have this)
3. ❌ No parallel agent execution with worktree isolation (Cursor, Claude Code)
4. ❌ No inline autocomplete suggestions (Cursor, Windsurf, Copilot)
5. ❌ No conversation forking (Codex)
6. ❌ No automated PR review agent (Cursor BugBot, Copilot)
7. ❌ No trust model for untrusted repositories (Codex)
8. ❌ No VS Code / JetBrains extensions (Claude Code, Copilot)
9. ❌ No live preview / visual editing (Cursor, Windsurf)
10. ❌ No PDF / Jupyter notebook reading (Claude Code, Cursor)

---

## 4. Gap Analysis

### Priority tiers

| Priority | Criteria |
|----------|----------|
| **P0 — Critical** | Core capability gap that makes poor-cli feel incomplete vs every competitor |
| **P1 — High** | Feature present in 2+ top competitors that significantly improves UX |
| **P2 — Medium** | Feature present in 1-2 competitors, nice-to-have for power users |
| **P3 — Low** | Differentiation feature, not widely expected |

### 4.1 P0 — Critical gaps

#### G-01: Persistent memory system
- **Who has it:** Cursor (Memories), Windsurf (auto-memory), Copilot (memory), Claude Code (file-based)
- **What's missing:** poor-cli has no way to remember user preferences, project patterns, or decisions across sessions
- **Impact:** Users must re-explain context every session; feels stateless

#### G-02: Background / headless agent execution
- **Who has it:** Cursor (cloud agents), Codex (Codex Cloud), Copilot (coding agent), Claude Code (GitHub-triggered)
- **What's missing:** poor-cli has `exec` mode but no persistent background agent that can be triggered externally (GitHub issue, webhook, cron)
- **Impact:** Cannot integrate into CI/CD or async workflows

#### G-03: Parallel agent execution with isolation
- **Who has it:** Cursor (8 parallel via worktrees), Claude Code (worktree isolation)
- **What's missing:** poor-cli has sub_agent support but no git worktree isolation for safe parallel execution
- **Impact:** Cannot safely run multiple agents modifying the same repo

#### G-04: Semantic codebase indexing
- **Who has it:** Cursor (semantic search), Windsurf (deep context), Aider (repo-map)
- **What's missing:** poor-cli uses import analysis and glob/grep but no persistent vector/semantic index
- **Impact:** Context selection is heuristic-based, misses relevant files in large repos

### 4.2 P1 — High-priority gaps

#### G-05: Automated PR review agent
- **Who has it:** Cursor (BugBot), Copilot (code review agent)
- **What's missing:** No dedicated review tool that can be triggered on PR creation to provide structured feedback
- **Impact:** Missing a key CI/CD integration point

#### G-06: Trust model for untrusted repos
- **Who has it:** Codex CLI (ignores `.codex/config.toml` in untrusted projects)
- **What's missing:** poor-cli loads `.poor-cli/config.yaml` from any repo without trust verification
- **Impact:** Malicious repos could inject custom config/instructions

#### G-07: Conversation forking
- **Who has it:** Codex CLI (`/fork`)
- **What's missing:** No way to branch a conversation into a separate exploration path
- **Impact:** Users must start new sessions to explore alternatives, losing context

#### G-08: Auto lint+test feedback loop
- **Who has it:** Aider (auto-runs linter/tests, auto-fixes), Cursor, Windsurf
- **What's missing:** poor-cli has `run_tests` and `format_and_lint` tools but no automatic loop that runs them after every edit and feeds errors back
- **Impact:** Manual intervention needed for iterative fix cycles

#### G-09: PDF and Jupyter notebook reading
- **Who has it:** Claude Code (PDF paginated, .ipynb), Cursor (Jupyter)
- **What's missing:** No PDF parsing, no notebook cell reading
- **Impact:** Cannot work with documentation PDFs or data science notebooks

#### G-10: Profile / named preset system
- **Who has it:** Codex CLI (`--profile`), poor-cli has economy presets but not full config profiles
- **What's missing:** Named configuration sets (e.g., "review-mode", "fast-prototype", "deep-debug") that bundle provider, model, sandbox, and behavior settings
- **Impact:** Users manually reconfigure for different task types

### 4.3 P2 — Medium-priority gaps

#### G-11: VS Code extension
- **Who has it:** Claude Code, Copilot, Continue.dev (all with rich VS Code integration)
- **What's missing:** poor-cli has Neovim/Emacs but no VS Code extension
- **Impact:** Misses the largest IDE user base

#### G-12: Inline autocomplete / code suggestions
- **Who has it:** Cursor (Tab), Windsurf (Supercomplete), Copilot (inline suggestions)
- **What's missing:** No inline code completion in any editor integration
- **Impact:** Cannot compete as a daily-driver coding assistant in editors

#### G-13: External service integrations (Slack, Linear, etc.)
- **Who has it:** Cursor (Slack bot, Linear), Windsurf (MCP-based), Copilot (GitHub native)
- **What's missing:** No direct integrations beyond GitHub (via gh CLI)
- **Impact:** Cannot receive tasks from project management tools

#### G-14: Live preview / browser integration
- **Who has it:** Cursor (browser), Windsurf (previews)
- **What's missing:** No way to preview web app changes in real-time
- **Impact:** Frontend development workflow is less fluid

#### G-15: Voice input
- **Who has it:** Aider, ChatGPT desktop
- **What's missing:** No speech-to-text input
- **Impact:** Accessibility and hands-free workflows limited

#### G-16: Git branch-per-session
- **Who has it:** Aider (every session on its own branch)
- **What's missing:** Sessions don't create isolated git branches
- **Impact:** Cannot easily review/revert an entire session's changes as a unit

### 4.4 P3 — Low-priority / aspirational

#### G-17: Cloud deployment from editor
- **Who has it:** Windsurf (app deploys beta)
- **What's missing:** No deploy integration

#### G-18: Autonomous memory generation
- **Who has it:** Windsurf (auto-generates memories from coding patterns)
- **What's missing:** Memory (once implemented) would be manual-only

#### G-19: IDE watch mode (comment-based instructions)
- **Who has it:** Aider (`# aider: ...` comments)
- **What's missing:** No way to leave inline comments that poor-cli picks up

#### G-20: Mission control / multi-window management
- **Who has it:** Cursor (grid view of windows)
- **What's missing:** No overview of multiple agent windows/sessions

---

## 5. Implementation Roadmap

### Phase 1 — Foundation (P0 gaps)

#### 5.1.1 G-01: Persistent Memory System

**Goal:** Cross-session memory that remembers user preferences, project decisions, and coding patterns.

**Design:**
```
~/.poor-cli/memory/
├── MEMORY.md              # index file, loaded into every session
├── user_role.md           # user profile memories
├── feedback_testing.md    # behavioral feedback
├── project_auth.md        # project-specific context
└── reference_linear.md    # external resource pointers
```

**Implementation plan:**

1. **Memory data model** (`poor_cli/memory.py`)
   - `MemoryEntry` dataclass: `name`, `description`, `type` (user/feedback/project/reference), `content`, `created_at`, `updated_at`
   - `MemoryManager` class:
     - `load_index()` → parse MEMORY.md
     - `save_memory(entry)` → write individual .md file + update index
     - `search_memories(query)` → keyword/semantic search over descriptions
     - `delete_memory(name)` → remove file + index entry
     - `get_relevant(context: str)` → return memories relevant to current task
   - Memory types: `user`, `feedback`, `project`, `reference`
   - Max 200 index entries (truncate oldest)

2. **Memory tools** (add to `tools_async.py`)
   - `memory_save(name, type, description, content)` → persist a memory
   - `memory_search(query)` → find relevant memories
   - `memory_delete(name)` → remove a memory
   - `memory_list()` → return index

3. **System prompt integration** (`prompts.py`)
   - Inject relevant memories into system instruction
   - Add memory-saving guidelines to tool-calling prompt
   - Instruct model when to save vs not save

4. **Session startup hook** (`core.py`)
   - On `initialize()`, load MEMORY.md
   - Pass relevant memories as context to first message
   - On session end, prompt model to save any new learnings

5. **CLI/Desktop integration**
   - `/memory` command to list, search, delete memories
   - Desktop: memory management view in sidebar
   - TUI: memory overlay

**Estimated scope:** ~800 LOC Python, ~200 LOC Rust, ~100 LOC JS

---

#### 5.1.2 G-02: Background / Headless Agent Execution

**Goal:** Agents that run autonomously, triggered by external events (GitHub, webhooks, cron).

**Design:**
```
poor-cli agent start --task "Fix issue #42" --sandbox workspace-write
poor-cli agent list
poor-cli agent logs <id>
poor-cli agent cancel <id>
```

**Implementation plan:**

1. **Agent runner** (`poor_cli/agent_runner.py`)
   - `AgentRunner` class wrapping `PoorCLICore`
   - Runs in background process (daemonized)
   - Writes structured logs to `~/.poor-cli/agents/<id>/`
   - Supports max runtime, cost limits
   - Auto-commits results to a branch
   - Reports status via JSON file or webhook

2. **GitHub integration** (`poor_cli/github_agent.py`)
   - GitHub App / webhook receiver
   - Triggers agent on: issue assignment, PR comment (`@poor-cli`), label events
   - Posts results as PR/issue comments
   - Requires `gh` CLI auth

3. **Cron/scheduler integration** (extend `automation_manager.py`)
   - Add `agent` automation type
   - Cron-based recurring agent tasks
   - Result history with diffs

4. **CLI subcommands** (extend `__main__.py`)
   - `poor-cli agent start` — launch background agent
   - `poor-cli agent list` — show running/completed agents
   - `poor-cli agent logs` — tail agent output
   - `poor-cli agent cancel` — stop agent
   - `poor-cli agent result` — show final output

5. **Desktop/TUI integration**
   - Agent status panel
   - Launch agents from task view
   - Live log streaming

**Estimated scope:** ~1500 LOC Python, ~300 LOC Rust, ~200 LOC JS

---

#### 5.1.3 G-03: Parallel Agents with Worktree Isolation

**Goal:** Run multiple agents in parallel on isolated git worktrees.

**Implementation plan:**

1. **Worktree manager** (`poor_cli/worktree.py`)
   - `WorktreeManager` class:
     - `create_worktree(branch_name)` → `git worktree add`
     - `cleanup_worktree(path)` → `git worktree remove`
     - `list_worktrees()` → active worktrees
   - Temp directory management
   - Auto-cleanup on agent completion (if no changes)
   - Branch naming: `poor-cli/agent/<task-id>`

2. **Parallel agent orchestrator** (`poor_cli/parallel_agents.py`)
   - `ParallelAgentPool` class:
     - Max concurrent agents (default 4)
     - Each agent gets its own worktree + PoorCLICore instance
     - Collect results and merge/report
   - Task decomposition interface:
     - `split_task(prompt)` → list of sub-tasks
     - `merge_results(results)` → combined output

3. **Core integration** (`core.py`)
   - Add `spawn_sub_agent(prompt, isolation="worktree")` method
   - Sub-agent inherits parent config but gets own worktree
   - Results returned as structured data

4. **CLI/Desktop**
   - Show parallel agents in task list
   - Merge UI for combining worktree results

**Estimated scope:** ~600 LOC Python, ~200 LOC Rust

---

#### 5.1.4 G-04: Semantic Codebase Indexing

**Goal:** Persistent vector index for semantic code search.

**Implementation plan:**

1. **Indexer** (`poor_cli/indexer.py`)
   - `CodebaseIndexer` class:
     - Walk project files (respect .gitignore)
     - Chunk files by function/class boundaries
     - Generate embeddings (provider-specific or local)
     - Store in SQLite FTS5 + optional vector DB
   - Incremental indexing (hash-based change detection)
   - Background re-index on file changes

2. **Embedding providers:**
   - Gemini: `text-embedding-004`
   - OpenAI: `text-embedding-3-small`
   - Ollama: `nomic-embed-text` (local)
   - Fallback: TF-IDF with SQLite FTS5 (zero-cost)

3. **Search interface** (add to `tools_async.py`)
   - `semantic_search(query, max_results=10)` → ranked file chunks
   - Integrates into context selection pipeline

4. **Context manager integration** (`context.py`)
   - Add semantic search as a context source alongside import analysis
   - Weight semantic results in priority scoring

5. **CLI/Desktop**
   - `/index` command to trigger re-index
   - `/search` enhanced with semantic results
   - Index status in diagnostics

**Estimated scope:** ~1000 LOC Python, optional dependency on embedding SDK

---

### Phase 2 — High Priority (P1 gaps)

#### 5.2.1 G-05: Automated PR Review Agent

**Implementation plan:**

1. **Review engine** (`poor_cli/review_agent.py`)
   - Fetch PR diff via `gh pr diff <number>`
   - Chunk diff by file, send to AI with review prompt
   - Structured output: issues found (severity, line, suggestion)
   - Post as PR review comments via `gh api`

2. **Trigger modes:**
   - Manual: `poor-cli review-pr <number>`
   - Automated: GitHub webhook on PR open/update
   - CI: `poor-cli review-pr --ci` (exit code reflects severity)

3. **Review prompt** (add to `prompts.py`)
   - Focus on: bugs, security issues, performance, style, test coverage gaps
   - Configurable review focus via `.poor-cli/review.yaml`

**Estimated scope:** ~500 LOC Python

---

#### 5.2.2 G-06: Trust Model for Untrusted Repos

**Implementation plan:**

1. **Trust registry** (`poor_cli/trust.py`)
   - `TrustManager` class:
     - Trusted roots stored in `~/.poor-cli/trusted_repos.json`
     - `is_trusted(repo_path)` → bool
     - `trust_repo(path)` → add to trusted
     - `untrust_repo(path)` → remove

2. **Behavior in untrusted repos:**
   - Ignore `.poor-cli/config.yaml` (use only user-level config)
   - Ignore `.poor-cli/instructions.md` (warn user)
   - Ignore `.poor-cli/skills/` (don't auto-execute)
   - Prompt user: "This repo has custom config. Trust it? [y/N]"

3. **Integration points:**
   - `config.py`: Check trust before loading repo config
   - `instructions.py`: Check trust before loading repo instructions
   - `skills.py`: Check trust before discovering repo skills

**Estimated scope:** ~300 LOC Python

---

#### 5.2.3 G-07: Conversation Forking

**Implementation plan:**

1. **Fork mechanism** (`poor_cli/session_manager.py`)
   - `/fork` command creates new session from current point
   - Deep-copies conversation history up to current message
   - New session gets unique ID, labeled as "Fork of <parent>"
   - Both parent and child continue independently

2. **History adapter** (`history.py`)
   - `fork_session(source_id, fork_point)` → new session with copied messages
   - Track parent-child relationships

3. **CLI/Desktop**
   - `/fork` slash command
   - Desktop: fork button in session tab context menu
   - Visual indicator of forked sessions

**Estimated scope:** ~300 LOC Python, ~100 LOC Rust, ~50 LOC JS

---

#### 5.2.4 G-08: Auto Lint+Test Feedback Loop

**Implementation plan:**

1. **Feedback loop engine** (`poor_cli/feedback_loop.py`)
   - `AutoFeedbackLoop` class:
     - After every file mutation, detect project type
     - Run appropriate linter (eslint, ruff, clippy, etc.)
     - Run relevant tests (nearest test file, affected tests)
     - If errors found, automatically feed back to AI
     - Continue until clean or max iterations (3)

2. **Project detection** (extend `context.py`)
   - Detect: package.json → npm test, pyproject.toml → pytest, Cargo.toml → cargo test
   - Cache detection results per session

3. **Configuration:**
   - `auto_feedback: true` in config
   - Configurable commands per project type
   - Max iterations before stopping

4. **Integration** (`core.py`)
   - Hook into post-tool-result for write_file/edit_file
   - Inject lint/test results as system message if errors found

**Estimated scope:** ~400 LOC Python

---

#### 5.2.5 G-09: PDF and Jupyter Notebook Reading

**Implementation plan:**

1. **PDF reader** (`poor_cli/readers/pdf_reader.py`)
   - Use `pymupdf` (fitz) or `pdfplumber` for text extraction
   - Page-range support: `read_file("doc.pdf", pages="1-5")`
   - Max 20 pages per request
   - Extract text, tables, and metadata

2. **Jupyter reader** (`poor_cli/readers/notebook_reader.py`)
   - Parse `.ipynb` JSON structure
   - Render cells: code cells with outputs, markdown cells
   - Handle image outputs (base64)

3. **Tool integration** (extend `read_file` in `tools_async.py`)
   - Detect file extension → route to appropriate reader
   - `.pdf` → PDFReader
   - `.ipynb` → NotebookReader
   - Add optional `pages` parameter to read_file

**Estimated scope:** ~400 LOC Python, new optional deps (pymupdf)

---

#### 5.2.6 G-10: Named Config Profiles

**Implementation plan:**

1. **Profile system** (`poor_cli/profiles.py`)
   - Profiles stored in `~/.poor-cli/profiles/`
   - Each profile: `<name>.yaml` with full config override
   - Built-in profiles: `fast`, `deep-review`, `safe`, `full-auto`
   - `--profile <name>` CLI flag
   - `/profile` command to list/switch

2. **Profile schema:**
   ```yaml
   # ~/.poor-cli/profiles/deep-review.yaml
   provider: anthropic
   model: claude-sonnet-4-20250514
   sandbox: review-only
   economy: quality
   agentic:
     max_iterations: 50
   ```

3. **Config integration** (`config.py`)
   - Profile settings overlay on base config
   - CLI flag > profile > repo config > user config > defaults

**Estimated scope:** ~200 LOC Python

---

### Phase 3 — Medium Priority (P2 gaps)

#### 5.3.1 G-11: VS Code Extension

**Implementation plan:**

1. **Extension architecture:**
   - VS Code extension (TypeScript)
   - Spawns `poor-cli-server` as child process
   - Communicates via JSON-RPC (same protocol as TUI/desktop)
   - Reuses entire Python backend

2. **Features (MVP):**
   - Chat panel (webview)
   - File context from active editor
   - Tool execution with approval prompts
   - Output panel for agent logs
   - Status bar with cost/provider info

3. **Directory:** `vscode-poor-cli/`

**Estimated scope:** ~2000 LOC TypeScript, ~500 LOC HTML/CSS

---

#### 5.3.2 G-12: Inline Autocomplete

**Implementation plan:**

1. **Completion engine** (`poor_cli/completion.py`)
   - Fill-in-middle (FIM) completion via provider
   - Debounced trigger on keystroke (300ms)
   - Context: current file, cursor position, imports
   - Provider-specific FIM templates (already exist in `prompts.py`)

2. **Editor integration:**
   - Neovim: `nvim-cmp` source using JSON-RPC
   - VS Code: `InlineCompletionItemProvider`
   - Emacs: `company-mode` backend

3. **Server endpoint** (add to `server/runtime.py`)
   - `getCompletion(file, line, column, prefix, suffix)` RPC method
   - Low-latency path (skip agentic loop, direct provider call)
   - Use cheap/fast model tier

**Estimated scope:** ~600 LOC Python, ~400 LOC per editor plugin

---

#### 5.3.3 G-13: External Service Integrations

**Implementation plan:**

1. **Integration framework** (`poor_cli/integrations/`)
   - `base.py`: Abstract `Integration` class
   - `slack.py`: Slack bot (receive tasks, post results)
   - `linear.py`: Linear webhook (sync issues as tasks)
   - `telegram.py`: Already has telegram dep — expand to full bot

2. **MCP-based approach (preferred):**
   - Leverage existing MCP support
   - Publish MCP server configs for popular services
   - User configures in `.poor-cli/mcp.yaml`

**Estimated scope:** ~500 LOC per integration, or ~100 LOC per MCP config

---

#### 5.3.4 G-14: Live Preview

**Implementation plan:**

1. **Preview server** (`poor_cli/preview.py`)
   - Lightweight HTTP server (aiohttp) serving project files
   - File watcher (watchdog) for live reload
   - Inject reload script into HTML pages
   - Auto-detect preview-able projects (has index.html, package.json with dev server)

2. **Integration:**
   - `/preview` command to start preview server
   - Desktop: embedded webview panel
   - CLI: opens in default browser
   - Auto-detect and proxy existing dev servers (vite, next, etc.)

**Estimated scope:** ~400 LOC Python, ~200 LOC JS (desktop)

---

#### 5.3.5 G-15: Voice Input

**Implementation plan:**

1. **Speech-to-text** (`poor_cli/voice.py`)
   - Use system STT (macOS Dictation API, or Whisper via Ollama)
   - Push-to-talk keybinding in TUI
   - Desktop: microphone button in chat input
   - Transcribed text inserted into prompt

2. **Dependencies:**
   - macOS: `NSSpeechRecognizer` via PyObjC (optional dep)
   - Cross-platform: Whisper model via Ollama
   - Or: browser Web Speech API (desktop only)

**Estimated scope:** ~300 LOC Python, ~100 LOC JS

---

#### 5.3.6 G-16: Git Branch-per-Session

**Implementation plan:**

1. **Session branching** (extend `session_manager.py`)
   - On new session, optionally create `poor-cli/session/<id>` branch
   - All commits during session go to that branch
   - On session end, offer: merge to main, keep branch, delete
   - Configurable: `git.branch_per_session: true`

2. **Integration:**
   - `/session-branch` command to enable/disable
   - Show branch name in workspace bar
   - Merge UI in desktop

**Estimated scope:** ~200 LOC Python

---

### Phase 4 — Low Priority (P3 gaps)

#### 5.4.1 G-17: Cloud Deployment
- Integrate with Vercel/Netlify/Fly.io CLIs
- `/deploy` command
- ~300 LOC

#### 5.4.2 G-18: Autonomous Memory Generation
- After G-01 (memory system), add auto-save heuristics
- Model analyzes session for memorable patterns
- ~200 LOC on top of memory system

#### 5.4.3 G-19: IDE Watch Mode
- File watcher for `# poor-cli: ...` comments
- Trigger agent on save when comment detected
- ~300 LOC

#### 5.4.4 G-20: Mission Control
- Desktop-only multi-session overview
- Grid view of active sessions with live previews
- ~500 LOC JS/CSS

---

## Implementation Priority Order

| Order | Gap | Phase | Est. Effort | Dependencies | Status |
|-------|-----|-------|-------------|--------------|--------|
| 1 | G-01 Memory System | P0 | M | None | ✅ Done |
| 2 | G-06 Trust Model | P1 | S | None | ✅ Done |
| 3 | G-08 Auto Lint+Test Loop | P1 | S | None | ✅ Done |
| 4 | G-09 PDF/Jupyter Reading | P1 | S | None | ✅ Done |
| 5 | G-10 Config Profiles | P1 | S | None | ✅ Done |
| 6 | G-07 Conversation Forking | P1 | S | None | ✅ Done |
| 7 | G-16 Branch-per-Session | P2 | S | None | ✅ Done |
| 8 | G-04 Semantic Indexing | P0 | L | Embedding provider | ✅ Done |
| 9 | G-03 Worktree Isolation | P0 | M | Git | ✅ Done |
| 10 | G-02 Background Agents | P0 | L | G-03 | ✅ Done |
| 11 | G-05 PR Review Agent | P1 | M | gh CLI | ✅ Done |
| 12 | G-12 Inline Autocomplete | P2 | L | Editor plugins | ✅ Done |
| 13 | G-11 VS Code Extension | P2 | L | JSON-RPC server | ✅ Done |
| 14 | G-14 Live Preview | P2 | M | None | ✅ Done |
| 15 | G-15 Voice Input | P2 | M | Optional deps | ✅ Done |
| 16 | G-13 External Integrations | P2 | M | MCP | ✅ Done |
| 17 | G-18 Auto Memory | P3 | S | G-01 | ✅ Done |
| 18 | G-19 IDE Watch Mode | P3 | S | Editor plugins | ✅ Done |
| 19 | G-17 Cloud Deploy | P3 | S | None | ✅ Done |
| 20 | G-20 Mission Control | P3 | M | Desktop only | ✅ Done |

**All 20 gaps implemented.** Total: ~5,500 LOC across 21 commits.

**Size key:** S = <500 LOC, M = 500-1500 LOC, L = >1500 LOC

---

## CLI vs Desktop Action Items

To close the parity gap between CLI and desktop:

| Item | Surface | Action |
|------|---------|--------|
| Command palette | CLI | Add fuzzy command search overlay (Ctrl+P equivalent) |
| Full slash command set | Desktop | Expose all 250+ commands via autocomplete |
| Vim-style navigation | Desktop | Add keyboard-driven navigation, split panes |
| File changes summary | CLI | Show mutation summary after tool execution |
| Richer keyboard shortcuts | Desktop | Tab switching, panel toggle, quick actions |
| Theme system | CLI | Port theme selection to TUI (already has config support) |

---

*This document should be updated as gaps are closed. Check off completed items and remove from the priority table.*
