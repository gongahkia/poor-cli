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

## Available Commands

Type `@path/to/file` in any message to attach file context.
Use quoted refs for spaces: `@"docs/My File.md"` or `@'docs/My File.md'`.
Run `!<command> [| optional question]` to execute local shell output and optionally ask the model about it.

**Core Workflow:**
- `/help` - Show all available commands
- `/onboarding` - Start guided CLI onboarding
- `/plan` - Generate a plan before executing
- `/history` - Show recent messages
- `/sessions` - List recent sessions
- `/new-session` - Start a fresh session
- `/queue` - Manage prompt queue (add/list/clear/drop)
- `/compact` - Manage context (auto/compact/gentle/aggressive/compress/handoff)
- `/search` - Search transcript, tools, and diffs
- `/status` - Show canonical session status summary
- `/runs` - Inspect recent shared run history
- `/audit-export` - Export audit log JSONL
- `/workflow` - Legacy alias: inspect slash-trigger AutomationRule scaffolds
- `/export` - Export conversation history
- `/retry` - Retry last request
- `/edit-last` - Edit and resend last prompt
- `/copy` - Copy last assistant response
- `/quit` - Exit the TUI
- `/exit` - Exit the TUI (alias)
- `/clear` - Clear conversation history
- `/clear-output` - Clear screen output only
- `/cost` - Show session token usage and estimated cost
- `/ollama-models` - List locally available Ollama models
- `/mcp-health` - Check health of MCP servers

**Review & Safety:**
- `/review` - Review code or staged diff
- `/test` - Generate tests for a file
- `/permission-mode` - Show permission mode
- `/sandbox` - Show or set sandbox preset
- `/instructions` - Inspect the active instruction stack
- `/memory` - Show or update repo-local memory
- `/policy` - Inspect repo-local hooks and audit status
- `/docker-sandbox` - Show Docker sandbox status and resource limits
- `/context` - Open backend context inspector or `/context explain`
- `/trust` - Open the trust center for provider, sandbox, rollback, and policy state
- `/timeline` - Open agent timeline and diffs
- `/explain-diff` - Explain behavior and risk in current diff
- `/fix-failures` - Analyze latest test/lint failure output
- `/checkpoints` - Browse and manage checkpoints
- `/checkpoint` - Create named checkpoint (optional label)
- `/save` - Quick checkpoint alias
- `/rewind` - Restore checkpoint (alias for /undo)
- `/restore` - Restore latest checkpoint (alias for /undo)
- `/diff` - Compare two files
- `/undo` - Undo file changes (restore last or specific checkpoint)
- `/plan-mode` - Toggle plan-first execution guidance
- `/gc` - Clean up stale checkpoints

**Providers & Config:**
- `/provider` - Show provider info, models, or switch (F2)
- `/switch` - Switch provider/model (alias for /provider switch)
- `/providers` - List providers (alias for /provider switch)
- `/config` - Show active configuration
- `/model-info` - Show model capabilities (alias for /provider)
- `/profile` - Set execution profile (speed|safe|deep-review)
- `/settings` - List editable config settings
- `/setup` - Open the guided setup summary and recommended first workflow
- `/env` - API key editor (alias for /setup)
- `/api-key` - Open the API key editor or use `/api-key status`
- `/verbose` - Toggle verbose logging
- `/toggle` - Toggle boolean config value
- `/set` - Set config key to a value
- `/theme` - Show or set UI theme (dark/light)
- `/tools` - List backend tools
- `/mcp` - Inspect or control MCP servers and tools

**Economy & Output:**
- `/broke` - Set frugal mode (terse responses)
- `/my-treat` - Set rich mode (comprehensive responses)
- `/economy` - Show or switch economy preset (frugal|balanced|quality)
- `/savings` - Show economy savings dashboard
- `/cache-clear` - Clear semantic response cache

**Context & Reuse:**
- `/files` - List pinned context files
- `/add` - Pin file/directory for context
- `/drop` - Unpin context file
- `/clear-files` - Clear all pinned context files
- `/focus` - Manage persistent coding focus state
- `/resume` - Resume with branch/checkpoint/session summary
- `/workspace-map` - Summarize repository layout and hotspots
- `/bootstrap` - Detect project type and suggest quickstart commands
- `/context-budget` - Rank context files against a token budget
- `/image` - Queue image for next message
- `/save-prompt` - Save reusable prompt
- `/use` - Load and run saved prompt
- `/prompts` - List saved prompts
- `/save-session` - Save current session for later restore
- `/restore-session` - Restore most recent saved session

**Automation & Tasks:**
- `/autopilot` - Toggle bounded autonomous execution mode
- `/qa` - Run background QA watch for lint/tests
- `/task` - Manage durable background tasks, including retry and replay
- `/automation` - Inspect AutomationRule run history and replay runs
- `/inbox` - Show pending and actionable tasks
- `/skills` - Inspect or run repo and user skills
- `/commands` - Legacy alias: inspect or run slash-trigger AutomationRules
- `/watch` - Watch directory for changes
- `/unwatch` - Stop watch mode

**Services & Shell:**
- `/doctor` - Open structured diagnostics with remediation guidance
- `/preview` - Start or manage web preview server with live reload
- `/deploy` - Detect targets and deploy project to cloud platforms
- `/service` - Manage local background services
- `/ollama` - Manage Ollama service and models
- `/run` - Run shell command via backend
- `/read` - Read file through backend
- `/pwd` - Show current working directory
- `/ls` - List files in directory

**Git & Workspace:**
- `/commit` - Create commit message from staged diff

**Collaboration:**
- `/collab` - Start, join, summarize, and manage collaboration sessions
- `/pass` - Hand driver role to the next collaborator
- `/suggest` - Send suggestion to the active driver
- `/leave` - Disconnect from collaboration session

**Workflows:**
- `/standup` - Summarize yesterday's git activity for standup
- `/weekly-update` - Synthesize this week's PRs into a weekly update
- `/pr-summary` - Summarize recent PRs by teammate and theme
- `/release-notes` - Draft release notes from merged PRs
- `/release-check` - Pre-release verification: changelog, migrations, tests
- `/changelog` - Update changelog with this week's highlights
- `/ci-failures` - Summarize CI failures and flaky tests; suggest fixes
- `/ci-debug` - Debug latest CI failure; find root cause
- `/triage` - Triage new issues; suggest owner, priority, labels
- `/scan-bugs` - Scan recent commits for likely bugs
- `/test-coverage` - Find untested paths and add focused tests
- `/perf-audit` - Audit recent changes for performance regressions
- `/dep-drift` - Detect dependency drift and propose alignment
- `/dep-upgrade` - Scan outdated deps; propose safe upgrades
- `/update-docs` - Update project docs with recent changes
- `/skill-suggest` - Suggest next skills to deepen from recent work
- `/perf-opportunity` - Find top performance improvement opportunities
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
