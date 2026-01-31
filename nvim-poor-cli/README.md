# nvim-poor-cli

[![Neovim](https://img.shields.io/badge/Neovim-0.9%2B-green.svg)](https://neovim.io/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**AI-powered inline code completion and chat for Neovim** - like Windsurf/Copilot but with your own API keys (BYOK).

## ✨ Features

- 🪄 **Inline Ghost Text Completion** - Windsurf-style inline suggestions
- 💬 **Chat Panel** - Conversational AI with markdown rendering
- 🔄 **Multi-Provider Support** - Gemini, OpenAI, Claude, Ollama
- 🛠️ **AI Commands** - Explain, Refactor, Generate Tests, Generate Docs
- ⚡ **Streaming Responses** - Real-time AI output
- 🎯 **Context-Aware** - Uses open buffers as context
- 🔐 **BYOK** - Bring Your Own Key, no subscription needed

## 📦 Installation

### Requirements

- Neovim 0.9+
- Python 3.8+
- `poor-cli` installed: `pip install poor-cli`
- At least one API key: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`

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
    server_cmd = "poor-cli-server --stdio",  -- Server command
    auto_start = true,                        -- Auto-start on setup
    
    -- Keymaps
    trigger_key = "<C-Space>",  -- Trigger completion in insert mode
    accept_key = "<Tab>",       -- Accept completion (falls back to Tab if no completion)
    dismiss_key = "<Esc>",      -- Dismiss completion (falls back to Esc if no completion)
    chat_key = "<leader>pc",    -- Toggle chat panel
    
    -- Appearance
    ghost_text_hl = "Comment",  -- Highlight group for ghost text
    chat_width = 60,            -- Chat panel width
    chat_position = "right",    -- "right" or "left"
    
    -- AI Provider (nil = auto-detect from environment)
    provider = nil,     -- "gemini", "openai", "anthropic", "ollama"
    model = nil,        -- Specific model name
    
    -- Auto-completion
    auto_trigger = false,   -- Auto-trigger on CursorHoldI
    trigger_delay = 500,    -- Delay in ms for auto-trigger
    
    -- Debug
    debug = false,          -- Enable debug logging
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
| `:PoorCliStatus` | Show server status and provider info |
| `:PoorCliChat` | Toggle chat panel |
| `:PoorCliSend [message]` | Send message to chat |
| `:PoorCliClear` | Clear chat history |
| `:PoorCliComplete` | Trigger inline completion |
| `:PoorCliAccept` | Accept current completion |
| `:PoorCliDismiss` | Dismiss current completion |
| `:PoorCliSwitchProvider [provider]` | Switch AI provider |
| `:'<,'>PoorCliExplain` | Explain selected code |
| `:'<,'>PoorCliRefactor` | Refactor selected code |
| `:PoorCliTest` | Generate tests for current function |
| `:PoorCliDoc` | Generate docs for current function |

### Health Check

Run `:checkhealth poor-cli` to verify your setup.

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

### No completions appearing

1. Verify API key is set: `echo $GEMINI_API_KEY`
2. Check server status: `:PoorCliStatus`
3. Enable debug mode: `require("poor-cli").setup({ debug = true })`
4. Check `:messages` for errors

### Ghost text not visible

1. Try a different highlight group: `ghost_text_hl = "NonText"`
2. Ensure your colorscheme has the highlight defined

## 📄 License

MIT License - see [LICENSE](../LICENSE)

## 🙏 Acknowledgements

- Built on [poor-cli](https://github.com/gongahkia/poor-cli) - the BYOK AI coding assistant
- Inspired by GitHub Copilot, Windsurf, and Codeium
