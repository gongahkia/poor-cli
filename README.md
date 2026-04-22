# poor-cli

[![](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/gongahkia/poor-cli/actions/workflows/tests.yml)
[![](https://img.shields.io/badge/poor-cli_5.0.0-blue)](https://github.com/gongahkia/poor-cli)

CI-focused CLI agent harness for code work. The product surface is a small terminal chat loop, a non-interactive `exec` path for automation, and a JSON-RPC server for harness integrations.

## Install

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli --version
```

Supported Python versions are `3.11`, `3.12`, `3.13`, and `3.14`.

## Quickstart

```sh
export ANTHROPIC_API_KEY="..."
poor-cli chat
```

Minimal CI path:

```sh
poor-cli exec --prompt "inspect this repo and run focused tests"
```

Useful commands:

```sh
poor-cli help
poor-cli provider list
poor-cli install info
poor-cli diag doctor
poor-cli chat --provider anthropic
```

## Product Surface

- `poor-cli chat`: minimal interactive harness with `you>` prompts, streamed assistant text, and slash-style control commands.
- `poor-cli exec`: one-shot agent run for CI, scripts, and review gates.
- `poor-cli-server`: JSON-RPC runtime for automation clients.
- Tools: filesystem, shell, git, diagnostics, tasks, review, deploy, MCP, memory, checkpoints.
- State: repo-local `.poor-cli/` for config, sessions, checkpoints, audit logs, memories, and automation history.

## Providers

Provider keys: `gemini`, `openai`, `anthropic`, `claude`, `openrouter`, `ollama`, `hf_local`, `vllm`, `llama_server`, `sglang`, `hf_tgi`, `lmstudio`, `litellm`.

Local-first providers work through Ollama, LM Studio, llama-server, vLLM, SGLang, HF TGI, or HF Local. Cloud providers use BYOK environment variables or keyring-backed config.

| Provider | Key | Default Model | Common Models | Capabilities in `poor-cli` |
|---|---|---|---|---|
| Gemini | `gemini` | `gemini-2.5-flash` | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite` | Streaming, function calling, system instructions, vision, JSON mode |
| OpenAI | `openai` | `gpt-5.1` | `gpt-5.1`, `gpt-5`, `gpt-5-mini` | Streaming, function calling, system instructions, JSON mode, vision on GPT-5/GPT-4.1-class models |
| Anthropic / Claude | `anthropic` (alias: `claude`) | `claude-sonnet-4-20250514` | `claude-sonnet-4-20250514`, `claude-3-7-sonnet-20250219`, `claude-3-5-haiku-20241022` | Streaming, function calling, system instructions, vision |
| OpenRouter | `openrouter` | `anthropic/claude-sonnet-4-20250514` | `openai/gpt-5`, `anthropic/claude-sonnet-4-20250514`, `google/gemini-2.5-flash`, `meta-llama/llama-4-maverick`, `deepseek/deepseek-r1` | Streaming, function calling, system instructions, vision (model-dependent) |
| Ollama | `ollama` | `llama3.1` | Auto-discovered from local `ollama` (`/api/tags`), with fallbacks `llama3.1`, `qwen2.5-coder`, `llama3.1:70b`, `mistral`, `codellama` | Streaming, system instructions, JSON mode, optional function calling for capable local models, local-only execution via `http://localhost:11434` |
| HF Local | `hf_local` | `Qwen/Qwen2.5-3B` | Local HuggingFace model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `Qwen/Qwen2.5-14B`, `meta-llama/Llama-3.2-3B` | System instructions, latent communication via local hidden-state access |
| vLLM | `vllm` | `Qwen/Qwen2.5-3B` | Served local model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `Qwen/Qwen2.5-14B`, `meta-llama/Llama-3.2-3B` | Streaming, system instructions over vLLM's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:8000/v1` |
| llama-server | `llama_server` | `local-model` | Served local model IDs such as `local-model`, `qwen2.5-coder`, `llama-3.2` | Streaming, system instructions over llama-server's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:8080/v1` |
| SGLang | `sglang` | `Qwen/Qwen2.5-3B` | Served local model IDs such as `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B`, `Qwen/Qwen2.5-14B`, `meta-llama/Llama-3.2-3B` | Streaming, system instructions over SGLang's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:30000/v1` |
| HF TGI | `hf_tgi` | `tgi` | Served local model IDs such as `tgi`, `Qwen/Qwen2.5-3B`, `Qwen/Qwen2.5-7B` | Streaming, system instructions over TGI's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:3000/v1` |
| LM Studio | `lmstudio` | `local-model` | Served local model IDs such as `local-model`, `qwen2.5-coder`, `llama-3.2` | Streaming, system instructions over LM Studio's OpenAI-compatible local server; no latent hidden-state hand-off, local-only execution via `http://localhost:1234/v1` |
| LiteLLM (any backend) | `litellm` | `groq/llama-3.1-70b-versatile` | `groq/llama-3.1-70b-versatile`, `groq/llama-3.1-8b-instant`, `cohere/command-r-plus`, `mistral/mistral-large-latest`, `bedrock/anthropic.claude-3-sonnet-20240229-v1:0` | Catch-all router to 100+ backends via litellm; feature parity varies by underlying backend |

## CI Usage

```sh
poor-cli exec \
  --provider anthropic \
  --prompt "review the diff, run targeted tests, and report blockers only"
```

Recommended CI defaults:

```yaml
agentic:
  auto_approve_tools: ["read_file", "glob_files", "grep_files", "git_status", "git_diff"]
  deny_patterns: ["rm -rf", "force-push", "drop database"]
sandbox:
  preset: moderate
```

## Documentation

- [Quickstart](./docs/QUICKSTART.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [Features](./docs/FEATURES.md)
- [Slash commands](./docs/COMMANDS.md)
- [Providers](./docs/PROVIDERS.md)
- [MCP](./docs/MCP.md)
- [Sandbox](./docs/SANDBOX.md)
- [Automations](./docs/AUTOMATIONS.md)
- [Economy](./docs/ECONOMY.md)
- [Troubleshooting](./docs/TROUBLESHOOTING.md)

## License

MIT
