# archived: gocli-poor (Go TUI)

Deprecated 2026-04-15. The Go Bubble Tea TUI client is no longer the primary frontend for poor-cli. Forward frontend work happens in `nvim-poor-cli/`. The Python backend at `poor_cli/` is unchanged.

## Contents

- `cmd-gocli-poor/` — Go entrypoint (was `cmd/gocli-poor/`).
- `internal/` — Go packages: config, deps, markdown, protocol, rpc, server, state, theme, transport, tui.
- `go.mod`, `go.sum`, `.golangci.yml`, `.goreleaser.yml` — Go build + release config.
- `homebrew-tap/` — brew tap formula.
- `install.sh` — release installer for the `gocli-poor` binary.
- `test/` — Go e2e + fixtures.
- `bench/*.go` — Go perceived-latency / render / startup / streaming benchmarks.
- `docs/` — Go-TUI-specific documentation: `phase_go_00..10`, BENCHMARKS, keybindings, config, perceived_latency, visual_audit, orchestration.

## Rebuilding from archive

Not supported from this location — the `internal/*` import paths refer to `github.com/gongahkia/gocli-poor/internal/...` and the module root was the repo root. Relocate the `cmd-gocli-poor/` (restore to `cmd/gocli-poor/`), `internal/`, and `go.mod/sum` back to the repo root to build.

## Why archived

Repo direction consolidated on Python backend + Neovim plugin. See `POOR.md`, `NORTH_STAR.md`.
