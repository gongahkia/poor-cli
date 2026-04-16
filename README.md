# gocli-poor

[![](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/gongahkia/poor-cli/actions/workflows/tests.yml)
[![](https://img.shields.io/badge/poor-cli_5.0.0-blue)](https://github.com/gongahkia/poor-cli)

> A fast, flicker-free TUI chat client for the poor-cli backend.

Demo asciicast: [https://asciinema.org/a/XXXXXX](https://asciinema.org/a/XXXXXX)

## Install

Backend (Python):

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli --version
```

Supported Python versions are `3.11`, `3.12`, `3.13`, and `3.14`.

Neovim plugin (lazy.nvim):

```lua
{ 'gongahkia/poor-cli', dir = '<path>/nvim-poor-cli',
  dependencies = {
    'folke/snacks.nvim',       -- REQUIRED: notifications + pickers
    'folke/trouble.nvim',      -- REQUIRED: :Trouble poor-cli
    'mfussenegger/nvim-dap',   -- REQUIRED: breakpoint keymaps
    'NeogitOrg/neogit',        -- REQUIRED: auto-open-on-commit
  },
  config = function() require('poor-cli').setup({}) end }
```

> **Required plugins:** snacks.nvim (notifications + pickers), trouble.nvim (diagnostics list), nvim-dap (breakpoint keymaps), neogit (commit flow). `setup()` lists every missing one and refuses to load until they're installed. See [nvim-poor-cli/README.md](./nvim-poor-cli/README.md#requirements) for the full list + per-plugin rationale.

Or from this checkout:

```sh
./install_nvim_plugin.sh
```

## Quickstart

```sh
export ANTHROPIC_API_KEY="..."
nvim
```

60-second path:

1. `:PoorCLIServer start` — attach to the backend.
2. `:PoorCLIChat toggle` — open the chat panel; send with `<CR>`.
3. `:PoorCLIProvider list` — switch provider or model.
4. `:PoorCLICost show` — inspect token and cost state.

Full walkthrough: [docs/quickstart.md](./docs/quickstart.md).

## Features

- Neovim-native chat, diff review, and inline completion surfaces.
- Streaming markdown chat with slash commands and @mentions.
- Provider/model picker and per-repo config.
- API-key prompt with keyring-backed backend storage.
- Cost, context-pressure, and savings dashboards.
- Checkpoint, session, and permission flows.
- snacks.nvim + trouble.nvim + nvim-dap + neogit (all required), plus optional blink.cmp / nvim-cmp / lualine / gitsigns / overseer / oil integrations.
- Treesitter-aware context; LSP-aware context.
- Policy + trust center.

## Provider Support

| Provider | Key | Default Model | Common Models | Capabilities in `poor-cli` |
|---|---|---|---|---|
| Gemini | `gemini` | `gemini-2.5-flash` | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite` | Streaming, function calling, system instructions, vision, JSON mode |
| OpenAI | `openai` | `gpt-5.1` | `gpt-5.1`, `gpt-5`, `gpt-5-mini` | Streaming, function calling, system instructions, JSON mode, vision on GPT-5/GPT-4.1-class models |
| Anthropic / Claude | `anthropic` (alias: `claude`) | `claude-sonnet-4-20250514` | `claude-sonnet-4-20250514`, `claude-3-7-sonnet-20250219`, `claude-3-5-haiku-20241022` | Streaming, function calling, system instructions, vision |
| OpenRouter | `openrouter` | `anthropic/claude-sonnet-4-20250514` | `openai/gpt-5`, `anthropic/claude-sonnet-4-20250514`, `google/gemini-2.5-flash`, `meta-llama/llama-4-maverick`, `deepseek/deepseek-r1` | Streaming, function calling, system instructions, vision (model-dependent) |
| Ollama | `ollama` | `llama3.1` | Auto-discovered from local `ollama` (`/api/tags`), with fallbacks `llama3.1`, `qwen2.5-coder`, `llama3.1:70b`, `mistral`, `codellama` | Streaming, system instructions, JSON mode, optional function calling for capable local models, local-only execution via `http://localhost:11434` |
| HF Local | `hf_local` | `Qwen/Qwen2.5-3B` | Local HuggingFace model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `Qwen/Qwen2.5-14B`, `meta-llama/Llama-3.2-3B` | System instructions, latent communication via local hidden-state access |
| vLLM | `vllm` | `Qwen/Qwen2.5-3B` | Served local model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `Qwen/Qwen2.5-14B`, `meta-llama/Llama-3.2-3B` | Streaming, system instructions over vLLM's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:8000/v1` |
| llama-server | `llama_server` | `local-model` | Served local model IDs such as `local-model`, `qwen2.5-coder`, `llama-3.2` | Streaming, system instructions over llama-server's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:8080/v1` |
| SGLang | `sglang` | `Qwen/Qwen2.5-3B` | Served local model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `Qwen/Qwen2.5-14B`, `meta-llama/Llama-3.2-3B` | Streaming, system instructions over SGLang's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:30000/v1` |
| HF TGI | `hf_tgi` | `tgi` | Served local model IDs such as `tgi`, `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B` | Streaming, system instructions over TGI's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:3000/v1` |
| LM Studio | `lmstudio` | `local-model` | Served local model IDs such as `local-model`, `qwen2.5-coder`, `llama-3.2` | Streaming, system instructions over LM Studio's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:1234/v1` |
| LiteLLM (any backend) | `litellm` | `groq/llama-3.1-70b-versatile` | `groq/llama-3.1-70b-versatile`, `groq/llama-3.1-8b-instant`, `cohere/command-r-plus`, `mistral/mistral-large-latest`, `bedrock/anthropic.claude-3-sonnet-20240229-v1:0` | Catch-all router to 100+ backends via litellm; feature parity varies by underlying backend |

## Configuration

Backend config (per-repo, persisted): `.poor-cli/` under repo root.

Neovim plugin config: pass options to `require('poor-cli').setup({ ... })` in your init.lua. See `:help poor-cli` and [nvim-poor-cli/README.md](./nvim-poor-cli/README.md).

## Documentation

- [Quickstart](./docs/quickstart.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Slash commands](./docs/COMMANDS.md)
- [Providers](./docs/PROVIDERS.md)
- [MCP](./docs/MCP.md)
- [Sandbox](./docs/SANDBOX.md)
- [Automations](./docs/AUTOMATIONS.md)
- [Economy](./docs/ECONOMY.md)
- [Neovim plugin](./nvim-poor-cli/README.md)

## License

MIT
