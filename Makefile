VENV := .venv/bin
CORPUS := corpus
OUT := out
DEBUG := out/debug

.PHONY: setup test lint vectorize build view clean all

setup:
	uv venv --python 3.11
	uv pip install -e ".[dev]"

test:
	$(VENV)/pytest tests/ -v

lint:
	$(VENV)/ruff check src/ tests/

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
	@glb=$$(ls -t $(OUT)/*/model.glb 2>/dev/null | head -1); \
	if [ -z "$$glb" ]; then echo "No GLB found. Run 'make build' first."; exit 1; fi; \
	echo "Viewing $$glb"; \
	$(VENV)/haus view --glb "$$glb"

clean:
	rm -rf $(OUT)

all: lint test build
