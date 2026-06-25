VENV := .venv/bin
CORPUS := corpus
OUT := out
DEBUG := out/debug
PORT := 8080

.PHONY: setup test lint e2e vectorize build view mcp clean all help

help:
	@echo "haus — floor plan vectorization + 3D editor"
	@echo ""
	@echo "  make setup      install deps into .venv"
	@echo "  make build      image → vector + GLB for all corpus images"
	@echo "  make view       launch 3D editor in browser (port $(PORT))"
	@echo "  make mcp        start MCP server for AI-assisted editing"
	@echo "  make all        lint + test + build"
	@echo ""
	@echo "  make vectorize  vectorize only (no GLB)"
	@echo "  make test       run tests"
	@echo "  make lint       run ruff linter"
	@echo "  make e2e        run optional Playwright frontend tests"
	@echo "  make clean      remove out/"
	@echo ""
	@echo "typical workflow:"
	@echo "  make setup && make build && make view"
	@echo ""
	@echo "AI chat (set one or more):"
	@echo "  ANTHROPIC_API_KEY=... make view"
	@echo "  OPENAI_API_KEY=...    make view"
	@echo "  GEMINI_API_KEY=...    make view"
	@echo "  OLLAMA_BASE_URL=...   make view"
	@echo "  HAUS_CODEX_OSS=1 HAUS_CODEX_LOCAL_PROVIDER=ollama make view"

setup:
	uv venv --python 3.11
	uv pip install -e ".[dev]"

test:
	$(VENV)/pytest tests/ -v

lint:
	$(VENV)/ruff check src tests

e2e:
	$(VENV)/pytest tests/test_frontend_e2e.py -v

vectorize: $(wildcard $(CORPUS)/cleaned/*.jpg)
	@mkdir -p $(OUT)
	@for img in $(CORPUS)/cleaned/*.jpg; do \
		name=$$(basename "$$img" .jpg); \
		echo "--- vectorize $$name ---"; \
		$(VENV)/haus vectorize --image "$$img" --out $(OUT)/$$name --debug-dir $(OUT)/$$name/debug; \
	done

build: $(wildcard $(CORPUS)/cleaned/*.jpg)
	@mkdir -p $(OUT)
	@for img in $(CORPUS)/cleaned/*.jpg; do \
		name=$$(basename "$$img" .jpg); \
		echo "--- build $$name ---"; \
		$(VENV)/haus build --image "$$img" --out $(OUT)/$$name --debug-dir $(OUT)/$$name/debug; \
	done

view:
	$(VENV)/haus view --port $(PORT)

mcp:
	$(VENV)/haus mcp

clean:
	rm -rf $(OUT) output/playwright viewer/mcp-layout.json

all: lint test build
