VENV := .venv/bin
CORPUS := corpus
OUT := out
DEBUG := out/debug
PORT := 8080
CASE_PORT := 8090

.PHONY: setup test lint vectorize build view mcp case-server case-smoke clean all help

help:
	@echo "haus — floor plan vectorization + 3D editor"
	@echo ""
	@echo "  make setup      install deps into .venv"
	@echo "  make build      image → vector + GLB for all corpus images"
	@echo "  make view       launch 3D editor in browser (port $(PORT))"
	@echo "  make mcp        start MCP server for AI-assisted editing"
	@echo "  make case-server start Stage-1 Case HTTP service (port $(CASE_PORT))"
	@echo "  make case-smoke  smoke-test a running Case HTTP service"
	@echo "  make all        lint + test + build"
	@echo ""
	@echo "  make vectorize  vectorize only (no GLB)"
	@echo "  make test       run tests"
	@echo "  make lint       run ruff linter"
	@echo "  make clean      remove out/"
	@echo ""
	@echo "typical workflow:"
	@echo "  make setup && make build && make view"
	@echo ""
	@echo "AI chat (set one or more):"
	@echo "  ANTHROPIC_API_KEY=... make view"
	@echo "  OPENAI_API_KEY=...    make view"
	@echo "  GEMINI_API_KEY=...    make view"

setup:
	uv venv --python 3.11
	uv pip install -e ".[dev]"

test:
	$(VENV)/pytest tests/ -v

lint:
	$(VENV)/ruff check src/ tests/ scripts/

vectorize: $(wildcard $(CORPUS)/*.jpg)
	@mkdir -p $(OUT)
	@for img in $(CORPUS)/*.jpg; do \
		name=$$(basename "$$img" .jpg); \
		echo "--- vectorize $$name ---"; \
		$(VENV)/haus vectorize --image "$$img" --out $(OUT)/$$name --debug-dir $(OUT)/$$name/debug; \
	done

build: $(wildcard $(CORPUS)/*.jpg)
	@mkdir -p $(OUT)
	@for img in $(CORPUS)/*.jpg; do \
		name=$$(basename "$$img" .jpg); \
		echo "--- build $$name ---"; \
		$(VENV)/haus build --image "$$img" --out $(OUT)/$$name --debug-dir $(OUT)/$$name/debug; \
	done

view:
	$(VENV)/haus view --port $(PORT)

mcp:
	$(VENV)/haus mcp

case-server:
	$(VENV)/haus case-server --port $(CASE_PORT) --proposals-dir tests/fixtures/proposals --vendor-cache-dir tests/fixtures/vendors

case-smoke:
	$(VENV)/python scripts/case_smoke.py --base-url http://127.0.0.1:$(CASE_PORT)

clean:
	rm -rf $(OUT) viewer/mcp-layout.json

all: lint test build
