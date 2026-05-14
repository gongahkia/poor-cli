from api.routers.benchmarks import router as benchmarks_router
from api.routers.chat import router as chat_router
from api.routers.clauses import router as clauses_router
from api.routers.compliance import router as compliance_router
from api.routers.contracts import router as contracts_router
from api.routers.documents import router as documents_router
from api.routers.glossary import router as glossary_router
from api.routers.health import router as health_router
from api.routers.jurisdictions import router as jurisdictions_router
from api.routers.legal_sources import router as legal_sources_router
from api.routers.ner import router as ner_router
from api.routers.predictions import router as predictions_router
from api.routers.research import router as research_router
from api.routers.rome_statute import router as rome_statute_router
from api.routers.search import router as search_router
from api.routers.statutes import router as statutes_router
from api.routers.templates import router as templates_router

__all__ = [
    "health_router",
    "chat_router",
    "glossary_router",
    "statutes_router",
    "benchmarks_router",
    "ner_router",
    "predictions_router",
    "research_router",
    "rome_statute_router",
    "search_router",
    "contracts_router",
    "clauses_router",
    "templates_router",
    "compliance_router",
    "documents_router",
    "legal_sources_router",
    "jurisdictions_router",
]
