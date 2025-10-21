# poor-cli

A CLI tool similar to Claude Code but powered by Gemini's free API and capable of general-purpose tasks.

## Features

- **Interactive REPL**: Conversational AI interface powered by Gemini
- **File Operations**: Read, write, and edit files with AI assistance
- **Code Search**: Glob and grep functionality for finding files and searching code
- **Bash Execution**: Run shell commands directly from the AI
- **Rich Terminal UI**: Beautiful markdown rendering and syntax highlighting

## Installation

1. Clone this repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set your Gemini API key as an environment variable:

```bash
export GEMINI_API_KEY="your-api-key-here"
```

Get a free API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

## Usage

Run the REPL:

```bash
python -m poor_cli
```

Or install and use as a command:

```bash
pip install -e .
poor-cli
```

## Available Commands

- `/help` - Show help message
- `/quit` - Exit the REPL
- `/clear` - Clear conversation history

## Available Tools

The AI can use these tools automatically:

- **read_file**: Read file contents with optional line ranges
- **write_file**: Create or overwrite files
- **edit_file**: Edit files using string replacement or line-based editing
- **glob_files**: Find files matching patterns (e.g., `**/*.py`)
- **grep_files**: Search for text in files using regex
- **bash**: Execute bash commands with timeout support

## Example Usage

### Answer General Questions
```
You: What is the time complexity of quicksort?
Assistant: Quicksort has an average time complexity of O(n log n)...
```

### File Operations
```
You: Create a Python file that implements a binary search algorithm

→ Calling tool: write_file
Assistant: I've created binary_search.py with the implementation.
```

### Code Analysis
```
You: Find all Python files in this directory

→ Calling tool: glob_files
[Shows list of .py files]
```

### Search Code
```
You: Search for all TODO comments in my Python files

→ Calling tool: grep_files
[Shows matching lines with file:line_number format]
```

### Run Commands
```
You: Run the tests using pytest

→ Calling tool: bash
[Shows test output]
```

## Project Structure

```
poor-cli/
├── poor_cli/
│   ├── __init__.py
│   ├── __main__.py
│   ├── gemini_client.py  # Gemini API wrapper
│   ├── repl.py            # Main REPL interface
│   └── tools.py           # Tool implementations
├── README.md
├── requirements.txt
├── setup.py
└── run.sh                 # Quick start script
```

## Development

To contribute or modify:

1. Fork the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate`
4. Install in development mode: `pip install -e .`
5. Make your changes
6. Test thoroughly

## License

MIT

## Acknowledgments

Inspired by Claude Code, powered by Google's Gemini API.
