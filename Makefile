VENV := .venv/bin
CORPUS := corpus
OUT := out
DEBUG := out/debug
PORT := 8080

.PHONY: setup test lint web-install web-build web-dev web-test api-dev e2e vectorize build view mcp clean all help

help:
	@echo "haus — floor plan vectorization + 3D editor"
	@echo ""
	@echo "  make setup      install deps into .venv"
	@echo "  make build      image → vector + GLB for all corpus images"
	@echo "  make web-build  build Svelte web app into package assets"
	@echo "  make web-dev    run Vite dev server for the Svelte app"
	@echo "  make api-dev    run Starlette API for split local development"
	@echo "  make view       launch built web app in browser (port $(PORT))"
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
	@echo "AI chat (local/browser runtimes):"
	@echo "  OLLAMA_BASE_URL=...   make view"
	@echo "  HAUS_CODEX_OSS=1 HAUS_CODEX_LOCAL_PROVIDER=ollama make view"
	@echo "  WebLLM runs in a WebGPU-capable browser"

setup:
	uv venv --python 3.11
	uv pip install -e ".[dev]"
	$(MAKE) web-install

test:
	$(VENV)/pytest tests/ -v

lint:
	$(VENV)/ruff check src tests
	cd web && npm run check

e2e:
	$(VENV)/pytest tests/test_frontend_e2e.py -v

web-install:
	cd web && npm install

web-build:
	cd web && npm run build
	rm -rf src/haus/web
	mkdir -p src/haus/web
	cp -R web/dist/. src/haus/web/

web-dev:
	cd web && npm run dev

web-test:
	cd web && npm run check && npm run test

api-dev:
	mkdir -p /tmp/haus-dev/viewer
	test -f /tmp/haus-dev/viewer/mcp-layout.json || printf '{"version":1,"items":[]}\n' > /tmp/haus-dev/viewer/mcp-layout.json
	_HAUS_ROOT=$(CURDIR)/src/haus/web _HAUS_LAYOUT_PATH=/tmp/haus-dev/viewer/mcp-layout.json $(VENV)/python -m uvicorn haus.chat_server:_reload_app --factory --host 127.0.0.1 --port $(PORT)

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
	rm -rf $(OUT) output/playwright viewer/mcp-layout.json web/dist

all: web-build lint web-test test build
