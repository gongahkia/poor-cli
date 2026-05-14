import importlib
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.celery_app import celery
from api.config import get_settings
from api.routers import (
    benchmarks_router,
    chat_router,
    clauses_router,
    compliance_router,
    contracts_router,
    documents_router,
    glossary_router,
    health_router,
    jurisdictions_router,
    legal_sources_router,
    ner_router,
    predictions_router,
    research_router,
    rome_statute_router,
    search_router,
    statutes_router,
    templates_router,
)
from api.security import SimpleRateLimiter, authorize_request
from api.services.benchmarks import BenchmarkService
from api.services.contract_classifier import create_contract_classifier
from api.services.court_predictor import create_court_predictor
from api.services.entity_extractor import create_entity_extractor
from api.services.readiness import collect_service_health
from api.services.rome_statute import create_rome_statute_service
from api.services.tos_scanner import create_tos_scanner


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
        return None
    if attr_name is None:
        return module
    return getattr(module, attr_name, None)


asyncpg_module = _optional_import("asyncpg")
elasticsearch_client_cls = _optional_import("elasticsearch", "AsyncElasticsearch")
qdrant_client_cls = _optional_import("qdrant_client", "AsyncQdrantClient")
redis_module = _optional_import("redis", "asyncio")

logger = logging.getLogger(__name__)
settings = get_settings()


tags_metadata = [
    {"name": "health", "description": "Service health, readiness, and runtime metrics"},
    {"name": "chat", "description": "BYOK streaming AI chat with multiple providers"},
    {"name": "glossary", "description": "Legal glossary lookup and comparison"},
    {"name": "statutes", "description": "Statute search and browsing"},
    {"name": "search", "description": "Case-law retrieval"},
    {"name": "research", "description": "RAG-powered legal assistant"},
    {"name": "contracts", "description": "Contract and ToS analysis"},
    {"name": "clauses", "description": "Legal clause library with tone variants"},
    {"name": "templates", "description": "Legal document templates with variable rendering"},
    {"name": "compliance", "description": "Compliance checking engine"},
    {"name": "documents", "description": "PDF/DOCX document parsing"},
    {"name": "legal-sources", "description": "Legal source scraping (SSO, CommonLII)"},
    {"name": "jurisdictions", "description": "Multi-jurisdiction registry"},
    {"name": "ner", "description": "Legal named entity extraction"},
    {"name": "predictions", "description": "Court decision prediction suite"},
    {"name": "benchmarks", "description": "LexGLUE benchmark dashboard"},
    {"name": "rome-statute", "description": "Rome Statute knowledge base"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    existing_rome_statute_service = getattr(app.state, "rome_statute_service", None)
    app.state.start_time = time.time()
    app.state.request_count = 0
    app.state.rate_limiter = SimpleRateLimiter(settings)
    app.state.pg_pool = None
    app.state.entity_extractor = None
    app.state.case_retrieval_service = None
    app.state.contract_classifier = None
    app.state.tos_scanner = None
    app.state.court_predictor = None
    app.state.benchmark_service = None
    app.state.legal_qa_service = None
    app.state.rome_statute_service = existing_rome_statute_service
    app.state.elasticsearch = (
        elasticsearch_client_cls(settings.elasticsearch_url) if elasticsearch_client_cls else None
    )
    app.state.qdrant = qdrant_client_cls(url=settings.qdrant_url) if qdrant_client_cls else None
    app.state.redis = (
        redis_module.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        if redis_module
        else None
    )

    if asyncpg_module is not None:
        try:
            app.state.pg_pool = await asyncpg_module.create_pool(
                settings.database_url, min_size=1, max_size=5, timeout=3
            )
        except Exception as exc:  # pragma: no cover - depends on local infra
            logger.warning("postgres startup check failed: %s", exc)
    else:
        logger.warning("asyncpg is not installed; postgres checks disabled")

    try:
        app.state.entity_extractor = create_entity_extractor(
            model_path=settings.ner_model_path,
            gazetteer_dir=settings.ner_gazetteer_dir,
            multilingual_model_path=settings.ner_multilingual_model_path,
        )
    except Exception as exc:  # pragma: no cover - depends on local model files
        logger.warning("ner model startup load failed: %s", exc)

    try:
        app.state.contract_classifier = create_contract_classifier(settings.ledgar_model_path)
    except Exception as exc:  # pragma: no cover - depends on local model files
        logger.warning("contract classifier startup load failed: %s", exc)

    try:
        app.state.tos_scanner = create_tos_scanner(settings.unfair_tos_model_path)
    except Exception as exc:  # pragma: no cover - depends on local model files
        logger.warning("tos scanner startup load failed: %s", exc)

    try:
        app.state.court_predictor = create_court_predictor(
            scotus_model_path=settings.scotus_model_path,
            ecthr_violation_model_path=settings.ecthr_violation_model_path,
            ecthr_alleged_model_path=settings.ecthr_alleged_model_path,
            casehold_model_path=settings.casehold_model_path,
            eurlex_model_path=settings.eurlex_model_path,
        )
    except Exception as exc:  # pragma: no cover - depends on local model files
        logger.warning("court predictor startup load failed: %s", exc)

    if app.state.rome_statute_service is None:
        try:
            app.state.rome_statute_service = create_rome_statute_service(settings.rome_statute_data_path)
        except Exception as exc:  # pragma: no cover - depends on local files
            logger.warning("rome statute startup load failed: %s", exc)

    app.state.benchmark_service = BenchmarkService(
        database_url=settings.database_url,
        pg_pool=app.state.pg_pool,
        celery_app=celery,
    )
    await app.state.benchmark_service.seed_published_baselines()

    startup_status = await collect_service_health(app)
    app.state.startup_status = startup_status
    logger.info("startup readiness: %s", startup_status)

    try:
        yield
    finally:
        if app.state.pg_pool is not None:
            await app.state.pg_pool.close()
        if app.state.elasticsearch is not None:
            await app.state.elasticsearch.close()
        if app.state.qdrant is not None:
            await app.state.qdrant.close()
        if app.state.redis is not None:
            await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Junas API",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "Legal AI platform providing multi-jurisdiction retrieval, legal NER, "
            "contract analysis, BYOK AI chat, compliance checking, clause & template libraries, "
            "benchmark evaluation, and court decision prediction."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=tags_metadata,
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error path=%s error=%s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if settings.debug else None,
            },
        )

    @app.middleware("http")
    async def auth_rate_limit_and_log(request: Request, call_next: Any) -> Any:
        start = time.time()
        app.state.request_count = int(getattr(app.state, "request_count", 0)) + 1

        try:
            authorize_request(request, settings)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        limiter: SimpleRateLimiter | None = getattr(app.state, "rate_limiter", None)
        decision = limiter.check(request) if limiter is not None else None
        if decision is not None and not decision.allowed:
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": str(decision.retry_after),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                },
                content={"detail": "Rate limit exceeded"},
            )

        response = await call_next(request)

        if decision is not None and decision.limit > 0:
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)

        duration_ms = round((time.time() - start) * 1000)
        logger.info(
            "request path=%s method=%s status=%s duration_ms=%s",
            request.url.path,
            request.method,
            response.status_code,
            duration_ms,
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api/v1", tags=["health"])
    app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
    app.include_router(benchmarks_router, prefix="/api/v1", tags=["benchmarks"])
    app.include_router(glossary_router, prefix="/api/v1", tags=["glossary"])
    app.include_router(statutes_router, prefix="/api/v1", tags=["statutes"])
    app.include_router(research_router, prefix="/api/v1", tags=["research"])
    app.include_router(predictions_router, prefix="/api/v1", tags=["predictions"])
    app.include_router(rome_statute_router, prefix="/api/v1", tags=["rome-statute"])
    app.include_router(ner_router, prefix="/api/v1", tags=["ner"])
    app.include_router(search_router, prefix="/api/v1", tags=["search"])
    app.include_router(contracts_router, prefix="/api/v1", tags=["contracts"])
    app.include_router(clauses_router, prefix="/api/v1", tags=["clauses"])
    app.include_router(templates_router, prefix="/api/v1", tags=["templates"])
    app.include_router(compliance_router, prefix="/api/v1", tags=["compliance"])
    app.include_router(documents_router, prefix="/api/v1", tags=["documents"])
    app.include_router(legal_sources_router, prefix="/api/v1", tags=["legal-sources"])
    app.include_router(jurisdictions_router, prefix="/api/v1", tags=["jurisdictions"])
    return app


app = create_app()
