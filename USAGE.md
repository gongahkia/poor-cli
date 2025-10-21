# poor-cli Usage Guide

## Quick Start

1. **Set up your API key**:
```bash
cp .env.example .env
# Edit .env and add your Gemini API key
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Run the CLI**:
```bash
./run.sh
# or
python -m poor_cli
```

## Example Interactions

### General Questions

```
You: What is the capital of France?
Assistant: The capital of France is Paris.
```

### File Operations

```
You: Create a new Python file called hello.py with a simple hello world program

→ Calling tool: write_file
[Tool Output: Successfully wrote to hello.py]