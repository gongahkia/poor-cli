# Phase Go 06 — Polish & Ship

**Priority:** Ship-gate. Everything works after Wave 5; this wave makes it *reliable, distributable, documented, and fast*.
**Agents:** 4 (all parallel, disjoint concerns)
**Dependencies:** Wave 5
**Philosophy:** Measure, don't guess. Document the contract. Ship a binary users can `brew install`.

---

## File-scope table

| Agent | Creates | Modifies |
|-------|---------|----------|
| 6A    | `test/e2e/chat_test.go`, `test/fixtures/*.jsonl`, `test/e2e/helpers.go` | `Makefile` (adds targets) |
| 6B    | `install.sh`, `homebrew-tap/Formula/gocli-poor.rb`, `.github/workflows/release.yml` | `.goreleaser.yml` (full), `README.md` (install section) |
| 6C    | `docs/quickstart.md`, `docs/keybindings.md`, `docs/config.md`, `docs/troubleshooting.md`, `docs/commands.md` | `README.md` (main overview) |
| 6D    | `bench/render_test.go`, `bench/streaming_test.go`, `bench/startup_test.go`, `docs/benchmarks.md` | `Makefile` (bench target) |

### Intra-phase collisions

- **`README.md`** — 6B adds an install section; 6C adds the main overview. Split by section header; no conflict if agents stay in their H2 sections. Serialize if concerned.
- **`Makefile`** — 6A adds test targets; 6D adds bench target. Different lines.

---

## Agent 6A: Test suite completion

### Goals

Reach 80% coverage across `internal/*` and add cross-cutting tests that validate wave-boundary behavior.

### Required tests

#### 1. End-to-end chat test

```go
//go:build e2e

package e2e

func TestE2E_HappyPathChat(t *testing.T) {
    if testing.Short() { t.Skip("e2e") }
    serverPath := os.Getenv("GOCLI_POOR_E2E_SERVER")
    if serverPath == "" { t.Skip("set GOCLI_POOR_E2E_SERVER") }

    // spawn gocli-poor with --headless test harness
    // send "say hi" as input
    // assert streaming output contains "hello" within 10s
    // assert cost > 0 in status
    // assert exit clean
}
```

Needs a headless mode in the TUI (Wave 2A: add `--headless` flag that skips Bubbletea init and uses a stub renderer for testing). The headless mode pipes rendered frames to a buffer for assertion.

#### 2. Fixture replay test

```go
func TestE2E_FixtureReplay(t *testing.T) {
    // replay fixtures/chat-session-01.jsonl through mock server
    // feed through real client stack: transport + rpc + state + flows + widgets + markdown
    // assert final rendered output matches fixtures/chat-session-01.golden.txt
}
```

Fixtures format (JSONL):
```
{"dir":"c2s","body":{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}}
{"dir":"s2c","body":{"jsonrpc":"2.0","id":1,"result":{"capabilities":{...}}}}
{"dir":"s2c","body":{"jsonrpc":"2.0","method":"poor-cli/streamChunk","params":{"chunk":"Hello","done":false,"requestId":"..."}}}
...
```

#### 3. Transport fuzz

```go
func FuzzTransportReader(f *testing.F) {
    f.Fuzz(func(t *testing.T, header, body []byte) {
        // assert reader never panics; either parses or returns error
    })
}
```

#### 4. Markdown streaming fuzz

```go
func FuzzStreamer_ByteSplit(f *testing.F) {
    f.Fuzz(func(t *testing.T, doc []byte, splitSeeds []byte) {
        // feed doc byte-by-byte per seed; compare to full-feed rendering
    })
}
```

#### 5. Goroutine leak check

`TestMain` installs `goleak.VerifyTestMain(m)`.

### Makefile additions

```makefile
test-e2e:
	go test -tags=e2e -run E2E ./test/e2e/...

test-fuzz:
	go test -run=^$ -fuzz=FuzzTransportReader -fuzztime=30s ./internal/transport/
	go test -run=^$ -fuzz=FuzzStreamer_ByteSplit -fuzztime=60s ./internal/markdown/

coverage-html:
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
```

### Acceptance criteria

- [ ] Overall coverage ≥ 80% on `internal/*`.
- [ ] E2E test passes in CI with provided fixtures.
- [ ] Fuzz jobs run 60s clean in CI nightly.
- [ ] Goroutine leak checker clean on all test runs.

### Decisions locked

- E2E provider: `ollama` with a local model (zero API cost). Fallback to the mock server via fixtures when ollama is not installed.
- Fixtures are captured by enabling a logging tee on `rpc.Client` that writes all traffic to `test/fixtures/*.jsonl` during a real session (flag-gated: `GOCLI_POOR_RECORD_FIXTURES=1`).

---

## Agent 6B: Distribution

### Goals

1. One-command install on macOS + Linux.
2. Prebuilt binaries for darwin/linux/windows × amd64/arm64.
3. Homebrew tap for `brew install <org>/tap/gocli-poor`.
4. GitHub Actions release pipeline on tag push.

### .goreleaser.yml (full)

```yaml
version: 2
project_name: gocli-poor

before:
  hooks:
    - go mod tidy
    - go generate ./...

builds:
  - id: gocli-poor
    main: ./cmd/gocli-poor
    binary: gocli-poor
    env:
      - CGO_ENABLED=0
    goos: [linux, darwin, windows]
    goarch: [amd64, arm64]
    flags: [-trimpath]
    ldflags:
      - -s -w -X main.Version={{.Version}} -X main.Commit={{.Commit}}

archives:
  - id: default
    formats: [tar.gz]
    format_overrides:
      - goos: windows
        formats: [zip]
    name_template: >-
      {{ .ProjectName }}_{{ .Version }}_{{ .Os }}_{{ .Arch }}

checksum:
  name_template: checksums.txt

brews:
  - name: gocli-poor
    description: "TUI chat client for poor-cli"
    homepage: "https://github.com/gongahkia/gocli-poor"
    repository:
      owner: "gongahkia"
      name: homebrew-tap
    install: |
      bin.install "gocli-poor"
    test: |
      assert_match "gocli-poor", shell_output("#{bin}/gocli-poor --version")

release:
  draft: true
  prerelease: auto
```

### install.sh

Standard curl-able installer:
- Detects OS + arch.
- Downloads latest release archive from GitHub.
- Verifies checksum.
- Unpacks to `$HOME/.local/bin` or `/usr/local/bin`.
- Sanity-checks with `gocli-poor --version`.

Must be idempotent and have `--uninstall`.

### .github/workflows/release.yml

```yaml
name: release
on:
  push:
    tags: ['v*']
permissions:
  contents: write
  packages: write
jobs:
  goreleaser:
    runs-on: macos-latest  # macos for universal binaries if desired; else ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-go@v5
        with: { go-version: '1.22' }
      - uses: goreleaser/goreleaser-action@v5
        with:
          version: ~> v2
          args: release --clean
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          HOMEBREW_TAP_GITHUB_TOKEN: ${{ secrets.HOMEBREW_TAP_GITHUB_TOKEN }}
```

### Acceptance criteria

- [ ] Tag `v0.1.0` produces a draft release with all 6 binaries + checksums.
- [ ] `curl -sSf https://.../install.sh | sh` installs on macOS + Linux.
- [ ] `brew install <tap>/gocli-poor` works after goreleaser publishes.
- [ ] `gocli-poor --version` prints matching tag.

### Decisions locked

- Tap repo: `gongahkia/homebrew-tap`.
- macOS binaries: separate arm64 + amd64 (no lipo-merged universal binary in v1).
- Package managers beyond Homebrew + direct download: NOT published in v1.

---

## Agent 6C: User documentation

### Goals

Ship documentation a first-time user can follow end-to-end in under 10 minutes.

### Files

1. `README.md` — 1-minute pitch, install, 60-second demo, links.
2. `docs/quickstart.md` — 10-minute walkthrough with screenshots via asciicast.
3. `docs/keybindings.md` — every keybind with rebinding instructions.
4. `docs/config.md` — every config field, types, defaults, env-var equivalents.
5. `docs/commands.md` — every slash command + arguments.
6. `docs/troubleshooting.md` — common issues:
   - Server not found → how to install poor-cli-server.
   - API key prompt → how to save to keyring vs env.
   - Streaming appears frozen → server log file location.
   - Colors look wrong → NO_COLOR / COLORTERM.
   - Windows terminal quirks.

### README sections (required order)

```markdown
# gocli-poor

> A fast, flicker-free TUI chat client for the poor-cli backend.

![demo](https://asciinema.org/a/XXXXXX.svg)

## Install
[brew | curl install.sh | download binary | from source]

## Quickstart
[60-second walkthrough]

## Features
- [bullet list]

## Configuration
[link to docs/config.md]

## Documentation
[links to each doc]

## License
```

### Acceptance criteria

- [ ] All 6 files render cleanly on GitHub.
- [ ] No broken links.
- [ ] Asciicast recording exists (even if placeholder URL).
- [ ] A new user can go from zero to a working chat turn in under 10 minutes using the docs.

### Decisions locked

- Demo: link to an asciicast recording. Do NOT inline a GIF (binary bloat).
- Docs language: English only in v1.

---

## Agent 6D: Benchmarks & performance

### Goals

Document baseline performance and ensure no regressions.

### Targets (must hit on M-series laptop)

| Metric | Target |
|--------|--------|
| Startup to first paint | ≤ 200 ms |
| RSS steady-state | ≤ 50 MB |
| Render latency per frame | ≤ 16 ms (60 Hz) |
| Markdown streamer throughput | ≥ 30 MB/s |
| Transport round-trip (loopback) | ≥ 100k msg/s |
| CPU usage at 200 tok/s stream | ≤ 10% of one core |

### Benchmarks

```go
// bench/render_test.go
func BenchmarkMarkdownStreamer_Chunk(b *testing.B) { ... }
func BenchmarkChatView_AppendChunk(b *testing.B) { ... }
func BenchmarkRenderer_TailSince(b *testing.B) { ... }

// bench/streaming_test.go
func BenchmarkE2E_200TokPerSec(b *testing.B) {
    // mock server that emits at 200 tok/s
    // measure CPU %, dropped frames, render latency
}

// bench/startup_test.go
func BenchmarkStartup_FirstPaint(b *testing.B) {
    // spawn binary, measure ms to first rendered frame
}
```

### docs/benchmarks.md

Table of results + flamegraph links. Update on every release.

### Optimization playbook

If a target isn't hit:
1. `pprof` the hot path.
2. Check for unnecessary allocations (reuse buffers, `sync.Pool` where warranted).
3. Check for unnecessary mutex contention (rarely a problem with our design).
4. Check for unnecessary string conversions (`[]byte` ↔ `string`).
5. Profile-guided optimization — generate a pgo file from a real session, rebuild with `-pgo`.

### Acceptance criteria

- [ ] All targets met on reference hardware.
- [ ] Benchmarks documented with before/after if changes were needed.
- [ ] CI runs benchmarks on main branch pushes; regression > 10% fails the build.

### Decisions locked

- Targets as written above (measured on M-series laptop reference hardware).
- Benchmarks run in CI on pushes to `main` only (not every PR) to balance cost vs. regression catch.

---

## Post-wave checklist

After Wave 6 lands:

- [ ] `v0.1.0` tagged + released.
- [ ] Homebrew tap contains formula.
- [ ] README links to binaries, docs, asciicast.
- [ ] CI green on main + release branch.
- [ ] User acceptance test: at least one person outside the development loop follows quickstart.md and reports success.
- [ ] Next wave (7+) planning issues opened for follow-up work: multiplayer client, MCP registry UI, watch panel, custom theme publishing.
