# poor-cli

`poor-cli` v6 is a deterministic orchestration runtime for AI software work.

It sits above local coding agents such as Claude Code, Codex, and shell-based tools. Given a software goal, it records a structured plan, detected agents, task state, context packets, agent inputs/outputs, artifacts, and replayable orchestration events.

## Status

`6.0.0a1` is an alpha rewrite. The v5 codebase is preserved under `legacy/`.

## Install

```sh
python3 -m pip install -e ".[dev]"
poor-cli --version
```

## Commands

```sh
poor-cli agents
poor-cli plan "inspect this repo and propose a task graph"
poor-cli run "make a small scoped change" --yes
poor-cli runs
poor-cli inspect <run_id> --events --context
poor-cli replay <run_id>
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

## Goal

The first milestone is not a full multi-agent framework. It is a small runtime that answers:

> What happened, why did it happen, what did the agent see, and can I replay the orchestration state?
