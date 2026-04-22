# Quickstart

Goal: install the package, run one non-interactive CI-style task, start the JSON-RPC backend, and inspect provider/cost state.

## 0:00 - Install

```sh
python3 -m pip install --upgrade 'poor-cli[all]'
poor-cli --version
```

## 0:30 - Configure a provider

```sh
export ANTHROPIC_API_KEY="..."
# or OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY
```

Check provider state:

```sh
poor-cli provider list
poor-cli provider info anthropic
```

## 1:00 - CI-style run

```sh
poor-cli exec --provider anthropic --prompt "review the current diff and run focused tests"
```

Use `exec` for CI jobs, pre-merge checks, release checks, and scripted agent runs.

## 2:00 - Start backend for clients

```sh
poor-cli server --stdio
```

Use the JSON-RPC server for native apps, editor integrations, and automation clients.

## 3:00 - Inspect state

```sh
poor-cli diag doctor
poor-cli install info
poor-cli help
```

Repo-local runtime state lives under `.poor-cli/`.

## Next

- [COMMANDS.md](./COMMANDS.md) - legacy command manifest and workflow aliases.
- [SANDBOX.md](./SANDBOX.md) - permissions and CI guardrails.
- [PROVIDERS.md](./PROVIDERS.md) - provider setup.
- [MCP.md](./MCP.md) - external tool servers.
