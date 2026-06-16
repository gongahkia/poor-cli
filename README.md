# poor-cli

`poor-cli` v6 is a verifiable run-record for coding agents.

It captures what an agent was asked, what context and route it got, what it did, and what changed into a content-addressed store that can be replayed offline.

## Status

`6.0.0a1` is an alpha rewrite. The v5 codebase is preserved under `legacy/`.

Current product direction and task list: [`TODO.md`](TODO.md).

## Install

```sh
python3 -m pip install -e ".[dev]"
poor-cli --version
```

## Commands

```sh
poor-cli agents
poor-cli doctor
poor-cli plan "inspect this repo and propose a task graph"
poor-cli plan "trace the parser flow" --graph
poor-cli run "make a small scoped change" --yes
poor-cli run "fix the caller lookup" --graph --yes
poor-cli run-swarm "split independent fixes" --parallel 2
poor-cli runs
poor-cli runs diff <run_a> <run_b> --fail-on-change
poor-cli runs fork <run_id>
poor-cli shims install
poor-cli shims doctor
poor-cli shims uninstall
poor-cli inspect <run_id> --events --context
poor-cli inspect <run_id> --artifacts --cost
poor-cli review-run <run_id>
poor-cli verify-run <run_id>
poor-cli replay <run_id> --verify
poor-cli provider add openai --model gpt-5.5
poor-cli provider list
poor-cli route explain "fix the parser"
poor-cli cleanup <run_id>
poor-cli cleanup-swarm <run_id>
poor-cli mcp list
poor-cli mcp call server:tool --args '{"text":"hello"}'
poor-cli rpc serve --stdio
poor-cli tui --run-id <run_id>
```

`poor-cli run` records the plan first. Without `--yes` or `--dry-run`, it requires confirmation before invoking write-capable agents.

The TUI is a debug/audit surface for surprising runs, route state, artifacts, replay, `open PLAN.md`, `diff recent`, and quick dry-run commands. Daily capture stays on the normal `claude`/`codex` shim and CLI replay path.

## Planner

Planning is LLM-backed. By default `poor-cli` uses `claude` if installed, then `codex`. For tests or custom planners, set:

```sh
export POOR_CLI_PLANNER_COMMAND="python path/to/planner.py"
```

The command receives the planner prompt on stdin and must print JSON with a `tasks` array.

## Storage

Run state lives in `.poor-cli/v6/`:

- `runs.sqlite3`: runs, tasks, events, agents, artifact refs
- `cas/`: content-addressed artifacts for prompts, plans, context packets, and agent results
- `runs/<run_id>/artifacts/`: deterministic `PLAN.md`, worker `RESULT.md`, `PATCH.diff`, review, and verifier artifacts

The on-disk record schema is documented in [`docs/record-schema.md`](docs/record-schema.md).

## Differentiation

Per-task routing and local replay are existing categories, not novel claims. [Claude Code Router](https://github.com/musistudio/claude-code-router) demonstrates the router/proxy front door; [agent-replay](https://github.com/clay-good/agent-replay), [cagent session recording](https://www.docker.com/blog/deterministic-ai-testing-with-session-recording-in-cagent/), and [Agent VCR](https://github.com/Jarvis2021/agent-vcr) demonstrate local replay, cassettes, and recording diffs.

`poor-cli` is scoped around the vertical record: route decision, context packet, plan/DAG, agent I/O, artifacts, and benchmark evidence in one content-addressed store that can be checked offline.

## Providers

Provider profiles are stored in config using secret references, not plaintext keys. Built-in presets cover OpenAI, OpenAI-compatible endpoints, OpenRouter, Kimi, Ollama, vLLM, and SGLang.

Local or configured providers can run through the native provider-backed tool loop. Shell runners for Codex, Claude, and generic commands remain supported.

## Gates

The v6 gate set is tests, ruff, strict mypy, docs build, replay determinism, packaging, and the source LOC cap.

## Goal

The first milestone is not a full multi-agent framework. It is a small runtime that answers:

> What happened, why did it happen, what did the agent see, and can I replay the orchestration state?
