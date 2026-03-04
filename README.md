[![](https://img.shields.io/badge/poor_cli_1.0.0-passing-90EE90)](https://github.com/gongahkia/poor-cli/releases/tag/1.0.0)
[![](https://img.shields.io/badge/poor_cli_2.0.0-passing-97CA00)](https://github.com/gongahkia/poor-cli/releases/tag/2.0.0)
[![](https://img.shields.io/badge/poor_cli_3.0.0-passing-6BA82E)](https://github.com/gongahkia/poor-cli/releases/tag/3.0.0)
![](https://github.com/gongahkia/poor-cli/actions/workflows/tests.yml/badge.svg)

# `poor-cli`

[BYOK](https://en.wikipedia.org/wiki/Bring_your_own_encryption) Agentic Coding Helper *(for the poor man)* that lives in your Terminal *(now also available in **[Neovim](https://neovim.io/)**)*.

```text
 ____   ___   ___  ____        ____ _     ___
|  _ \ / _ \ / _ \|  _ \      / ___| |   |_ _|
| |_) | | | | | | | |_) |    | |   | |    | |
|  __/| |_| | |_| |  _ <     | |___| |___ | |
|_|    \___/ \___/|_| \_\     \____|_____|___|
```

## Stack

* *Script*: [Python](https://www.python.org/), [Lua](https://www.lua.org/), [Vim Script](https://vimhelp.org/usr_41.txt.html) 
* *Core Dependencies*: [google-generativeai](https://pypi.org/project/google-generativeai/), [rich](https://pypi.org/project/rich/), [PyYAML](https://pypi.org/project/PyYAML/), [aiofiles](https://pypi.org/project/aiofiles/), [aiohttp](https://pypi.org/project/aiohttp/), [cryptography](https://pypi.org/project/cryptography/), [prompt_toolkit](https://pypi.org/project/prompt_toolkit/)
* *Optional Provider Dependencies*: [openai](https://pypi.org/project/openai/), [anthropic](https://pypi.org/project/anthropic/)
* *Development Tools*: [black](https://black.readthedocs.io/), [ruff](https://docs.astral.sh/ruff/), [mypy](https://mypy.readthedocs.io/), [pytest](https://docs.pytest.org/)
* *Infrastructure*: [SQLite 3](https://www.sqlite.org/), [Docker](https://www.docker.com/), [GitHub Actions](https://github.com/features/actions)

## Usage

The below instructions are for locally hosting `poor-cli`. See screenshots [here](#screenshots).

1. First run the below

```console
$ git clone && cd poor-cli
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and configure your preferred LLM providers by setting your API keys in `.env`. `poor-cli` supports [Gemini](https://aistudio.google.com/) *(free tier)*, [OpenAI](https://platform.openai.com/docs/models), [Anthropic](https://docs.claude.com/en/docs/about-claude/models/overview) and [Ollama](https://ollama.com/) *(local)*.

```console
$ cp .env.example .env
```

3. Now run the below to use the `poor-cli` CLI client.

```console
$ ./run.sh
$ ./run_tui.sh
$ python -m poor_cli         # wrapper that launches the Rust TUI
$ pip install -e .
$ poor-cli                   # wrapper that launches the Rust TUI
$ ./uninstall.sh
```

4. Alternatively, install via [pip](https://pypi.org/project/pip/) for system-wide access.

```console
$ pip install poor-cli
```

5. You can also run `poor-cli` with [Docker](https://www.docker.com/).

```console
$ docker build -t poor-cli .
$ docker run -it --env-file .env poor-cli
```

6. Finally, you can also use `poor-cli` directly through a [Neovim plugin](https://neovim.io/), where it provides inline ghost text completion and a chat panel similar to [Windsurf](https://windsurf.com/) or [Copilot](https://copilot.microsoft.com/). The easiest way to install this is through the [lazy.nvim](https://github.com/folke/lazy.nvim) Package Manager.

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

## Available Commands

**Session Management:**
- `/help` - Show help message
- `/quit` - Exit and print session summary
- `/clear` - Clear current conversation
- `/clear-output` - Clear visible output
- `/history [N]` - Show recent messages (default: 10)
- `/new-session` - Start fresh session
- `/retry` - Retry last request
- `/search <term>` - Search session messages
- `/edit-last` - Load previous message into input

**Git Integration:**
- `/commit` - Generate commit message from staged diff
- `/review [file]` - Review a file or staged diff
- `/test <file>` - Generate tests for a file

**Provider Management:**
- `/provider` - Show current provider info
- `/providers` - List all available providers and models
- `/switch` - Switch AI provider
- `/model-info` - Show provider model notes

**Prompt Library & Watch:**
- `/save-prompt <name> <text>` - Save reusable prompt
- `/use <name>` - Load and run saved prompt
- `/prompts` - List saved prompts
- `/watch <dir>` - Watch directory and auto-analyze changes
- `/unwatch` - Stop watch mode

**Configuration:**
- `/config` - Show current configuration
- `/permission-mode` - Show active permission mode
- `/broke` - Set poor mode (terse, token-minimal responses; session-only)
- `/my-treat` - Set rich mode (comprehensive responses; session-only, default)
- `/cost` - Show token/cost estimate
- `/tools` - List backend tool declarations
- `/image <path>` - Queue image path for next request

**Neovim Commands:**
- `:PoorCliStart`: Start the AI server
- `:PoorCliStop`: Stop the AI server
- `:PoorCliStatus`: Show server status
- `:PoorCliChat`: Toggle chat panel
- `:PoorCliComplete`: Trigger inline completion
- `:'<,'>PoorCliExplain`: Explain selected code
- `:'<,'>PoorCliRefactor`: Refactor selected code
- `:checkhealth poor-cli`: Verify your Neovim setup

## Available Tools

`poor-cli` can currently use these tools.

- read_file: Read file contents with optional line ranges
- write_file: Create or overwrite files
- edit_file: Edit files using string replacement or line-based editing
- glob_files: Find files matching patterns (e.g., `**/*.py`)
- grep_files: Search for text in files using regex
- bash: Execute bash commands with timeout support
- run_tests: Run project tests and report structured failures
- git_status_diff: Summarize git status, diff stats, and risk hints
- apply_patch_unified: Validate/apply unified diff patches via `git apply`
- format_and_lint: Run available formatters/linters (`black`, `ruff`, `mypy`)
- dependency_inspect: Inspect declared, installed, and outdated dependencies
- fetch_url: Fetch and summarize URL content with SSRF safeguards
- json_yaml_edit: Edit JSON/YAML using dotted-path updates
- process_logs: Parse logs into level counts and likely root cause

## Architecture

```mermaid
flowchart TB
    subgraph Clients["Client Interfaces"]
        CLI["Rust TUI<br/>(poor-cli-tui)"]
        NVIM["Neovim Plugin<br/>(Lua)"]
        EXT["Other Editors<br/>(VSCode, etc.)"]
    end

    subgraph Server["JSON-RPC Server"]
        RPC["server.py<br/>JSON-RPC 2.0"]
    end

    subgraph Core["Core Engine"]
        ENGINE["PoorCLICore<br/>(core.py)"]
        CTX["Context Manager<br/>(context.py)"]
        PROMPTS["Prompt Templates<br/>(prompts.py)"]
    end

    subgraph Providers["AI Providers"]
        FACTORY["Provider Factory<br/>(provider_factory.py)"]
        GEMINI["Gemini Provider<br/>(free tier)"]
        OPENAI["OpenAI Provider<br/>(GPT-4)"]
        CLAUDE["Anthropic Provider<br/>(Claude)"]
        OLLAMA["Ollama Provider<br/>(local)"]
    end

    subgraph Tools["Tool System"]
        REGISTRY["Tool Registry<br/>(tools_async.py)"]
        READ["read_file"]
        WRITE["write_file"]
        EDIT["edit_file"]
        GLOB["glob_files"]
        GREP["grep_files"]
        BASH["bash"]
    end

    subgraph Safety["Safety & Versioning"]
        CHECKPOINT["Checkpoint System<br/>(checkpoint.py)"]
        PLAN["Plan Mode<br/>(plan_mode.py)"]
        AUDIT["Audit Logger<br/>(audit_log.py)"]
        VALIDATE["Command Validator<br/>(command_validator.py)"]
    end

    subgraph Storage["Data Storage (SQLite)"]
        HISTORY["History DB<br/>~/.poor-cli/history.db"]
        CACHE["File Cache<br/>~/.poor-cli/cache/"]
        AUDITDB["Audit Log<br/>~/.poor-cli/audit/"]
        CHECKDB["Checkpoints<br/>~/.poor-cli/checkpoints/"]
    end

    subgraph Config["Configuration"]
        YAML["config.yaml"]
        ENV[".env<br/>(API Keys)"]
    end

    CLI --> RPC
    NVIM --> RPC
    EXT --> RPC
    RPC --> ENGINE

    ENGINE --> CTX
    ENGINE --> PROMPTS
    ENGINE --> FACTORY
    ENGINE --> REGISTRY

    FACTORY --> GEMINI
    FACTORY --> OPENAI
    FACTORY --> CLAUDE
    FACTORY --> OLLAMA

    REGISTRY --> READ
    REGISTRY --> WRITE
    REGISTRY --> EDIT
    REGISTRY --> GLOB
    REGISTRY --> GREP
    REGISTRY --> BASH

    WRITE --> CHECKPOINT
    EDIT --> CHECKPOINT
    BASH --> VALIDATE

    ENGINE --> PLAN
    PLAN --> AUDIT
    CHECKPOINT --> CHECKDB

    ENGINE --> HISTORY
    CTX --> CACHE
    AUDIT --> AUDITDB

    ENGINE --> YAML
    FACTORY --> ENV
```

## Screenshots

![](./asset/reference/1.png)
![](./asset/reference/2.png)
![](./asset/reference/3.png)
![](./asset/reference/6.png)
![](./asset/reference/4.png)
![](./asset/reference/5.png)
