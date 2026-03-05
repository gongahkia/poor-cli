[![](https://img.shields.io/badge/poor_cli_1.0.0-passing-90EE90)](https://github.com/gongahkia/poor-cli/releases/tag/1.0.0)
[![](https://img.shields.io/badge/poor_cli_2.0.0-passing-97CA00)](https://github.com/gongahkia/poor-cli/releases/tag/2.0.0)
[![](https://img.shields.io/badge/poor_cli_3.0.0-passing-6BA82E)](https://github.com/gongahkia/poor-cli/releases/tag/3.0.0)
[![](https://img.shields.io/badge/poor_cli_4.0.0-passing-6BA82E)](https://github.com/gongahkia/poor-cli/releases/tag/4.0.0)
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

Set at least one API key in `.env` (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) or use local [Ollama](https://ollama.com/) with `ollama serve` and `ollama pull <model>`.

3. Start the CLI/TUI.

```console
$ ./run.sh                   # checks .env, then launches Rust TUI
$ ./run_tui.sh               # direct Rust TUI launcher
$ python -m poor_cli         # Python wrapper -> Rust TUI
$ poor-cli                   # installed entrypoint -> Rust TUI
```

4. Optional runtime overrides.

```console
$ poor-cli --provider ollama --model llama3
$ poor-cli --provider openai --model gpt-4o
$ poor-cli --remote-url ws://127.0.0.1:8765/rpc --remote-room dev --remote-token <token>
```

5. Run backend server directly (for editor integrations / host controls).

```console
$ poor-cli-server --stdio
$ poor-cli-server --host --bind 0.0.0.0 --port 8765 --room dev
```

6. You can also run `poor-cli` with [Docker](https://www.docker.com/).

```console
$ docker build -t poor-cli .
$ docker run -it --env-file .env poor-cli
```

7. Finally, you can also use `poor-cli` directly through a [Neovim plugin](https://neovim.io/), where it provides inline ghost text completion and a chat panel similar to [Windsurf](https://windsurf.com/) or [Copilot](https://copilot.microsoft.com/). The easiest way to install this is through the [lazy.nvim](https://github.com/folke/lazy.nvim) Package Manager.

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
- ready-to-run join command examples

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

### Tunnel alternatives

You can use cloudflared, Tailscale funnel, or any reverse tunnel/provider.
Expose the host `/rpc` endpoint and pass the resulting `ws://` or `wss://` URL
to `--remote-url` / `multiplayer.url`.

## Model support

`poor-cli` supports provider/model selection via `/switch` (inside TUI) or `--provider/--model` flags. You can pass any model ID accepted by the provider SDK/API.

| Provider | Key | Default Model | Common Models | Capabilities in `poor-cli` |
|---|---|---|---|---|
| Gemini | `gemini` | `gemini-2.0-flash-exp` | `gemini-2.0-flash-exp`, `gemini-1.5-pro` | Streaming, function calling, system instructions, vision, JSON mode |
| OpenAI | `openai` | `gpt-4-turbo` | `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo` | Streaming, function calling, system instructions, JSON mode, vision on GPT-4-class models |
| Anthropic / Claude | `anthropic` (alias: `claude`) | `claude-3-5-sonnet-20241022` | `claude-sonnet-4-20250514`, `claude-3-haiku-20240307` | Streaming, function calling, system instructions, vision |
| Ollama | `ollama` | `llama3` | Auto-discovered from local `ollama` (`/api/tags`), with fallbacks `llama3`, `codellama`, `mistral`, `phi3` | Streaming, system instructions, JSON mode, optional function calling (model-dependent), local-only execution via `http://localhost:11434` |

## Architecture

![](./asset/reference/architecture.png)

## Available Commands

Type `@path/to/file` in any prompt to attach local file context.  
Use quoted refs for spaces, e.g. `@"docs/My File.md"` or `@'docs/My File.md'`.
Run `!<shell command> [| optional question]` to execute shell output and optionally ask the model about it.

**Session Management:**
- `/help` - Show help message
- `/onboarding` - Guided walkthrough (`start|next|prev|<step>|show|exit`)
- `/quit`, `/exit` - Exit and print session summary
- `/clear` - Clear current conversation
- `/clear-output` - Clear visible output
- `/history [N]` - Show recent messages (default: 10)
- `/sessions` - List recent sessions
- `/new-session` - Start fresh session
- `/status` - Show quick session + provider status
- `/export [json|md|txt]` - Export active session history
- `/retry` - Retry last request
- `/search <term>` - Search session messages
- `/edit-last` - Load previous message into input
- `/copy` - Copy last assistant response
- `/cost` - Show token/cost estimate

**Checkpoints & Undo:**
- `/checkpoints [N]` - List checkpoints
- `/checkpoint` - Create manual checkpoint
- `/save` - Quick checkpoint alias
- `/rewind [id|last]` - Restore checkpoint by ID or latest
- `/restore` - Restore latest checkpoint
- `/undo` - Restore latest checkpoint (alias)
- `/diff <file1> <file2>` - Compare two files

**Git Integration:**
- `/commit` - Generate commit message from staged diff
- `/commit --apply <message>` - Commit with explicit message
- `/commit --apply-last` - Commit with latest assistant response
- `/review [file]` - Review a file or staged diff
- `/test <file>` - Generate tests for a file
- `/explain-diff [file]` - Analyze behavior/risk from diff
- `/fix-failures [command]` - Analyze latest failure output (or run command first)

**Provider Management:**
- `/provider` - Show current provider info
- `/providers` - List all available providers and models
- `/switch` - Switch AI provider
- `/api-key` - Show or set provider API keys (`/api-key <provider> <key>`)
- `/model-info` - Show provider model notes
- `/permission-mode [prompt|auto-safe|danger-full-access]` - Show or set permission mode

**Configuration & Profiles:**
- `/config` - Show current configuration
- `/settings` - List editable config keys
- `/toggle <key>` - Toggle boolean config value
- `/set <key> <value>` - Set config value
- `/theme [dark|light]` - Show or set UI/code-block theme
- `/broke` - Set poor mode (terse output)
- `/my-treat` - Set rich mode (comprehensive output)
- `/verbose` - Toggle verbose logging
- `/plan-mode` - Toggle plan mode
- `/profile [speed|safe|deep-review]` - Execution profile control

**Prompt Library, Context & Planning:**
- `/add <path>` - Pin file/directory as persistent context
- `/drop <path>` - Unpin context file
- `/files` - List pinned context files
- `/clear-files` - Clear pinned context files
- `/save-prompt <name> <text>` - Save reusable prompt text immediately
- `/save-prompt <name>` - Capture next input as reusable prompt text
- `/use <name>` - Load and run saved prompt
- `/prompts` - List saved prompts
- `/image <path>` - Queue image for next request
- `/plan <task>` - Generate an explicit step plan for the task

**Automation, QA & Workspace Ops:**
- `/doctor` - Run environment/provider/service diagnostics
- `/bootstrap [path]` - Detect project type and suggest quickstart
- `/resume` - Snapshot of session/branch/checkpoint state
- `/focus start|status|done` - Persistent focus goal workflow
- `/tasks [list|add|done|drop|clear]` - Lightweight local task board
- `/workspace-map [path]` - File/entrypoint map of workspace
- `/context-budget [tokens]` - Rank context files by token budget
- `/autopilot start|stop|status [cap]` - Bounded autonomous loop control
- `/qa start|stop|status [dir] [command]` - Background incremental QA watch
- `/watch <dir>` - Watch directory and auto-analyze changes
- `/unwatch` - Stop watch mode

**Service & Shell Utilities:**
- `/service status [name]` - Show managed service status
- `/service start <name> [command...]` - Start managed service
- `/service stop <name>` - Stop managed service
- `/service logs <name> [lines]` - Tail managed service logs
- `/ollama start|stop|status` - Ollama lifecycle shortcuts
- `/ollama logs [lines]` - Tail Ollama logs
- `/ollama pull <model>` - Pull local Ollama model
- `/ollama list-models` - List locally installed Ollama models
- `/ollama ps` - Show running Ollama model sessions
- `/run <command>` - Run shell command via backend
- `/read <file>` - Read file via backend
- `/pwd` - Print current working directory
- `/ls [path]` - List directory contents
- `/tools` - List backend tool declarations

**Multiplayer Commands:**
- `/host-server [room]` - Start host (or room-scoped host context)
- `/host-server status|stop|share [viewer|prompter] [room]` - Host lifecycle/share payloads
- `/host-server members [room]` - List host-connected members
- `/host-server kick <connection-id> [room]` - Remove host member
- `/host-server role <id> <viewer|prompter> [room]` - Set role (`promote`/`demote` aliases)
- `/host-server lobby <on|off> [room]` - Toggle lobby approvals
- `/host-server approve|deny <id> [room]` - Resolve pending lobby requests
- `/host-server rotate-token <viewer|prompter> [room] [expiry-seconds]` - Rotate invite tokens
- `/host-server revoke <token|connection-id> [room]` - Revoke invite or member
- `/host-server handoff <id> [room]` - Transfer prompter role
- `/host-server preset <pairing|mob|review> [room]` - Apply room collaboration preset
- `/host-server activity [room] [limit] [event-type]` - Host room activity log
- `/join-server` - Interactive join wizard
- `/join-server <invite-code|ws-url room token>` - Direct join
- `/kick <connection-id> [room]` - Kick room member
- `/who [room]`, `/members [room]` - List room members
- Each TUI run writes session logs under `.poor-cli/logs/` (TUI + backend files)

**Neovim Commands:**
- `:PoorCliStart`: Start the AI server
- `:PoorCliStop`: Stop the AI server
- `:PoorCliStatus`: Show server status
- `:PoorCliChat`: Toggle chat panel
- `:PoorCliSend [message]`: Send message to chat
- `:PoorCliClear`: Clear chat history
- `:PoorCliDiagnostics`: Toggle assistant diagnostics integration
- `:PoorCliCheckpoints`: Browse + restore checkpoints (Telescope)
- `:PoorCliComplete`: Trigger inline completion
- `:PoorCliAccept`: Accept current completion
- `:PoorCliDismiss`: Dismiss current completion
- `:PoorCliSwitchProvider [provider]`: Switch provider
- `:'<,'>PoorCliExplain`: Explain selected code
- `:'<,'>PoorCliRefactor`: Refactor selected code
- `:PoorCliTest`: Generate tests for current function
- `:PoorCliDoc`: Generate docs for current function
- `:checkhealth poor-cli`: Verify your Neovim setup

## Available Tools

`poor-cli` can currently use these tools.

* *File & Workspace Tools*: `read_file`, `write_file`, `edit_file`, `list_directory`, `glob_files`, `grep_files`, `copy_file`, `move_file`, `delete_file`, `create_directory`, `diff_files`
* *Execution & Quality Tools*: `bash`, `run_tests`, `format_and_lint`, `dependency_inspect`, `process_logs`
* *Git Tools*: `git_status`, `git_diff`, `git_status_diff`, `apply_patch_unified`
* *Network/Data Tools*: `fetch_url`, `web_search`, `json_yaml_edit`
* *Optional GitHub Tools* *(available when `gh` CLI is installed)*: `gh_pr_list`, `gh_pr_view`, `gh_pr_create`, `gh_pr_comment`, `gh_issue_list`, `gh_issue_view`
