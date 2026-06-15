# poor-cli

`poor-cli` v6 is a deterministic orchestration runtime for AI software work.

It sits above local coding agents such as Claude Code, Codex, and shell-based tools. Given a software goal, it records a structured plan, detected agents, task state, context packets, agent inputs/outputs, artifacts, and replayable orchestration events.

## Status

`6.0.0a1` is an alpha rewrite. The v5 codebase is preserved under `legacy/`.

Current roadmap: [`WORKON-PIVOT-ASAP.md`](WORKON-PIVOT-ASAP.md).

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
poor-cli runs
poor-cli inspect <run_id> --events --context
poor-cli inspect <run_id> --artifacts --cost
poor-cli review-run <run_id>
poor-cli verify-run <run_id>
poor-cli replay <run_id>
poor-cli provider add openai --model gpt-5.5
poor-cli provider list
poor-cli route explain "fix the parser"
poor-cli cleanup <run_id>
poor-cli mcp list
poor-cli mcp call server:tool --args '{"text":"hello"}'
poor-cli tui --run-id <run_id>
```

`poor-cli run` records the plan first. Without `--yes` or `--dry-run`, it requires confirmation before invoking write-capable agents.

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

## Providers

Provider profiles are stored in config using secret references, not plaintext keys. Built-in presets cover OpenAI, OpenAI-compatible endpoints, OpenRouter, Kimi, Ollama, vLLM, and SGLang.

Local or configured providers can run through the native provider-backed tool loop. Shell runners for Codex, Claude, and generic commands remain supported.

## Gates

The v6 gate set is tests, ruff, strict mypy, docs build, replay determinism, packaging, and the 6500-line source LOC cap.

## Goal

The first milestone is not a full multi-agent framework. It is a small runtime that answers:

> What happened, why did it happen, what did the agent see, and can I replay the orchestration state?
