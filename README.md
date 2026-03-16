[![](https://img.shields.io/badge/poor_cli_1.0.0-passing-A8E6A3)](https://github.com/gongahkia/poor-cli/releases/tag/1.0.0)
[![](https://img.shields.io/badge/poor_cli_2.0.0-passing-7CD67A)](https://github.com/gongahkia/poor-cli/releases/tag/2.0.0)
[![](https://img.shields.io/badge/poor_cli_3.0.0-passing-50C878)](https://github.com/gongahkia/poor-cli/releases/tag/3.0.0)
[![](https://img.shields.io/badge/poor_cli_4.0.0-passing-2E8B57)](https://github.com/gongahkia/poor-cli/releases/tag/4.0.0)
![](https://github.com/gongahkia/poor-cli/actions/workflows/tests.yml/badge.svg)

# `poor-cli`

[Multiplayer](#multiplayer-lan--tunnel) & [BYOK](#model-support) [CLI](https://en.wikipedia.org/wiki/Command-line_interface) and [Neovim](https://neovim.io/) Coding Agent *(optimised for the [poor man](#available-commands))*.

<div align="center">
    <img src="./asset/logo/1.png" width="30%">
</div>

## Stack

* *Script*: [Rust](https://rust-lang.org/), [Python](https://www.python.org/), [Lua](https://www.lua.org/), [Vim Script](https://vimhelp.org/usr_41.txt.html), [Bash](https://www.gnu.org/software/bash/)
* *Dependencies*: [ratatui](https://crates.io/crates/ratatui), [crossterm](https://crates.io/crates/crossterm), [tokio](https://crates.io/crates/tokio), [clap](https://crates.io/crates/clap), [serde](https://crates.io/crates/serde), [google-genai](https://pypi.org/project/google-genai/), [rich](https://pypi.org/project/rich/), [PyYAML](https://pypi.org/project/PyYAML/), [aiofiles](https://pypi.org/project/aiofiles/), [aiohttp](https://pypi.org/project/aiohttp/), [cryptography](https://pypi.org/project/cryptography/)
* *Optional SDKs*: [openai](https://pypi.org/project/openai/), [anthropic](https://pypi.org/project/anthropic/)
* *CI/CD*: [black](https://black.readthedocs.io/), [ruff](https://docs.astral.sh/ruff/), [mypy](https://mypy.readthedocs.io/), [pytest](https://docs.pytest.org/), [Docker](https://www.docker.com/), [GitHub Actions](https://github.com/features/actions)

## Screenshots

![](./asset/reference/1.png)
![](./asset/reference/2.png)

## Usage

The below instructions are for locally hosting `poor-cli`. See screenshots [here](#screenshots).

1. Bootstrap the project.

```console
$ git clone https://github.com/gongahkia/poor-cli.git
$ cd poor-cli
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -e ".[dev]"
```

2. Configure providers.

```console
$ cp .env.example .env
```

You can still pre-create `.env` yourself, but it is no longer required before launch. `poor-cli` can now open a guided `/setup` editor in-chat, create `.env` from `.env.example`, and save API keys there for you. Local [Ollama](https://ollama.com/) still works with `ollama serve` and `ollama pull <model>`.

3. Start the CLI/TUI.

```console
$ ./run.sh                   # launches Rust TUI; use /setup if you need credentials
$ ./run_tui.sh               # direct Rust TUI launcher
$ python3 -m poor_cli        # Python wrapper -> Rust TUI if a Rust binary is available
$ poor-cli                   # requires repo launcher or `poor-cli-tui` already in PATH
$ poor-cli help              # show the full Python/TUI surface overview without launching the TUI
```

The Python package always provides `poor-cli-server`.
The interactive `poor-cli` command is supported from a repo checkout via `./run.sh` / `./run_tui.sh`,
or anywhere a `poor-cli-tui` binary is already installed.

4. Optional runtime overrides.

```console
$ poor-cli --provider ollama --model llama3
$ poor-cli --provider openai --model gpt-4o
$ poor-cli --remote-url ws://127.0.0.1:8765/rpc --remote-room dev --remote-token <token>
```

5. Run backend server directly (for editor integrations / host controls).

```console
$ poor-cli-server --stdio
$ poor-cli server --stdio
$ poor-cli-server --host --bind 0.0.0.0 --port 8765 --room dev
```

6. The Python entrypoint also exposes headless and automation surfaces.

```console
$ poor-cli exec --prompt "Summarize this repository" --plan-only
$ poor-cli task --help
$ poor-cli automation --help
$ poor-cli github-task --help
$ poor-cli skills --help
$ poor-cli commands --help
```

7. You can also run `poor-cli` with [Docker](https://www.docker.com/).

```console
$ docker build -t poor-cli .
$ docker run -it --env-file .env poor-cli
```

8. Finally, you can also use `poor-cli` directly through a [Neovim plugin](https://neovim.io/), where it provides inline ghost text completion and a chat panel similar to [Windsurf](https://windsurf.com/) or [Copilot](https://copilot.microsoft.com/). The easiest way to install this is through the [lazy.nvim](https://github.com/folke/lazy.nvim) Package Manager.

```lua
{
    "gongahkia/poor-cli",
    submodules = false,
    config = function()
        require("poor-cli").setup({
            trigger_key = "<C-Space>",  -- Trigger completion
            accept_key = "<Tab>",       -- Accept completion
            chat_key = "<leader>pc",    -- Toggle chat panel
            provider = nil,             -- Auto-detect from env
        })
    end,
}
```

## Multiplayer (LAN / Tunnel)

`poor-cli-server` can run in multiplayer WebSocket host mode with room-scoped
invite tokens and role permissions (`viewer` or `prompter`).

### Start host (LAN)

```console
$ poor-cli-server --host --bind 0.0.0.0 --port 8765 --room dev --room docs
```

The host prints:
- room names
- viewer/prompter tokens per room
- canonical viewer/prompter invite codes built from the externally joinable `joinWsUrl`
- ready-to-run join command examples that can be pasted into another TUI instance

### Optional ngrok helper

```console
$ poor-cli-server --host --bind 127.0.0.1 --port 8765 --room dev --ngrok
```

If `ngrok` is available in PATH, the host also prints `wss://.../rpc` join URLs.
If ngrok is unavailable/fails, local hosting continues normally.

### Join from TUI

```console
$ poor-cli --remote-url ws://HOST:8765/rpc --remote-room dev --remote-token <prompter-or-viewer-token>
```

### Join from Neovim

```lua
require("poor-cli").setup({
    multiplayer = {
        enabled = true,
        url = "ws://HOST:8765/rpc",
        room = "dev",
        token = "<prompter-or-viewer-token>",
    },
})
```

Neovim remote bridge mode now supports:
- guarded execution reviews (`planReq` -> `planRes`)
- room presence and role updates in `:PoorCliStatus`
- driver-targeted suggestions and room event notifications in the chat panel

Host lifecycle management and advanced room admin commands remain TUI-first.

### Tunnel alternatives

You can use cloudflared, Tailscale funnel, or any reverse tunnel/provider.
Expose the host `/rpc` endpoint and pass the resulting `ws://` or `wss://` URL
to `--remote-url` / `multiplayer.url`.

## Surface Matrix

| Surface | Chat + tools | Permission review | Plan review | Pair join | Pair host/admin | Room presence/status | Suggestions / handoff |
|---|---|---|---|---|---|---|---|
| Rust TUI (`poor-cli`) | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Neovim plugin (`nvim-poor-cli`) | Yes | Yes | Yes | Yes (remote bridge config) | No | Yes | Suggestions only |
| Remote stdio bridge (`poor-cli-server --bridge`) | Transport only | Client-dependent | Client-dependent | Yes | No | Client-dependent | Client-dependent |

Current install status:
- `poor-cli-server` ships with the Python package.
- Interactive `poor-cli` still requires either a repo checkout launcher or a separately installed `poor-cli-tui` binary.
- `poor-cli help` shows the full Python CLI surface, including `exec`, `task`, `automation`, `skills`, `commands`, `github-task`, and the `server` alias.
- In `auto-safe`, mutating tools are limited to trusted workspace roots and `bash` is restricted to allowlisted safe commands.

## Model support

`poor-cli` supports provider/model selection via `/switch` (inside TUI) or `--provider/--model` flags. You can pass any model ID accepted by the provider SDK/API.

| Provider | Key | Default Model | Common Models | Capabilities in `poor-cli` |
|---|---|---|---|---|
| Gemini | `gemini` | `gemini-2.0-flash` | `gemini-2.0-flash`, `gemini-1.5-pro` | Streaming, function calling, system instructions, vision, JSON mode |
| OpenAI | `openai` | `gpt-4-turbo` | `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo` | Streaming, function calling, system instructions, JSON mode, vision on GPT-4-class models |
| Anthropic / Claude | `anthropic` (alias: `claude`) | `claude-3-5-sonnet-20241022` | `claude-sonnet-4-20250514`, `claude-3-haiku-20240307` | Streaming, function calling, system instructions, vision |
| Ollama | `ollama` | `llama3` | Auto-discovered from local `ollama` (`/api/tags`), with fallbacks `llama3`, `codellama`, `mistral`, `phi3` | Streaming, system instructions, JSON mode, optional function calling (model-dependent), local-only execution via `http://localhost:11434` |

## Architecture

![](./asset/reference/architecture.png)

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
- `/compact` - Manage context (compact/compress/handoff)
- `/search` - Search transcript, tools, and diffs
- `/status` - Show session status summary
- `/export` - Export conversation history
- `/retry` - Retry last request
- `/edit-last` - Edit and resend last prompt
- `/copy` - Copy last assistant response
- `/quit` - Exit the TUI
- `/exit` - Exit the TUI (alias)
- `/clear` - Clear conversation history
- `/clear-output` - Clear screen output only

**Review & Safety:**
- `/review` - Review code or staged diff
- `/test` - Generate tests for a file
- `/permission-mode` - Show permission mode
- `/sandbox` - Show or set sandbox preset
- `/instructions` - Inspect the active instruction stack
- `/memory` - Show or update repo-local memory
- `/policy` - Inspect repo-local hooks and audit status
- `/context` - Open backend context inspector
- `/timeline` - Open agent timeline and diffs
- `/explain-diff` - Explain behavior and risk in current diff
- `/fix-failures` - Analyze latest test/lint failure output
- `/checkpoints` - List available checkpoints
- `/checkpoint` - Create manual checkpoint
- `/save` - Quick checkpoint alias
- `/rewind` - Restore checkpoint by id or latest
- `/restore` - Restore latest checkpoint
- `/diff` - Compare two files
- `/undo` - Undo last file change (checkpoint)
- `/plan-mode` - Toggle plan-first execution guidance

**Providers & Config:**
- `/provider` - Show active provider
- `/switch` - Switch provider/model
- `/providers` - List providers and models
- `/config` - Show active configuration
- `/model-info` - Show model capabilities
- `/profile` - Set execution profile (speed|safe|deep-review)
- `/broke` - Set poor mode (terse responses)
- `/my-treat` - Set rich mode (comprehensive responses)
- `/settings` - List editable config settings
- `/setup` - Open the guided API key and `.env` editor
- `/env` - Alias for the guided API key and `.env` editor
- `/api-key` - Open the API key editor
- `/api-key status` - Inspect provider API key status
- `/verbose` - Toggle verbose logging
- `/toggle` - Toggle boolean config value
- `/set` - Set config key to a value
- `/theme` - Show or set UI theme (dark/light)
- `/tools` - List backend tools
- `/mcp` - Inspect or control MCP servers and tools

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

**Automation & Tasks:**
- `/autopilot` - Toggle bounded autonomous execution mode
- `/qa` - Run background QA watch for lint/tests
- `/task` - Manage durable background tasks
- `/inbox` - Show pending and actionable tasks
- `/tasks` - Legacy alias for /task
- `/skills` - Inspect or run repo and user skills
- `/commands` - Inspect or run repo and user commands
- `/watch` - Watch directory for changes
- `/unwatch` - Stop watch mode

**Services & Shell:**
- `/doctor` - Run environment and service health checks
- `/service` - Manage local background services
- `/ollama` - Manage Ollama service and models
- `/run` - Run shell command via backend
- `/read` - Read file through backend
- `/pwd` - Show current working directory
- `/ls` - List files in directory

**Git & Workspace:**
- `/commit` - Create commit message from staged diff

**Collaboration:**
- `/collab` - Start, join, and manage collaboration sessions
- `/pair` - Legacy pair alias for collaboration sessions
- `/pass` - Hand driver role to the next collaborator
- `/suggest` - Send suggestion to the active driver
- `/leave` - Disconnect from collaboration session
- `/host-server` - Legacy advanced host controls for collaboration
- `/join-server` - Legacy join alias for invite/manual room entry
- `/kick` - Remove a room member from collaboration
- `/who` - Show room members and roles
- `/members` - Alias for /who

## Available Tools

`poor-cli` can currently use these tools.

* *File & Workspace Tools*: `read_file`, `write_file`, `edit_file`, `list_directory`, `glob_files`, `grep_files`, `copy_file`, `move_file`, `delete_file`, `create_directory`, `diff_files`
* *Execution & Quality Tools*: `bash`, `run_tests`, `format_and_lint`, `dependency_inspect`, `process_logs`
* *Git Tools*: `git_status`, `git_diff`, `git_status_diff`, `apply_patch_unified`
* *Network/Data Tools*: `fetch_url`, `web_search`, `json_yaml_edit`
* *Optional GitHub Tools* *(available when `gh` CLI is installed)*: `gh_pr_list`, `gh_pr_view`, `gh_pr_create`, `gh_pr_comment`, `gh_issue_list`, `gh_issue_view`
