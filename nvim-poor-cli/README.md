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
- 🤝 **Remote Multiplayer Bridge** - Pair-session status, role updates, room events, and driver suggestions
- 🧾 **Fail-Open Debugging** - managed server log, doctor report, copyable debug bundle, and minimal repro init generation
- 🔐 **BYOK** - Bring Your Own Key, no subscription needed

## 📦 Installation

### Requirements

- Neovim 0.9+
- Python 3.11+
- `poor-cli` Python package installed: `python3 -m pip install --upgrade 'poor-cli[all]'` (provides `poor-cli-server`)
- At least one API key: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`
- Optional: `telescope.nvim` for `:PoorCLICheckpoints`
- Optional: `trouble.nvim` for `:Trouble poor-cli`
- Optional: `snacks.nvim` for grouped non-error notifications and a dashboard section
- Optional: `oil.nvim` for `@oil:` chat mentions

### Lazy.nvim

```lua
{
    "gongahkia/poor-cli",
    submodules = false,
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
    
    -- Default chat provider (nil = auto-detect from environment)
    provider = nil,
    model = nil,

    -- Optional completion-specific provider/model overrides
    completion_provider = nil,
    completion_model = nil,

    -- Invite-only remote multiplayer bridge
    multiplayer = {
        enabled = false,
        invite = nil,
    },
    
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

With `snacks.nvim` installed, non-error poor-cli notifications route through `snacks.notify` using the configured `notifications.group`. Error-level notifications stay on `vim.notify`. The optional `snacks.dashboard` section is registered as `poor-cli`; add it to your Snacks dashboard sections to show session cost and active turns.

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

### Commands

| Command | Description |
|---------|-------------|
| `:PoorCLIStart` | Start the AI server |
| `:PoorCLIStop` | Stop the AI server |
| `:PoorCLIRestart` | Restart the AI server and re-initialize the session |
| `:PoorCLICancel` | Cancel the active inline/chat request |
| `:PoorCLIStatus` | Show the shared session status summary with routing, context, and collaboration state |
| `:PoorCLITrust` | Open the trust center for provider, sandbox, rollback, policy, and privacy posture |
| `:PoorCLIRuns` | Open recent shared run history |
| `:PoorCLIWorkflow [name]` | Legacy alias: list slash-trigger AutomationRule scaffolds |
| `:PoorCLIContext` | Open the backend context explanation for the current editing session |
| `:PoorCLIChat` | Toggle chat panel |
| `:PoorCLISend [message]` | Send message to chat |
| `:PoorCLIClear` | Clear chat history |
| `:PoorCLIDoctor` | Open a structured diagnostic report with actionable remediation |
| `:PoorCLICopyDebugInfo` | Copy a bug-report bundle to the clipboard |
| `:PoorCLIOpenLog` | Open the managed poor-cli server log |
| `:PoorCLIOpenStateDir` | Open the plugin state directory |
| `:PoorCLIWriteMinInit [path]` | Generate a minimal Neovim config for reproduction |
| `:PoorCLIDiagnostics` | Toggle assistant diagnostics integration |
| `:PoorCLITrouble` | Open assistant diagnostics in trouble.nvim (`:Trouble poor-cli`) |
| `:PoorCLICheckpoints` | Browse and restore checkpoints (Telescope) |
| `:PoorCLIComplete` | Trigger inline completion |
| `:PoorCLIAccept` | Accept current completion |
| `:PoorCLIDismiss` | Dismiss current completion |
| `:PoorCLIAcceptLine` | Accept the current completion line |
| `:PoorCLIAcceptWord` | Accept the next completion word |
| `:PoorCLISwitchProvider [provider]` | Switch AI provider |
| `:'<,'>PoorCLIExplain` | Explain selected code |
| `:'<,'>PoorCLIRefactor` | Refactor selected code |
| `:PoorCLITest` | Generate tests for current function |
| `:PoorCLIDoc` | Generate docs for current function |

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

## Multiplayer

Press `S` in `:PoorCLIChat` or run `:PoorCLICollabQuick` to start or share a prompter invite. Open the room panel with `:PoorCLIRoom`.

Configure the plugin to attach to an existing host room:

```lua
require("poor-cli").setup({
    multiplayer = {
        enabled = true,
        invite = "<signed-viewer-or-prompter-invite>",
    },
})
```

Neovim supports:
- chat-panel Share via `S`
- quick invite creation with `:PoorCLICollabQuick [viewer|prompter]`
- joining an existing room through the stdio bridge
- room/member state updates in `:PoorCLIStatus`
- room panel via `:PoorCLIRoom`
- trust-center visibility in `:PoorCLITrust`
- plan review prompts, room events, suggestions, and driver handoff

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

## 🩺 Troubleshooting

### Server won't start

1. Check that `poor-cli-server` is in your PATH: `which poor-cli-server`
2. Install if missing: `python3 -m pip install --upgrade 'poor-cli[all]'`
3. Check Python version: `python3 --version` (needs 3.11+)
4. Open the managed log with `:PoorCLIOpenLog`
5. Capture a full report with `:PoorCLIDoctor`, `:PoorCLITrust`, or `:PoorCLICopyDebugInfo`

### No completions appearing

1. Verify API key is set: `echo $GEMINI_API_KEY`
2. Check server status: `:PoorCLIStatus`
3. Check whether completion is disabled for the current buffer/filetype in `:PoorCLIStatus`
4. Inspect provider, sandbox, and rollback posture in `:PoorCLITrust`
5. If you use `nvim-cmp`, run `:checkhealth poor-cli` to confirm the `poor-cli` source is registered
6. Open the server log with `:PoorCLIOpenLog`

### blink.cmp source not appearing

1. Confirm `blink.cmp` is installed and loaded
2. Add `poor-cli = require("poor-cli.blink").provider()` to your blink `sources.providers`
3. Include `"poor-cli"` in blink `sources.default`
4. Run `:checkhealth poor-cli`

### Plan review prompt not appearing

1. Check that the server initialized successfully with `:PoorCLIStatus`
2. Ensure your `vim.ui.select()` provider is working
3. Open the chat panel and inspect `:PoorCLIDoctor` for RPC errors and remediation guidance

### Multiplayer room state missing

1. Run `:PoorCLICollabQuick` to start or share a host invite
2. Confirm joiners have `multiplayer.enabled = true` and an `invite`
3. Check `:PoorCLIStatus` or `:PoorCLICollab summary` for room, role, and member count
4. Verify the remote host `/rpc` endpoint is reachable from Neovim

### Ghost text not visible

1. Try a different highlight group: `ghost_text_hl = "NonText"`
2. Ensure your colorscheme has the highlight defined
3. If suggestions flash and disappear, use `:PoorCLICancel` and inspect the log for request cancellations or provider errors

### Reporting bugs

When reporting a Neovim-side issue, include:

1. `:PoorCLICopyDebugInfo`
2. the contents of `:PoorCLIOpenLog`
3. a minimal repro generated by `:PoorCLIWriteMinInit`

## 📄 License

MIT License

## 🙏 Acknowledgements

- Built on [poor-cli](https://github.com/gongahkia/poor-cli) - the BYOK AI coding assistant
- Inspired by GitHub Copilot, Windsurf, and Codeium
