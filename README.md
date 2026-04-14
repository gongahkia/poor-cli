[![](https://img.shields.io/badge/poor-cli_4.0.0-passing-light_green)](https://github.com/gongahkia/poor-cli/releases/tag/4.0.0)
[![](https://img.shields.io/badge/poor-cli_5.0.0-passing-green)](https://github.com/gongahkia/poor-cli/releases/tag/5.0.0)
![](https://github.com/gongahkia/poor-cli/actions/workflows/tests.yml/badge.svg)
![](https://github.com/gongahkia/poor-cli/actions/workflows/release.yml/badge.svg)

# `poor-cli`

```txt
  {o,o}    poor-cli
  /)__)    cost-controlled BYOK coding
  -"-"-    Neovim + local/cloud providers
```

Cost-controlled BYOK AI coding and invite-only multiplayer for Neovim.

`nvim-poor-cli` gives Neovim inline ghost text, chat, plan review, checkpoints, context panels, provider switching, budget guardrails, cost/savings dashboards, and shared sessions. The Python backend (`poor-cli-server --stdio`) owns model routing, tools, session state, policy checks, multiplayer invites, and telemetry for [`median_usd_per_completion`](./NORTH_STAR.md).

Start solo, then press `S` in the chat panel or run `:PoorCLICollabQuick` to copy a signed invite for a shared owner-authoritative session.

<!-- TODO: real screenshot. v6 placeholders are labeled in-image until owner-provided captures land. -->
![Neovim chat panel mid-response](./asset/reference/v6/1.png)

## Install

```console
$ python3 -m pip install --upgrade 'poor-cli[all]'
```

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

## Quickstart

1. Install the Python package and Neovim plugin.
2. Export one provider key, for example `export GEMINI_API_KEY=...`.
3. Open Neovim and run `:PoorCLIChat`.

Run `:checkhealth poor-cli` if the server does not start.

Credential lookup order is OS keyring, then env var, then plaintext config. Install `poor-cli[keyring]` or `poor-cli[all]` to enable macOS Keychain, Linux Secret Service, or Windows Credential Manager storage; env/plaintext fallback remains supported for CI and dev shells.

## Features

- Inline ghost text completion with manual trigger, accept, dismiss, and streaming partials.
- Chat panel with markdown rendering and request-scoped cancellation.
- Chat mention picker with optional `oil.nvim` `@oil:` file-path insertion.
- Cost guardrails, budget templates, model cost comparison, and savings dashboards.
- Provider switching across Gemini, OpenAI, Anthropic, OpenRouter, Ollama, HF Local, vLLM, llama-server, SGLang, HF TGI, and LM Studio.
- Guarded plan review, diagnostics, trust status, checkpoints, run history, and context panels.
- `nvim-cmp` and `blink.cmp` completion integration.
- Optional `snacks.nvim` notification grouping and dashboard section.
- First-class invite-only multiplayer with chat Share, quick invites, room panel, roles, and driver handoff.

## Screenshots

![Diff review panel placeholder](./asset/reference/v6/2.png)
![Cost HUD and lualine placeholder](./asset/reference/v6/3.png)
![Onboarding wizard placeholder](./asset/reference/v6/4.png)
![Navigator panels placeholder](./asset/reference/v6/5.png)

## How It Works

```txt
Neovim buffers, chat, panels
            |
            v
Lua plugin: nvim-poor-cli
            |
            v
JSON-RPC over stdio
            |
            v
Python server: poor-cli-server
            |
            +--> provider adapters
            +--> tool execution + policy
            +--> sessions + checkpoints
            +--> cost + savings telemetry
            +--> multiplayer invites + room state
```

## Model Support

`poor-cli` uses provider/model selection through the Python backend. Pass any model ID accepted by the selected provider.

Latent-space inter-agent communication is available only through `hf_local` with `research.latent_communication.enabled = true`; Ollama, vLLM, llama-server, SGLang, HF TGI, LM Studio, and cloud providers use text hand-offs.

| Provider | Key | Default Model | Common Models | Capabilities in `poor-cli` |
|---|---|---|---|---|
| Gemini | `gemini` | `gemini-2.5-flash` | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite` | Streaming, function calling, system instructions, vision, JSON mode |
| OpenAI | `openai` | `gpt-5.1` | `gpt-5.1`, `gpt-5`, `gpt-5-mini` | Streaming, function calling, system instructions, JSON mode, vision on GPT-5/GPT-4.1-class models |
| Anthropic / Claude | `anthropic` (alias: `claude`) | `claude-sonnet-4-20250514` | `claude-sonnet-4-20250514`, `claude-3-7-sonnet-20250219`, `claude-3-5-haiku-20241022` | Streaming, function calling, system instructions, vision |
| OpenRouter | `openrouter` | `anthropic/claude-sonnet-4-20250514` | `anthropic/claude-sonnet-4-20250514`, `openai/gpt-5`, `google/gemini-2.5-flash`, `meta-llama/llama-4-maverick`, `deepseek/deepseek-r1` | Streaming, function calling, system instructions, vision (model-dependent) |
| Ollama | `ollama` | `llama3.1` | Auto-discovered from local `ollama` (`/api/tags`), with fallbacks `llama3.1`, `qwen2.5-coder`, `mistral`, `codellama` | Streaming, system instructions, JSON mode, optional function calling for capable local models, local-only execution via `http://localhost:11434` |
| HF Local | `hf_local` | `Qwen/Qwen2.5-3B` | Local HuggingFace model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `meta-llama/Llama-3.2-3B` | System instructions, latent communication via local hidden-state access |
| vLLM | `vllm` | `Qwen/Qwen2.5-3B` | Served local model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `meta-llama/Llama-3.2-3B` | Streaming, system instructions over vLLM's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:8000/v1` |
| llama-server | `llama_server` | `local-model` | Served local model IDs such as `local-model`, `qwen2.5-coder`, `llama-3.2` | Streaming, system instructions over llama-server's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:8080/v1` |
| SGLang | `sglang` | `Qwen/Qwen2.5-3B` | Served local model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `meta-llama/Llama-3.2-3B` | Streaming, system instructions over SGLang's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:30000/v1` |
| HF TGI | `hf_tgi` | `tgi` | Served local model IDs such as `tgi`, `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B` | Streaming, system instructions over TGI's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:3000/v1` |
| LM Studio | `lmstudio` | `local-model` | Served local model IDs such as `local-model`, `qwen2.5-coder`, `llama-3.2` | Streaming, system instructions over LM Studio's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:1234/v1` |

## MCP

Configure MCP servers in `.poor-cli/mcp.json`:

```json
{
  "multi": true,
  "registry_autodiscover": false,
  "servers": [
    {
      "name": "github",
      "transport": "stdio",
      "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
      "enabled": true
    },
    {
      "name": "docs",
      "transport": "http",
      "url": "http://127.0.0.1:3333/mcp",
      "enabled": true
    }
  ]
}
```

Tools are registered as `<server>:<tool>`, for example `github:create_issue`. Registry lookup is off by default; enable only on demand with `registry_autodiscover: true` in `.poor-cli/mcp.json` or `mcp.registry.enabled: true` in config.

## Multiplayer

`poor-cli-server` runs invite-only, owner-authoritative P2P sessions over WebRTC DataChannels. In Neovim, press `S` in `:PoorCLIChat` or run:

```vim
:PoorCLICollabQuick
```

Neovim can also join through a signed invite:

```lua
require("poor-cli").setup({
    multiplayer = {
        enabled = true,
        invite = "<signed-viewer-or-prompter-invite>",
    },
})
```

See [docs/MULTIPLAYER.md](./docs/MULTIPLAYER.md) for protocol details, invite format, host setup, and failure behavior. A 2-minute multiplayer demo is the Phase 20 gating marketing deliverable.

## Commands

Neovim commands, keymaps, health checks, blink.cmp setup, and troubleshooting live in [nvim-poor-cli/README.md#commands](./nvim-poor-cli/README.md#commands).

Core entry points:

- `:PoorCLIChat`
- `:PoorCLIComplete`
- `:PoorCLIStatus`
- `:PoorCLITrust`
- `:PoorCLIDoctor`
- `:PoorCLICheckpoints`

## Development

Supported Python versions are `3.11`, `3.12`, `3.13`, and `3.14`.

```console
$ git clone https://github.com/gongahkia/poor-cli.git
$ cd poor-cli
$ python3 -m venv .venv
$ source .venv/bin/activate
$ python3 -m pip install -e '.[all,dev]'
$ make lint
$ make test
```

## License

MIT.

## Acknowledgements

Inspired by Neovim-native AI workflows and BYOK provider control.
