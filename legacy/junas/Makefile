.PHONY: up down dev api frontend test lint migrate ingest-all download-data setup

# === primary ===
up:
	docker compose up -d

down:
	docker compose down

dev:
	@echo "Starting dev servers (backend :8000, frontend :3000)..."
	$(MAKE) -j2 api frontend

# === backend ===
api:
	cd backend && uvicorn api.main:app --reload --port 8000

# === frontend ===
frontend:
	cd frontend && npm run dev

# === database ===
migrate:
	cd backend && alembic -c migrations/alembic.ini upgrade head

# === testing ===
test:
	cd backend && pytest -x -q

lint:
	cd backend && ruff check . && mypy api ml data

# === data ===
ingest-all:
	cd backend && python -m ml.pipelines.run_all

VENDOR_DIR := vendor-data

download-data: download-lecard download-glossaries download-ner
	@echo "All datasets downloaded to $(VENDOR_DIR)/"

download-lecard:
	@mkdir -p $(VENDOR_DIR)
	@if [ ! -d "$(VENDOR_DIR)/LeCaRD" ]; then git clone --depth 1 https://github.com/myx666/LeCaRD.git $(VENDOR_DIR)/LeCaRD; fi

download-glossaries:
	@mkdir -p $(VENDOR_DIR)
	@if [ ! -d "$(VENDOR_DIR)/datasets" ]; then git clone --depth 1 https://github.com/public-law/datasets.git $(VENDOR_DIR)/datasets; fi

download-ner:
	@mkdir -p $(VENDOR_DIR)
	@if [ ! -d "$(VENDOR_DIR)/Legal-Entity-Recognition" ]; then git clone --depth 1 https://github.com/elenanereiss/Legal-Entity-Recognition.git $(VENDOR_DIR)/Legal-Entity-Recognition; fi

# === quick setup ===
setup: download-data
	docker compose up -d postgres elasticsearch qdrant redis
	sleep 5
	$(MAKE) migrate
	$(MAKE) ingest-all
	@echo "Setup complete. Run 'make up' to start all services."
