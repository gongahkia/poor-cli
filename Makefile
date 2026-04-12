.PHONY: cli server install installer install-info dev test lint lint-sizes clean help hooks

PYTHON := $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/python,python3)
PIP := $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/pip,pip)

# ── venv guard ──────────────────────────────────────────────────────
REQUIRE_VENV := cli server exec agent-start agent-list watch preview deploy review-pr installer install-info install dev test lint index
$(foreach t,$(REQUIRE_VENV),$(eval $(t): _check-venv))

_check-venv:
ifndef VIRTUAL_ENV
	$(error virtualenv not activated — run 'source .venv/bin/activate' first)
endif

# ── launch surfaces ──────────────────────────────────────────────────

cli: ## launch poor-cli (default surface)
	$(PYTHON) -m poor_cli

server: ## start the JSON-RPC server (for editor plugins)
	$(PYTHON) -m poor_cli server

# ── headless / background ────────────────────────────────────────────

exec: ## run headless (poor-cli exec --prompt "...")
	$(PYTHON) -m poor_cli exec $(ARGS)

agent-start: ## start a background agent (PROMPT="..." make agent-start)
	$(PYTHON) -m poor_cli agent start --prompt "$(PROMPT)"

agent-list: ## list background agents
	$(PYTHON) -m poor_cli agent list

watch: ## start IDE watch mode
	$(PYTHON) -m poor_cli watch

preview: ## start live preview server
	$(PYTHON) -m poor_cli preview

deploy: ## deploy project (TARGET=vercel make deploy)
	$(PYTHON) -m poor_cli deploy $(if $(TARGET),--target $(TARGET),)

review-pr: ## review a PR (PR=123 make review-pr)
	$(PYTHON) -m poor_cli review-pr $(PR)

# ── installer ────────────────────────────────────────────────────────

installer: ## run the interactive installer and setup wizard
	$(PYTHON) -m poor_cli install

install-info: ## inspect install details
	$(PYTHON) -m poor_cli install-info

# ── build ────────────────────────────────────────────────────────────

install: ## install the Python package in dev mode
	$(PIP) install -e ".[dev]"

# ── dev ──────────────────────────────────────────────────────────────

dev: ## install deps + launch CLI
	$(PIP) install -e . && $(MAKE) cli

test: ## run Python tests with coverage
	$(PYTHON) -m pytest tests/ -x -q --cov=poor_cli --cov-report=term-missing

lint: lint-sizes ## run linters
	ruff check poor_cli/

lint-sizes: ## check Python file line budgets
	$(PYTHON) scripts/check_line_budgets.py

index: ## build/refresh the semantic search index
	$(PYTHON) -c "from poor_cli.indexer import CodebaseIndexer; i=CodebaseIndexer(); s=i.index(); print(f'{s.total_files} files, {s.total_chunks} chunks')"

hooks: ## activate git hooks from .githooks/
	git config core.hooksPath .githooks

clean: ## remove build artifacts
	rm -rf build/ dist/ *.egg-info .poor-cli/index/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── help ─────────────────────────────────────────────────────────────

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
