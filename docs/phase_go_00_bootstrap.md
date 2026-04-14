# Phase Go 00 — Bootstrap

**Priority:** Foundational — every later wave assumes this layout exists.
**Agents:** 1 (serial)
**Dependencies:** none
**Philosophy:** Zero business logic. Produce a clean, typed, CI-green repo skeleton that every subsequent agent can extend without discussion.

---

## Goals

1. Establish the canonical directory layout referenced throughout `orchestration.md`.
2. Pin the Go toolchain version and the exact third-party dependencies later waves rely on.
3. Make CI go green on an empty codebase so the first real commit surfaces only real signal.
4. Produce a runnable `make build` that emits a placeholder binary.

## Non-goals

- Any TUI, RPC, or markdown code.
- Any styling or theming.
- Any docs beyond a README stub.

---

## Agent 0A: Repo scaffold

### What to build

A Go module named `github.com/gongahkia/gocli-poor` with:

1. The full directory tree listed below.
2. `go.mod` with the pinned deps listed.
3. A Makefile wired for the standard dev loop.
4. A GitHub Actions workflow that runs lint + vet + build + test on every push.
5. A `.goreleaser.yml` skeleton ready for Wave 6 Agent 6B to extend.
6. A stub `cmd/gocli-poor/main.go` that prints version and exits.

### Directory tree (exact)

```
gocli-poor/
├── cmd/
│   └── gocli-poor/
│       └── main.go
├── internal/
│   ├── transport/       (empty + doc.go)
│   ├── rpc/             (empty + doc.go)
│   ├── protocol/        (empty + doc.go)
│   ├── server/          (empty + doc.go)
│   ├── tui/
│   │   ├── widgets/     (empty + doc.go)
│   │   └── flows/       (empty + doc.go)
│   ├── theme/           (empty + doc.go)
│   ├── config/          (empty + doc.go)
│   ├── state/           (empty + doc.go)
│   └── markdown/        (empty + doc.go)
├── docs/
│   └── (empty — user docs go here in Wave 6)
├── test/
│   ├── e2e/
│   └── fixtures/
├── bench/               (empty)
├── .github/
│   └── workflows/
│       └── ci.yml
├── go.mod
├── go.sum               (generated)
├── Makefile
├── VERSION
├── .goreleaser.yml
├── .gitignore
├── LICENSE
└── README.md
```

Each empty directory should contain a single `doc.go` with `// Package <name> …` so that `go build ./...` is green.

### go.mod pins

```go
module github.com/gongahkia/gocli-poor

go 1.22

require (
    github.com/charmbracelet/bubbletea v0.25.0
    github.com/charmbracelet/bubbles v0.18.0
    github.com/charmbracelet/lipgloss v0.10.0
    github.com/alecthomas/chroma/v2 v2.13.0
    github.com/mattn/go-runewidth v0.0.15
    github.com/sahilm/fuzzy v0.1.1
    github.com/zalando/go-keyring v0.2.3
    gopkg.in/yaml.v3 v3.0.1
)
```

### Makefile (exact targets and semantics)

```makefile
.PHONY: build test lint fmt clean run release vet

VERSION := $(shell cat VERSION)
LDFLAGS := -X main.Version=$(VERSION)

build:
	go build -ldflags "$(LDFLAGS)" -o bin/gocli-poor ./cmd/gocli-poor

test:
	go test ./...

test-unit:
	go test -short ./...

test-integration:
	go test -run Integration ./...

test-e2e:
	go test -run E2E ./test/e2e/...

lint:
	golangci-lint run

vet:
	go vet ./...

fmt:
	gofmt -s -w .
	goimports -w .

clean:
	rm -rf bin/ dist/

run: build
	./bin/gocli-poor

release:
	goreleaser release --clean

coverage:
	go test -coverprofile=coverage.out ./...
	go tool cover -func=coverage.out | tail -n 1
```

### cmd/gocli-poor/main.go (placeholder)

```go
package main

import (
	"fmt"
	"os"
)

var Version = "dev"

func main() {
	fmt.Fprintf(os.Stdout, "gocli-poor %s\n", Version)
	os.Exit(0)
}
```

### .github/workflows/ci.yml

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true
      - run: go vet ./...
      - uses: golangci/golangci-lint-action@v4
        with:
          version: v1.57
      - run: make build
      - run: make test
```

### .goreleaser.yml (skeleton — Wave 6B extends)

```yaml
project_name: gocli-poor
version: 2

before:
  hooks:
    - go mod tidy

builds:
  - id: gocli-poor
    main: ./cmd/gocli-poor
    binary: gocli-poor
    env:
      - CGO_ENABLED=0
    goos: [linux, darwin, windows]
    goarch: [amd64, arm64]
    ldflags:
      - -s -w -X main.Version={{.Version}}

archives:
  - formats: [tar.gz]
    name_template: >-
      {{ .ProjectName }}_
      {{- .Version }}_
      {{- .Os }}_
      {{- .Arch }}

checksum:
  name_template: checksums.txt

release:
  draft: true
```

### .gitignore

Standard Go + macOS + editor ignores. Minimum:
```
bin/
dist/
*.out
*.test
.DS_Store
.vscode/
.idea/
```

### README.md (stub)

One paragraph describing the project, plus a single prominent link to `../poor-cli/docs/orchestration.md` in the backend repo (since that's where the plan lives). Optional: a roadmap section that mirrors the wave overview table.

---

## Acceptance criteria

- [ ] `go build ./...` exits 0.
- [ ] `go vet ./...` exits 0.
- [ ] `make build` produces `bin/gocli-poor`.
- [ ] `./bin/gocli-poor` prints `gocli-poor 0.0.1` and exits 0.
- [ ] `make test` exits 0 even with no tests (go test is happy with empty packages as long as they have a Go file).
- [ ] CI passes on first push.
- [ ] Every `internal/*` subdirectory has at least one `.go` file so `go build ./...` does not complain about non-Go directories.
- [ ] go.sum is committed and reproducible (`go mod tidy` idempotent).
- [ ] `golangci-lint run` exits 0 (may require a `.golangci.yml` with relaxed defaults for an empty repo).

## Rollback / risk

Very low. All deletions are safe — no external state changed.

## Handoff to later waves

- Every later agent's deliverables specify paths relative to this layout.
- If an agent proposes creating a new top-level directory, flag it at review — the layout is intentionally flat.
- If a later wave needs a dependency not pinned here, that agent adds it + runs `go mod tidy` themselves. This wave ships only the deps listed above.

## Decisions locked

1. Go module path: `github.com/gongahkia/gocli-poor`.
2. Target parent directory: `/Users/gongahkia/Desktop/coding/projects/gocli-poor` (alongside `poor-cli`).
3. License: Apache-2.0.
4. CI lives in this repo (standalone, not monorepo-shared).
5. Go toolchain target: 1.22.
