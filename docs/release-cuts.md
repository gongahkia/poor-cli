# Release Cuts

## v6.1

Provider profiles, route schema, provider-backed runner skeleton, and doctor tests.

## v6.2

Parallel DAG scheduling, worktree swarm, artifacts, and cleanup.

## v6.3

Fusion, Kimi, web tools, review/verifier lanes, and benchmark reports.

## v6.4

RPC, MCP hosting, TUI panels, and prompt-pack workflow.

## Stop Gate

Stop release work if provenance, security, budget, replay, packaging, or claim gates fail. Use:

```sh
python bench/release_gate.py
```
