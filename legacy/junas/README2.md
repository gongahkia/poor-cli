# Junas

Legal AI platform combining multi-jurisdiction retrieval, BYOK AI chat, contract analysis, compliance checking, court prediction, document drafting, and benchmark evaluation.

## Quick Start

```bash
# 1. download vendor datasets
make download-data

# 2. start infrastructure (postgres, elasticsearch, qdrant, redis)
docker compose up -d postgres elasticsearch qdrant redis
sleep 5

# 3. run database migrations
make migrate

# 4. ingest data (glossaries, statutes, case law)
make ingest-all

# 5. start all services
make up
```

Open http://localhost:3000

## Repository Direction

As of April 3, 2026, `frontend/` + `backend/` is the primary product stack and source of truth.

The legacy desktop stack in `src/` + `src-tauri/` is being migrated into the unified web platform and will be removed after feature parity and stabilization.

## Features

| Category | Feature | Description |
|----------|---------|-------------|
| **Draft** | AI Chat | BYOK streaming chat (Claude, OpenAI, Gemini, Ollama, LM Studio) |
| **Draft** | Clause Library | 6 SG clauses with 4 tone variants (standard, aggressive, balanced, protective) |
| **Draft** | Templates | Legal document templates (NDA, employment, MOU, tenancy, board resolution, share transfer) |
| **Search** | Glossary | Multi-jurisdiction legal glossary (6 jurisdictions) |
| **Search** | Statutes | Statute search with keyword, semantic, and hybrid modes |
| **Search** | Case Retrieval | BM25 + dense + cross-encoder reranker pipeline |
| **Search** | Research Assistant | RAG-powered legal Q&A with citation verification |
| **Analyze** | Contract Analysis | LEDGAR clause classification + unfair ToS scanning |
| **Analyze** | Legal NER | 19 fine-grained entity types (multilingual) |
| **Analyze** | Compliance | PDPA, Employment Act, contract basics checking |
| **Analyze** | Document Parsing | PDF and DOCX text extraction |
| **Predict** | Court Prediction | SCOTUS, ECtHR, CaseHOLD, EUR-LEX models |
| **Evaluate** | Benchmarks | LexGLUE multi-task benchmark suite |
| **Reference** | Rome Statute | ICC treaty knowledge base |

## Architecture

```
junas/
├── backend/          Python FastAPI (unified backend)
│   ├── api/          routers + services (17 routers, 21 services)
│   ├── ml/           ML training, evaluation, pipelines
│   ├── data/         data parsers
│   └── migrations/   Alembic (4 migrations)
├── frontend/         Next.js 14 (unified frontend, 13 pages)
├── docker-compose.yml
├── Makefile
└── vendor-data/      external datasets
```

**Infrastructure**: PostgreSQL 16, Elasticsearch 8.13, Qdrant 1.8.4, Redis 7

## Jurisdictions

Singapore, Malaysia, United States, European Union, International (ICC). Extensible via `jurisdiction_registry.py`.

## API Endpoints

All endpoints at `http://localhost:8000/api/v1/`. Full Swagger docs at `/docs`.

- `/chat/stream` `/chat/send` `/chat/providers` - BYOK AI chat
- `/clauses` `/clauses/{id}/tone/{tone}` - clause library
- `/templates` `/templates/{id}/render` - document templates
- `/compliance/check` - compliance checking
- `/documents/parse` - PDF/DOCX parsing
- `/legal-sources/sso` `/legal-sources/commonlii` - SG legal sources
- `/jurisdictions` - multi-jurisdiction registry
- `/glossary/search` - legal glossary
- `/statutes/search` - statute retrieval
- `/search/cases` - case law retrieval
- `/research/ask` - RAG legal assistant
- `/contracts/classify` `/contracts/scan-tos` - contract analysis
- `/ner/extract` - named entity recognition
- `/predict/scotus` `/predict/ecthr` `/predict/casehold` `/predict/eurlex` - court prediction
- `/benchmarks/run` `/benchmarks/leaderboard` - benchmarks
- `/rome-statute/search` - Rome Statute

## Development

```bash
make dev       # backend + frontend in dev mode
make test      # run pytest
make lint      # ruff + mypy
npm run dev:unified                 # same as make dev
npm run test:backend:routers        # lightweight backend API checks
npm run build:unified               # build Next.js frontend
```

## BYOK (Bring Your Own Key)

API keys are stored in the browser (localStorage) and sent per-request. The server never persists user keys. Configure keys at http://localhost:3000/settings or pass via `api_key` in request body.

## License

MIT
