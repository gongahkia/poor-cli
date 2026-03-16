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
- Python 3.8+
- `poor-cli` Python package installed: `pip install poor-cli` (provides `poor-cli-server`)
- At least one API key: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`
- Optional: `telescope.nvim` for `:PoorCliCheckpoints`

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
    
    -- Default chat provider (nil = auto-detect from environment)
    provider = nil,
    model = nil,

    -- Optional completion-specific provider/model overrides
    completion_provider = nil,
    completion_model = nil,

    -- Optional remote multiplayer bridge
    multiplayer = {
        enabled = false,
        url = nil,
        room = nil,
        token = nil,
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
    
    -- Debug
    debug = false,
})
```

## 🎮 Usage

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

### Commands

| Command | Description |
|---------|-------------|
| `:PoorCliStart` | Start the AI server |
| `:PoorCliStop` | Stop the AI server |
| `:PoorCliRestart` | Restart the AI server and re-initialize the session |
| `:PoorCliCancel` | Cancel the active inline/chat request |
| `:PoorCliStatus` | Show server state, provider info, completion state, trusted-workspace status, stderr excerpt, and room state |
| `:PoorCliChat` | Toggle chat panel |
| `:PoorCliSend [message]` | Send message to chat |
| `:PoorCliClear` | Clear chat history |
| `:PoorCliDoctor` | Open a diagnostic report with status, config, and recent stderr |
| `:PoorCliCopyDebugInfo` | Copy a bug-report bundle to the clipboard |
| `:PoorCliOpenLog` | Open the managed poor-cli server log |
| `:PoorCliOpenStateDir` | Open the plugin state directory |
| `:PoorCliWriteMinInit [path]` | Generate a minimal Neovim config for reproduction |
| `:PoorCliDiagnostics` | Toggle assistant diagnostics integration |
| `:PoorCliCheckpoints` | Browse and restore checkpoints (Telescope) |
| `:PoorCliComplete` | Trigger inline completion |
| `:PoorCliAccept` | Accept current completion |
| `:PoorCliDismiss` | Dismiss current completion |
| `:PoorCliAcceptLine` | Accept the current completion line |
| `:PoorCliAcceptWord` | Accept the next completion word |
| `:PoorCliSwitchProvider [provider]` | Switch AI provider |
| `:'<,'>PoorCliExplain` | Explain selected code |
| `:'<,'>PoorCliRefactor` | Refactor selected code |
| `:PoorCliTest` | Generate tests for current function |
| `:PoorCliDoc` | Generate docs for current function |

### Health Check

Run `:checkhealth poor-cli` to verify:

- the configured `server_cmd`
- server log path creation
- Python availability
- detected API keys
- active provider/session state
- optional `nvim-cmp` attachment

## Guarded Execution

When the backend requests plan review, the plugin opens the chat panel, shows the plan summary, and prompts through `vim.ui.select()` for `Approve` or `Reject`. Permission reviews use the same backend RPC path and are surfaced through notifications.

## Remote Multiplayer Bridge

Configure the plugin to attach to an existing host room:

```lua
require("poor-cli").setup({
    multiplayer = {
        enabled = true,
        url = "ws://HOST:8765/rpc",
        room = "dev",
        token = "<viewer-or-prompter-token>",
    },
})
```

What Neovim currently supports:
- joining an existing room through the stdio bridge
- room/member state updates in `:PoorCliStatus`
- trusted-workspace boundary visibility in `:PoorCliStatus`
- plan review prompts, room events, and suggestions in the chat panel

What remains TUI-first:
- creating/stopping host sessions
- advanced room admin commands (`/host-server ...`)
- direct `/pass` and `/pair` command UX inside Neovim

## 🔧 API

For custom integrations, you can use the Lua API:

```lua
local poor_cli = require("poor-cli")

-- Server control
poor_cli.start()
poor_cli.stop()
poor_cli.is_running()

-- Completion
poor_cli.complete()      -- Trigger completion
poor_cli.accept()        -- Accept completion
poor_cli.dismiss()       -- Dismiss completion

-- Chat
poor_cli.toggle_chat()
poor_cli.send("Hello!")  -- Send message to chat
```

## 🩺 Troubleshooting

### Server won't start

1. Check that `poor-cli-server` is in your PATH: `which poor-cli-server`
2. Install if missing: `pip install poor-cli`
3. Check Python version: `python3 --version` (needs 3.8+)
4. Open the managed log with `:PoorCliOpenLog`
5. Capture a full report with `:PoorCliDoctor` or `:PoorCliCopyDebugInfo`

### No completions appearing

1. Verify API key is set: `echo $GEMINI_API_KEY`
2. Check server status: `:PoorCliStatus`
3. Check whether completion is disabled for the current buffer/filetype in `:PoorCliStatus`
4. If you use `nvim-cmp`, run `:checkhealth poor-cli` to confirm the `poor-cli` source is registered
5. Open the server log with `:PoorCliOpenLog`

### Plan review prompt not appearing

1. Check that the server initialized successfully with `:PoorCliStatus`
2. Ensure your `vim.ui.select()` provider is working
3. Open the chat panel and inspect `:PoorCliDoctor` for RPC errors and stderr

### Multiplayer room state missing

1. Confirm `multiplayer.enabled = true` and that `url`, `room`, and `token` are all set
2. Check `:PoorCliStatus` for room, role, and member count
3. Verify the remote host `/rpc` endpoint is reachable from Neovim

### Ghost text not visible

1. Try a different highlight group: `ghost_text_hl = "NonText"`
2. Ensure your colorscheme has the highlight defined
3. If suggestions flash and disappear, use `:PoorCliCancel` and inspect the log for request cancellations or provider errors

### Reporting bugs

When reporting a Neovim-side issue, include:

1. `:PoorCliCopyDebugInfo`
2. the contents of `:PoorCliOpenLog`
3. a minimal repro generated by `:PoorCliWriteMinInit`

## 📄 License

MIT License - see [LICENSE](../LICENSE)

## 🙏 Acknowledgements

- Built on [poor-cli](https://github.com/gongahkia/poor-cli) - the BYOK AI coding assistant
- Inspired by GitHub Copilot, Windsurf, and Codeium
