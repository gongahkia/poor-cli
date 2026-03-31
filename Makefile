.PHONY: cli server tui build-tui install dev test lint clean help

# ── venv guard ──────────────────────────────────────────────────────
REQUIRE_VENV := cli server exec agent-start agent-list watch preview deploy review-pr install dev test lint index
$(foreach t,$(REQUIRE_VENV),$(eval $(t): _check-venv))

_check-venv:
ifndef VIRTUAL_ENV
	$(error virtualenv not activated — run 'source .venv/bin/activate' first)
endif

# ── launch surfaces ──────────────────────────────────────────────────

cli: ## launch the Rust TUI (default surface)
	python3 -m poor_cli

server: ## start the JSON-RPC server (for editor plugins)
	python3 -m poor_cli server

# ── headless / background ────────────────────────────────────────────

exec: ## run headless (poor-cli exec --prompt "...")
	python3 -m poor_cli exec $(ARGS)

agent-start: ## start a background agent (PROMPT="..." make agent-start)
	python3 -m poor_cli agent start --prompt "$(PROMPT)"

agent-list: ## list background agents
	python3 -m poor_cli agent list

watch: ## start IDE watch mode
	python3 -m poor_cli watch

preview: ## start live preview server
	python3 -m poor_cli preview

deploy: ## deploy project (TARGET=vercel make deploy)
	python3 -m poor_cli deploy $(if $(TARGET),--target $(TARGET),)

review-pr: ## review a PR (PR=123 make review-pr)
	python3 -m poor_cli review-pr $(PR)

# ── build ────────────────────────────────────────────────────────────

build-tui: ## build the Rust TUI binary
	cd poor-cli-tui && cargo build --release

install: ## install the Python package in dev mode
	pip install -e ".[dev]"

# ── dev ──────────────────────────────────────────────────────────────

dev: ## install deps + build TUI + launch CLI
	pip install -e . && $(MAKE) build-tui && $(MAKE) cli

test: ## run Python tests
	python3 -m pytest tests/ -x -q

lint: ## run linters
	ruff check poor_cli/
	cd poor-cli-tui && cargo clippy --quiet

index: ## build/refresh the semantic search index
	python3 -c "from poor_cli.indexer import CodebaseIndexer; i=CodebaseIndexer(); s=i.index(); print(f'{s.total_files} files, {s.total_chunks} chunks')"

clean: ## remove build artifacts
	rm -rf build/ dist/ *.egg-info poor-cli-tui/target/release .poor-cli/index/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── help ─────────────────────────────────────────────────────────────

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
