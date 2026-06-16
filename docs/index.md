# Quickstart

`poor-cli` v6 is an alpha Python runtime for verifiable coding-agent run records.

It captures the prompt, route decision, context packet, plan, agent I/O, artifacts, and replay metadata into an on-disk store that can be verified offline.

## Install

```sh
python3 -m pip install -e ".[dev]"
poor-cli --version
```

## Run

```sh
poor-cli agents
poor-cli plan "inspect this repo and propose a task graph"
poor-cli plan "trace the parser flow" --graph
poor-cli run "make a small scoped change" --yes
poor-cli run "fix the caller lookup" --graph --yes
poor-cli runs
poor-cli shims install
poor-cli inspect <run_id> --events --context
poor-cli replay <run_id> --verify
```

Without `--yes` or `--dry-run`, `poor-cli run` records a plan and then stops for confirmation before invoking write-capable agents.

## Planner

Planning is LLM-backed by default. For deterministic tests or custom planning, set:

```sh
export POOR_CLI_PLANNER_COMMAND="python path/to/planner.py"
```

The command receives the planner prompt on stdin and must print JSON with a `tasks` array.

## Offline Replay

```sh
poor-cli --offline replay <run_id> --verify
```

Offline mode sets `POOR_CLI_OFFLINE=1` and blocks live network-backed provider or agent calls.
