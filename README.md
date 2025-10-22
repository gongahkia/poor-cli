[![](https://img.shields.io/badge/poor_cli_1.0.0-passing-green)](https://github.com/gongahkia/poor-cli/releases/tag/1.0.0)

# `poor-cli`

A CLI tool similar to Claude Code but powered by Gemini's free API and capable of general-purpose tasks.

<div align="center">
    <img src="./asset/logo/1.png" width="35%">
</div>

## Features

- **Interactive REPL**: Conversational AI interface powered by Gemini
- **File Operations**: Read, write, and edit files with AI assistance
- **Code Search**: Glob and grep functionality for finding files and searching code
- **Bash Execution**: Run shell commands directly from the AI
- **Rich Terminal UI**: Beautiful markdown rendering and syntax highlighting

## Stack

...

## Usage

The below instructions are for locally hosting `poor-cli`.

1. First run the below.

```console
$ git clone && cd poor-cli
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -r requirements.txt
```

2. Get your free API key from [Google AI Studio](https://makersuite.google.com/app/apikey) and 
3. Set the below values within `.env`.

```env
GEMINI_API_KEY="your-api-key-here"
```

4. Now run the below.

```console
$ python -m poor_cli
$ pip install -e .
$ poor-cli
```

## Available Commands

- `/help` - Show help message
- `/quit` - Exit the REPL
- `/clear` - Clear conversation history

## Available Tools

`poor-cli` can currently use these tools.

- **read_file**: Read file contents with optional line ranges
- **write_file**: Create or overwrite files
- **edit_file**: Edit files using string replacement or line-based editing
- **glob_files**: Find files matching patterns (e.g., `**/*.py`)
- **grep_files**: Search for text in files using regex
- **bash**: Execute bash commands with timeout support
