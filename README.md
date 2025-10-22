[![](https://img.shields.io/badge/poor_cli_1.0.0-passing-green)](https://github.com/gongahkia/poor-cli/releases/tag/1.0.0)

# `poor-cli`

Agentic Coding CLI Helper similar powered by Gemini's free API and capable of general-purpose tasks.

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

## Installation

### Quick Install (Recommended)

1. Clone and navigate to the repository:
```console
$ git clone https://github.com/gongahkia/poor-cli && cd poor-cli
```

2. Get your free API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

3. Set the API key as an environment variable:
```console
$ export GEMINI_API_KEY="your-api-key-here"
```

Or add it to your `~/.bashrc` or `~/.zshrc` for permanent setup:
```bash
export GEMINI_API_KEY="your-api-key-here"
```

4. Run the installation script:
```console
$ chmod +x install.sh
$ ./install.sh
```

5. **Use poor-cli from anywhere!**
```console
$ cd ~/any/directory
$ poor-cli
```

### Manual Installation

If you prefer manual installation:

```console
$ git clone https://github.com/gongahkia/poor-cli && cd poor-cli
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -e .
```

Then set your `GEMINI_API_KEY` environment variable and run:
```console
$ poor-cli
```

### Uninstallation

To uninstall poor-cli:
```console
$ ./uninstall.sh
```

Or manually:
```console
$ pip uninstall poor-cli
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
