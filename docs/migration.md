# Migration Notes

## v6.0 Alpha Compatibility

Existing CLI flows remain supported:

- `poor-cli agents`
- `poor-cli plan`
- `poor-cli run`
- `poor-cli runs`
- `poor-cli inspect`
- `poor-cli replay`
- `poor-cli provider`
- `poor-cli route`
- `poor-cli mcp`
- `poor-cli tui`

Provider profiles are additive. Existing environment-driven local provider usage still works through `POOR_CLI_PROVIDER`, `POOR_CLI_MODEL`, and `POOR_CLI_LOCAL_BASE_URL`.

The native provider runner adds tool-loop support for configured providers without replacing shell runners. Codex, Claude, and generic shell adapters keep their existing command paths.

Run artifacts now include deterministic files under `.poor-cli/v6/runs/<run_id>/artifacts/`; existing CAS and SQLite artifact records remain the replay source of truth.

## LOC Gate

The source LOC cap is 6500 lines. This keeps v6 compact while allowing provider profiles, native runner, artifacts, shell hardening, graph fallback, real scheduling, swarm, and RPC code to coexist without deleting useful safety checks.
