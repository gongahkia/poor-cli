[![](https://img.shields.io/badge/poor_cli_1.0.0-passing-green)](https://github.com/gongahkia/poor-cli/releases/tag/1.0.0)

# `poor-cli`

[BYOK](https://en.wikipedia.org/wiki/Bring_your_own_encryption) Agentic Coding Helper that lives in your Terminal.

<div align="center">
    <img src="./asset/logo/1.png" width="35%">
</div>

## Stack

...

## Screenshots

<div align="centre">
    <img src="" width="32%">
    <img src="" width="32%">
    <img src="" width="32%">
</div>

<div align="centre">
    <img src="" width="32%">
    <img src="" width="32%">
    <img src="" width="32%">
</div>

## Usage

The below instructions are for locally hosting `poor-cli`.

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

3. Now run the below

```console
$ ./run.sh
$ python -m poor_cli
$ pip install -e .
$ poor-cli
$ ./uninstall.sh
```

## Available Commands

**Session Management:**
- `/help` - Show help message
- `/quit` - Exit the REPL
- `/clear` - Clear current conversation
- `/history [N]` - Show recent messages (default: 10)
- `/sessions` - List all previous sessions
- `/new-session` - Start fresh session

**Checkpoints & Undo:**
- `/checkpoints` - List all checkpoints
- `/checkpoint` - Create manual checkpoint
- `/rewind [ID]` - Restore checkpoint (ID or 'last')
- `/diff <f1> <f2>` - Compare two files

**Provider Management:**
- `/provider` - Show current provider info
- `/providers` - List all available providers and models
- `/switch` - Switch AI provider

**Export & Archive:**
- `/export [format]` - Export conversation (json, md, txt)

**Configuration:**
- `/config` - Show current configuration
- `/verbose` - Toggle verbose logging
- `/plan-mode` - Toggle plan mode

## Available Tools

`poor-cli` can currently use these tools.

- read_file: Read file contents with optional line ranges
- write_file: Create or overwrite files
- edit_file: Edit files using string replacement or line-based editing
- glob_files: Find files matching patterns (e.g., `**/*.py`)
- grep_files: Search for text in files using regex
- bash: Execute bash commands with timeout support
