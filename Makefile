.PHONY: cli server install installer install-info dev test test-lua lint lint-sizes bench-swe clean help hooks

PYTHON := $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/python,python3)
PIP := $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/pip,pip)
NVIM_TEST_RUNTIME := $(CURDIR)/nvim-poor-cli/.test-runtime
PLENARY_DIR ?= $(NVIM_TEST_RUNTIME)/site/pack/test/start/plenary.nvim

# ── venv guard ──────────────────────────────────────────────────────
REQUIRE_VENV := cli server exec agent-start agent-list watch preview deploy review-pr installer install-info install dev test lint index bench-swe
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

test-lua: ## run Lua plenary specs
	@mkdir -p "$(NVIM_TEST_RUNTIME)/data" "$(NVIM_TEST_RUNTIME)/state" "$(NVIM_TEST_RUNTIME)/cache" "$(NVIM_TEST_RUNTIME)/config" "$(NVIM_TEST_RUNTIME)/site/pack/test/start"
	XDG_DATA_HOME="$(NVIM_TEST_RUNTIME)/data" XDG_STATE_HOME="$(NVIM_TEST_RUNTIME)/state" XDG_CACHE_HOME="$(NVIM_TEST_RUNTIME)/cache" XDG_CONFIG_HOME="$(NVIM_TEST_RUNTIME)/config" PLENARY_DIR="$(PLENARY_DIR)" nvim --headless --noplugin -u nvim-poor-cli/tests/minimal_init.lua -c "PlenaryBustedDirectory nvim-poor-cli/tests/ {minimal_init = 'nvim-poor-cli/tests/minimal_init.lua'}"

lint: lint-sizes ## run linters
	ruff check poor_cli/

lint-sizes: ## check Python file line budgets
	$(PYTHON) scripts/check_line_budgets.py

index: ## build/refresh the semantic search index
	$(PYTHON) -c "from poor_cli.indexer import CodebaseIndexer; i=CodebaseIndexer(); s=i.index(); print(f'{s.total_files} files, {s.total_chunks} chunks')"

bench-swe: ## run SWE-bench Lite with explicit cost warning
	@echo "COST WARNING: SWE-bench Lite runs poor-cli over model-backed tasks and can incur API charges plus Docker evaluation cost."
	@printf "Type RUN SWE BENCH to continue: "; read confirm; if [ "$$confirm" != "RUN SWE BENCH" ]; then echo "aborted"; exit 1; fi; $(PYTHON) bench/swe_bench_lite/run.py --confirm-cost $(ARGS)

hooks: ## activate git hooks from .githooks/
	git config core.hooksPath .githooks

clean: ## remove build artifacts
	rm -rf build/ dist/ *.egg-info .poor-cli/index/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── help ─────────────────────────────────────────────────────────────

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
