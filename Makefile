SHELL := /usr/bin/env bash

.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
POORCLI := $(VENV)/bin/poor-cli

.PHONY: help venv setup check-env run run-module run-cli test lint import-graph typecheck tui acceptance

help:
	@echo "Available targets:"
	@echo "  make setup         Create .venv, install deps, and create .env if missing"
	@echo "  make run           Run Rust TUI via ./run.sh"
	@echo "  make run-module    Run Rust TUI via python -m poor_cli wrapper"
	@echo "  make run-cli       Run Rust TUI via installed poor-cli entrypoint"
	@echo "  make test          Run pytest tests/ -v"
	@echo "  make lint          Run ruff check poor_cli tests"
	@echo "  make import-graph  Run import graph check"
	@echo "  make typecheck     Run mypy poor_cli --no-error-summary"
	@echo "  make tui           Run Rust TUI via ./run_tui.sh"
	@echo "  make acceptance    Run acceptance prep + manual walkthrough guide"

venv:
	@if [ ! -x "$(PY)" ]; then \
		$(PYTHON) -m venv "$(VENV)"; \
	fi

setup: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example (fill in your API keys)."; \
	fi

check-env:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Run 'make setup' first."; \
		exit 1; \
	fi

run: check-env
	./run.sh

run-module: setup check-env
	$(PY) -m poor_cli

run-cli: setup check-env
	$(POORCLI)

test: setup
	$(PYTEST) tests/ -v

lint: setup
	$(RUFF) check poor_cli tests

import-graph: setup
	$(PY) scripts/import_graph_check.py

typecheck: setup
	$(PIP) install mypy types-PyYAML types-aiofiles
	$(MYPY) poor_cli --no-error-summary

tui:
	./run_tui.sh

acceptance:
	./scripts/acceptance_walkthrough.sh
