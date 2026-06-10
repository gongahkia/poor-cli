.PHONY: install test lint cli agents plan run clean help

PYTHON := $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/python,python3)
PIP := $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV)/bin/pip,pip)

install: ## install v6 package in dev mode
	$(PIP) install -e ".[dev]"

test: ## run focused v6 tests
	$(PYTHON) -m pytest tests/

lint: ## run ruff checks
	$(PYTHON) -m ruff check src/poor_cli tests

cli: ## show CLI help
	$(PYTHON) -m poor_cli --help

agents: ## list detected agents
	$(PYTHON) -m poor_cli agents

plan: ## run planner, e.g. make plan GOAL="..."
	$(PYTHON) -m poor_cli plan "$(GOAL)"

run: ## run orchestrator, e.g. make run GOAL="..." ARGS="--yes"
	$(PYTHON) -m poor_cli run "$(GOAL)" $(ARGS)

clean: ## remove local build/runtime artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .poor-cli/v6
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
