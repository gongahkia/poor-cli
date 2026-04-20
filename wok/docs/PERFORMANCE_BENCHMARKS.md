# Wok Performance Benchmarks

Wok now includes a Criterion benchmark harness focused on large-workspace query paths.

## Scope

`wok-app/benches/large_workspace.rs` currently measures:

1. Global output search over `50,000` lines (`GlobalSearch::search`).
2. Block filter query over `20,000` output lines (`BlockQueryState::search` in `Filter` mode).
3. Pane + global command-history search over `44,000` entries (`CommandSearchState::search`).

These workloads target the real bottleneck class for interactive terminal UX: repeated search/filter operations on very large workspaces.

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

## PR Regression Gate

CI now runs a pull-request-only performance gate (`perf_gate` job in `.github/workflows/ci.yml`):

1. Benchmarks the PR base commit.
2. Benchmarks the PR head commit.
3. Uses Criterion baseline comparison and checks median change confidence intervals.
4. Fails the job when any benchmark regresses more than the configured threshold (`12%` by default).

The job uploads:

- `.perf-gate/perf-gate-summary.md`
- `.perf-gate/perf-gate-results.json`
