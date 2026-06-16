# Shim Capture

`poor-cli shims install` creates opt-in PATH wrappers for `claude` and `codex` under `~/.poor-cli/shims/`.

```sh
poor-cli shims install
export PATH="$HOME/.poor-cli/shims:$PATH"
poor-cli shims doctor
```

The installer writes only managed wrapper files. It refuses to overwrite unmanaged `claude` or `codex` files, and `doctor` resolves the next real binary outside the shim directory to catch recursion.

## Captured Forms

Captured v1 forms:

- `claude -p "prompt"` and `claude --print "prompt"`
- `cat file | claude -p "question"`
- `codex exec "prompt"`
- `claude "prompt"` as invocation-only capture when the installed Claude binary accepts prompt-as-arg

Bare interactive `claude` or `codex` calls pass through unchanged. Unsupported subcommands also pass through.

Captured runs write normal run records with `shim.capture`, `shim.invoked`, and `shim.completed` entries, then `poor-cli replay <run_id> --verify` can verify the record offline. Noninteractive captures also write `shim.result` with stdout, stderr, and exit code.

## Route Preflight

Every captured shim run writes a `route.decision` artifact and a `route.preflight` artifact. The preflight input is command name, argv, stdin mode, cwd, and safe environment-derived flags. The output records classifier labels, selected route, intervention reason, and the exact pass-through command.

```sh
poor-cli route explain --shim-agent codex --shim-arg exec --shim-arg "fix tests" --json
poor-cli route explain --shim-agent claude --shim-arg -p --shim-arg "review patch"
```

Classifier labels and route names are heuristic. They are recorded for audit/replay and policy decisions; they are not learned model predictions.

Visible interruption is intentionally narrow. The shim asks for TTY confirmation on high-risk write tasks and interrupts non-TTY high-risk runs before invoking the real agent. It also interrupts route fallback, missing required provider/config, or offline mode blocking a network-backed route. High-risk prompts can be allowed explicitly per repo:

```toml
[shims]
allow_high_risk = true
```

## Mechanism Decision

v1 uses a PATH shim because it is explicit, reversible, and does not require changing Claude/Codex API endpoint settings. The trade-off is that it sees process invocation, argv, stdin for supported noninteractive forms, stdout/stderr, and exit status; it does not see the full HTTP request stream or every tool event inside an opaque upstream CLI.

A base-URL proxy is the migration trigger if the product needs request-stream capture, per-turn routing, or provider-level policy enforcement. That is richer, but it changes more user environment and competes directly with existing router/proxy tools.

## Uninstall

```sh
poor-cli shims uninstall
```

Uninstall removes only managed wrapper files and refuses unmanaged files.
