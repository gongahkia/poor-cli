# nvim-poor-cli

[![Neovim](https://img.shields.io/badge/Neovim-0.9%2B-green.svg)](https://neovim.io/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**AI-powered inline code completion and chat for Neovim** with BYOK, explicit failure reporting, and request-scoped cancellation.

## ✨ Features

- 🪄 **Inline Ghost Text Completion** - Windsurf-style inline suggestions
- 🧠 **Completion Controls** - manual-only mode, filetype/buftype gating, context budgets, and partial streaming
- 💬 **Chat Panel** - Conversational AI with markdown rendering
- 🔄 **Multi-Provider Support** - Gemini, OpenAI, Claude, Ollama
- 🔌 **nvim-cmp Integration** - registers a `poor-cli` completion source when `nvim-cmp` is installed
- ⚡ **blink.cmp Integration** - provides a native `poor-cli` source for blink.cmp users
- 🛠️ **AI Commands** - Explain, Refactor, Generate Tests, Generate Docs
- ⚡ **Streaming Responses** - Real-time AI output
- 🎯 **Context-Aware** - Uses open buffers as context
- 🩺 **Inline Diagnostics** - Optional file:line suggestions as Neovim diagnostics
- ✅ **Guarded Plan Review** - Approve or reject backend execution plans from Neovim
- 🧾 **Fail-Open Debugging** - managed server log, doctor report, copyable debug bundle, and minimal repro init generation
- 🔐 **BYOK** - Bring Your Own Key, no subscription needed

## 📦 Installation

### Requirements

- Neovim 0.9+
- Python 3.11+
- `poor-cli` Python package installed: `python3 -m pip install --upgrade 'poor-cli[all]'` (provides `poor-cli-server`)
- At least one API key: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`
- **Required plugins** (`require('poor-cli').setup()` refuses to load without any of these):
  - [`folke/snacks.nvim`](https://github.com/folke/snacks.nvim) — notifications + pickers
  - [`folke/trouble.nvim`](https://github.com/folke/trouble.nvim) — `:Trouble poor-cli` diagnostics list
  - [`mfussenegger/nvim-dap`](https://github.com/mfussenegger/nvim-dap) — `<leader>pb` / `<leader>pB` breakpoint keymaps
  - [`NeogitOrg/neogit`](https://github.com/NeogitOrg/neogit) — auto-open-on-commit flow

### Optional integrations

Each integration below enables one extra feature but is not required for poor-cli to start. Missing plugins never produce errors — the affected feature simply doesn't register. Every feature in this table has a parallel path that still works (or a built-in native fallback), so you can skip any of them without losing core functionality.

| Plugin | Feature it enables | If missing |
|---|---|---|
| [`stevearc/oil.nvim`](https://github.com/stevearc/oil.nvim) | `@oil:` mention in chat to pick a file via oil's buffer | **Degraded** — `@file:` and `@buffer:` mentions still work |
| [`hrsh7th/nvim-cmp`](https://github.com/hrsh7th/nvim-cmp) | Registers a `poor-cli` source in nvim-cmp's completion menu | **Degraded** — inline ghost-text completion (`<C-Space>` / `<Tab>`) still works |
| [`saghen/blink.cmp`](https://github.com/saghen/blink.cmp) | Registers a `poor-cli` source in blink.cmp | **Degraded** — inline ghost-text completion still works |
| [`lewis6991/gitsigns.nvim`](https://github.com/lewis6991/gitsigns.nvim) | AI-hunk signs in the sign column showing lines edited by the assistant | **Degraded** — `:PoorCLIDiff open` still shows the same hunks |
| [`stevearc/overseer.nvim`](https://github.com/stevearc/overseer.nvim) | Mirrors poor-cli tasks into overseer's task list | **Degraded** — `:PoorCLIPanel open tasks` still shows tasks |
| [`nvim-lualine/lualine.nvim`](https://github.com/nvim-lualine/lualine.nvim) | Cost / streaming-status component in the statusline | **Degraded** — cost still visible via `:PoorCLICost show`, `:PoorCLIDiag status` |
| [`nvim-treesitter/nvim-treesitter`](https://github.com/nvim-treesitter/nvim-treesitter) | Richer context extraction for completion / `:PoorCLIChat doc` | **Fallback** — uses native `vim.treesitter` (built into Neovim 0.9+) automatically |

Run `:checkhealth poor-cli` to see which integrations are currently active and which are missing.

### Lazy.nvim

```lua
{
    "gongahkia/poor-cli",
    submodules = false,
    dependencies = {
        "folke/snacks.nvim",        -- REQUIRED: notifications + pickers
        "folke/trouble.nvim",       -- REQUIRED: :Trouble poor-cli
        "mfussenegger/nvim-dap",    -- REQUIRED: breakpoint keymaps
        "NeogitOrg/neogit",         -- REQUIRED: auto-open-on-commit
    },
    config = function()
        require("poor-cli").setup({
            -- your options here
        })
    end,
}
```

### Packer

```lua
use {
    "gongahkia/poor-cli",
    requires = {
        "folke/snacks.nvim",
        "folke/trouble.nvim",
        "mfussenegger/nvim-dap",
        "NeogitOrg/neogit",
    },
    config = function()
        require("poor-cli").setup({})
    end,
}
```

### vim-plug

```vim
Plug 'gongahkia/poor-cli'

" In your init.vim after plug#end():
lua require('poor-cli').setup({})
```

### Manual Installation

```bash
# Clone the plugin
git clone https://github.com/gongahkia/poor-cli.git ~/.local/share/nvim/site/pack/poor-cli/start/nvim-poor-cli

# Or just copy the nvim-poor-cli directory
cp -r nvim-poor-cli ~/.local/share/nvim/site/pack/poor-cli/start/
```

## ⚙️ Configuration

```lua
require("poor-cli").setup({
    -- Server settings
    server_cmd = "poor-cli-server --stdio",
    server_log_file = nil,                   -- default: stdpath("state")/poor-cli/server.log
    auto_start = true,
    auto_restart = true,
    exit_stop_timeout_ms = 180,            -- hard stop budget on :wq / VimLeavePre
    
    -- Keymaps
    trigger_key = "<C-Space>",
    accept_key = "<Tab>",
    dismiss_key = "<Esc>",
    chat_key = "<leader>pc",
    checkpoints_key = nil,
    
    -- Appearance
    ghost_text_hl = "Comment",
    chat_width = 60,
    chat_position = "right",
    notifications = {
        group = "poor-cli",
        snacks = true,
    },

    -- Info-panel surface: "float" (default, centered/sidebar floats via
    -- snacks) or "vsplit" (legacy right-side vertical split).
    layout = {
        panels = "float",
        scratch = "float",
    },
    
    -- Default chat provider (nil = auto-detect from environment)
    provider = nil,
    model = nil,

    -- Optional completion-specific provider/model overrides
    completion_provider = nil,
    completion_model = nil,

    -- Completion behavior
    completion_enabled = true,
    completion_manual_only = false,
    completion_min_prefix = 0,
    completion_stream_partial = true,
    completion_max_lines_before = 80,
    completion_max_lines_after = 80,
    completion_max_chars = 16000,
    completion_lsp_context_max_chars = 4000,
    completion_filetype_allowlist = {},
    completion_filetype_blocklist = {},
    completion_buftype_blocklist = { "nofile", "prompt", "quickfix", "terminal" },

    -- Auto-triggered completion
    auto_trigger = false,
    trigger_delay = 500,

    -- Diagnostics
    diagnostics_enabled = false,
    dap = {
        keymaps_enabled = true,
        breakpoint_key = "<leader>pb",
        run_key = "<leader>pB",
    },
    
    -- Debug
    debug = false,
})
```

All poor-cli notifications route through `snacks.notify` using the configured `notifications.group`. The `snacks.dashboard` section is registered as `poor-cli`; add it to your Snacks dashboard sections to show session cost and active turns.

Info panels (`:PoorCLIPanel open tasks`, `:PoorCLIPanel open agents`, `:PoorCLIPanel open sessions`, `:PoorCLIPanel open automations`) open as right-side sidebar floats by default, with per-row action keymaps (e.g. `<CR>` detail, `x` cancel, `t` toggle, `h` history, `f` fork). Set `layout = { panels = "vsplit" }` to restore the legacy vertical-split sidebar.

## 🎮 Usage

### Chat Mentions

Type `@` in the chat input to pick a mention source. With `oil.nvim` installed, `@oil:` opens a temporary oil floating window; pressing `<CR>` on a file inserts `@file:<path>` into the chat input and closes the float.

### nvim-dap

When `nvim-dap` is installed, poor-cli adds buffer-local DAP maps only in the chat buffer and buffers with poor-cli assistant diagnostics. Put the cursor on a `file:line` reference and press `<leader>pb` to toggle a breakpoint there, or `<leader>pB` to toggle and call `dap.continue()`. poor-cli does not configure adapters or launch configs; your own DAP setup decides the debugger.

### blink.cmp

PoorCLI exposes a blink.cmp provider at `require("poor-cli.blink").provider()`:

```lua
require("blink.cmp").setup({
    sources = {
        default = { "lsp", "path", "snippets", "buffer", "poor-cli" },
        providers = {
            poor-cli = require("poor-cli.blink").provider(),
        },
    },
})
```

This reuses the same enablement rules and completion request shaping as the inline ghost-text path.

### Keymaps

| Keymap | Mode | Description |
|--------|------|-------------|
| `<C-Space>` | Insert | Trigger inline completion |
| `<Tab>` | Insert | Accept completion (or normal Tab) |
| `<Esc>` | Insert | Dismiss completion (or normal Esc) |
| `<leader>pc` | Normal | Toggle chat panel |
| `<leader>pc` | Visual | Send selection to chat |
| `<M-CR>` | Insert | Trigger completion with instruction |
| `gc` | Normal | Start insert and trigger completion |
| `<leader>pr` | Visual | Refactor selection |
| `<leader>pe` | Visual | Explain selection |
| `<leader>pb` | Normal | Toggle nvim-dap breakpoint at a poor-cli `file:line` reference |
| `<leader>pB` | Normal | Toggle breakpoint and run nvim-dap at a poor-cli `file:line` reference |

### Commands (v6.2)

All user interactions are behind **9 top-level commands**. Each takes a verb
and optional args: `:PoorCLI<Noun> <verb> [args]`. Tab-completion drives
discovery; the palette (`:PoorCLIHelp palette`) fuzzy-finds across every verb.

| Command | Role | Example verbs |
|---|---|---|
| `:PoorCLIChat` | Chat with the agent; inline completion; history; prompts; queue | `toggle send retry explain refactor test doc history prompt completion-accept queue` |
| `:PoorCLIReview` | Review agent edits; diff panel; timeline; checkpoints; code review | `diff timeline file pr commit lint checkpoint checkpoint-create` |
| `:PoorCLIContext` | What the agent is told; search; memory; watch; repo-map | `show search memory repo-map memory-save search-index watch` |
| `:PoorCLIAgent` | Agent runtime: tasks, sessions, plan, skills, workflows, automations, background agents | `runtime plan task session skill workflow automation sub-list` |
| `:PoorCLICost` | Cost dashboard, audit export | `dashboard show savings estimate audit-export` |
| `:PoorCLITrust` | Guardrails: permissions, sandbox, profile presets | `center repo profile profile-apply` |
| `:PoorCLIConfig` | Config, providers, server lifecycle | `set toggle provider server-start permission-mode sandbox` |
| `:PoorCLIDiag` | Diagnostics, MCP, services, docker sandbox, logs | `status doctor perf mcp tools service-status log-open` |
| `:PoorCLIHelp` | Palette, home, onboarding | `palette home onboarding` |

> **`:PoorCLIDeploy` was removed** in v6.2. Deploys are an agent tool: say it in chat (`:PoorCLIChat send deploy staging`).

### v6.3 — tools flow through the agent

Every plugin integration (neogit, DAP, Trouble, gitsigns, oil, overseer) is
now a *tool* the agent calls, not a command the user launches. This means
poor-cli is an agent that *uses* your plugins rather than a wrapper that
*exposes* them.

The agent has these tool families (registered in `poor_cli/tools/`):

| Domain | Tools | What it does |
|---|---|---|
| `git.*` | `status diff stage unstage commit log branch.{list,create,checkout} push` | Inspect/modify the repo. Prefers neogit for the commit UI; falls back to CLI. |
| `hunks.*` | `list stage reset ai_mark` | Per-file hunk-level operations. Gitsigns integration marks AI-authored hunks. |
| `debug.*` | `breakpoint.{set,clear} step continue stack eval` | Drives nvim-dap. |
| `diagnostics.*` | `emit clear list` | Agent-authored diagnostics surface in `:Trouble poor-cli`. |
| `fs.*` | `browse glob` | Structured directory listing and glob. Pops oil when available. |
| `task.*` | `run status logs cancel list` | Run overseer templates or managed subprocesses. |
| `deploy.*` | `run targets preview.{start,stop,status}` | Replaces the removed `:PoorCLIDeploy`. Reads `.poor-cli/deploy.json`. |
| `watch.*` | `directives.{list,consume,clear}` | Scans for `@poor-cli: <instruction>` comments; agent acts on them. |
| `review.*` | `pr changes lint` | Fetch GitHub PR, diff current changes, run linters. |

Each tool has a JSONSchema and a structured `ToolResult` return shape
(`TextBlock`, `CodeBlock`, `DiffBlock`, `TableBlock`, ...). When a preferred
plugin is missing the tool falls through to the CLI and sets
`metadata.degraded = "cli"` on the result. **No tool should hard-fail because
an optional plugin isn't installed.**

To talk through the agent instead of invoking the plugin directly:

| Instead of | Say in chat |
|---|---|
| opening neogit, writing a message, committing | "commit with a conventional message" |
| stepping through DAP | "set a breakpoint at line 42 of foo.py and run" |
| running deploy | "deploy staging" |
| checking pending TODOs | "check @poor-cli directives" |
| running lint | "lint current changes" |

### Health Check

Run `:checkhealth poor-cli` to verify:

- the configured `server_cmd`
- server log path creation
- Python availability
- detected API keys
- active provider/session state
- optional `nvim-cmp` attachment
- optional `blink.cmp` availability

## Guarded Execution

When the backend requests plan review, the plugin opens the chat panel, shows the plan summary, and prompts through `vim.ui.select()` for `Approve` or `Reject`. Permission reviews use the same backend RPC path and are surfaced through notifications.

## 🔧 API

For custom integrations, you can use the Lua API:

```lua
local poor-cli = require("poor-cli")

-- Server control
poor-cli.start()
poor-cli.stop()
poor-cli.is_running()

-- Completion
poor-cli.complete()      -- Trigger completion
poor-cli.accept()        -- Accept completion
poor-cli.dismiss()       -- Dismiss completion

-- Chat
poor-cli.toggle_chat()
poor-cli.send("Hello!")  -- Send message to chat
```

## 🧪 Testing

Lua specs run headlessly with plenary.busted:

```bash
make test-lua
```

The target uses `nvim-poor-cli/tests/minimal_init.lua`, keeps Neovim state under `nvim-poor-cli/.test-runtime/`, and loads plenary from `PLENARY_DIR` or `nvim-poor-cli/.test-runtime/site/pack/test/start/plenary.nvim`.

Spec files live in `nvim-poor-cli/tests/*_spec.lua`. Shared setup belongs in `nvim-poor-cli/tests/init.lua`; helpers belong in `nvim-poor-cli/tests/helpers/`.

Use the mock RPC helper when a spec touches backend calls:

```lua
local mock_rpc = require("helpers.mock_rpc")
mock_rpc.install()
require("poor-cli.rpc").request("poor-cli/ping", { ok = true })
mock_rpc.assert_called("poor-cli/ping", { ok = true })
```

Specs must not start or require a live `poor-cli-server`.

## 🩺 Troubleshooting

### Server won't start

1. Check that `poor-cli-server` is in your PATH: `which poor-cli-server`
2. Install if missing: `python3 -m pip install --upgrade 'poor-cli[all]'`
3. Check Python version: `python3 --version` (needs 3.11+)
4. Open the managed log with `:PoorCLIDiag log-open`
5. Capture a full report with `:PoorCLIDiag doctor`, `:PoorCLITrust center`, or `:PoorCLIDiag debug-copy`

### No completions appearing

1. Verify API key is set: `echo $GEMINI_API_KEY`
2. Check server status: `:PoorCLIDiag status`
3. Check whether completion is disabled for the current buffer/filetype in `:PoorCLIDiag status`
4. Inspect provider, sandbox, and rollback posture in `:PoorCLITrust center`
5. If you use `nvim-cmp`, run `:checkhealth poor-cli` to confirm the `poor-cli` source is registered
6. Open the server log with `:PoorCLIDiag log-open`

### blink.cmp source not appearing

1. Confirm `blink.cmp` is installed and loaded
2. Add `poor-cli = require("poor-cli.blink").provider()` to your blink `sources.providers`
3. Include `"poor-cli"` in blink `sources.default`
4. Run `:checkhealth poor-cli`

### Plan review prompt not appearing

1. Check that the server initialized successfully with `:PoorCLIDiag status`
2. Ensure your `vim.ui.select()` provider is working
3. Open the chat panel and inspect `:PoorCLIDiag doctor` for RPC errors and remediation guidance

### Ghost text not visible

1. Try a different highlight group: `ghost_text_hl = "NonText"`
2. Ensure your colorscheme has the highlight defined
3. If suggestions flash and disappear, use `:PoorCLIServer cancel` and inspect the log for request cancellations or provider errors

### Reporting bugs

When reporting a Neovim-side issue, include:

1. `:PoorCLIDiag debug-copy`
2. the contents of `:PoorCLIDiag log-open`
3. a minimal repro generated by `:PoorCLIDiag write-min-init`

## 📄 License

MIT License

## 🙏 Acknowledgements

- Built on [poor-cli](https://github.com/gongahkia/poor-cli) - the BYOK AI coding assistant
- Inspired by GitHub Copilot, Windsurf, and Codeium
