# Quickstart

Goal: install the package, start the minimal chat harness, run one non-interactive CI-style task, and inspect provider/cost state.

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

## 1:00 - Chat

```sh
poor-cli chat --provider anthropic
```

Inside chat:

```text
you> /help
you> summarize this repository in five bullets
you> /quit
```

The chat surface is intentionally plain: one prompt, streamed assistant text, terse tool events, no editor dependency.

## 2:00 - CI-style run

```sh
poor-cli exec --provider anthropic --prompt "review the current diff and run focused tests"
```

Use `exec` for CI jobs, pre-merge checks, release checks, and scripted agent runs.

## 3:00 - Inspect state

```sh
poor-cli diag doctor
poor-cli install info
poor-cli help
```

Repo-local runtime state lives under `.poor-cli/`.

## Next

- [COMMANDS.md](./COMMANDS.md) - slash command reference.
- [SANDBOX.md](./SANDBOX.md) - permissions and CI guardrails.
- [PROVIDERS.md](./PROVIDERS.md) - provider setup.
- [MCP.md](./MCP.md) - external tool servers.
