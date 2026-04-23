# Wok Performance Benchmarks

Wok now includes a Criterion benchmark harness focused on large-workspace query paths.

## Scope

`wok-app/benches/large_workspace.rs` currently measures:

1. Global output search over `50,000` lines (`GlobalSearch::search`).
2. Block filter query over `20,000` output lines (`BlockQueryState::search` in `Filter` mode).
3. Pane + global command-history search over `44,000` entries (`CommandSearchState::search`).
4. CPU-side quad batch construction for a `240x90` high-DPI viewport-like workload (`QuadBatch` background and glyph emission).

These workloads target the real bottleneck classes for interactive terminal UX: repeated search/filter operations on very large workspaces and CPU-side render preparation for dense Retina-scale terminal grids.

## Run

```bash
cargo bench -p wok --bench large_workspace
```

For compile-only verification in CI/local smoke checks:

```bash
cargo bench -p wok --bench large_workspace --no-run
```

## Usage Notes

1. Use release-mode benchmark runs on an otherwise idle machine.
2. Compare medians across commits instead of single-run outliers.
3. Track regressions before changing `MAX_GLOBAL_SEARCH_LINES` or command-history search behavior.

## Runtime Profiling

Set `debug_overlay = true` in your Wok config to inspect live frame timings. The overlay reports rolling last/average/max timings for:

- frame tick orchestration
- PTY drain
- semantic event handling
- replay capture
- owned-input sync
- output hooks
- block-query refresh
- CPU-side quad construction
- GPU render submission/presentation
- terminal clean-up bookkeeping

Use these phase timings before considering a native macOS frontend rewrite. If `quads` or `gpu` dominate, optimize the renderer path first; if text input or event-loop behavior dominates, that is stronger evidence for a native AppKit bridge.

## Command Telemetry

Set `command_telemetry = true` to write command lifecycle records to:

```bash
~/.config/wok/command-telemetry.jsonl
```

Each record is one JSON object. `command_submitted` records the pane, command text, cwd, and timestamp. `command_completed` adds exit code, duration, block id, and output row range. This is intentionally disabled by default because command text can contain secrets.

## PR Regression Gate

CI now runs a pull-request-only performance gate (`perf_gate` job in `.github/workflows/ci.yml`):

1. Benchmarks the PR base commit.
2. Benchmarks the PR head commit.
3. Uses Criterion baseline comparison and checks median change confidence intervals.
4. Fails the job when any benchmark regresses more than the configured threshold (`12%` by default).

The job uploads:

- `.perf-gate/perf-gate-summary.md`
- `.perf-gate/perf-gate-results.json`
