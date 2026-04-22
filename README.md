# poor-cli

CI-focused CLI agent harness for code work. The product surface is a small terminal chat loop, a non-interactive `exec` path for automation, and a JSON-RPC server for harness integrations.

## Install

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli --version
```

Supported Python versions: `3.11`, `3.12`, `3.13`, `3.14`.

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
