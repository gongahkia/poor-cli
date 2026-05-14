"""Service package for API business logic."""

from api.services.benchmarks import BenchmarkService
from api.services.case_retrieval import CaseRetrievalService, create_case_retrieval_service
from api.services.citation_verifier import CitationVerifier
from api.services.contract_classifier import ContractClassifier, create_contract_classifier
from api.services.court_predictor import CourtPredictor, create_court_predictor
from api.services.entity_extractor import EntityExtractor, create_entity_extractor
from api.services.glossary_lookup import GlossaryService
from api.services.legal_qa import ConversationStore, LegalQAService
from api.services.llm_client import LLMClient, get_llm_client, get_llm_model_name
from api.services.retrieval_orchestrator import RetrievedChunk, RetrievalOrchestrator, SourceType
from api.services.rome_statute import RomeStatuteService, create_rome_statute_service
from api.services.statute_lookup import StatuteService
from api.services.tos_scanner import ToSScanner, create_tos_scanner

__all__ = [
    "BenchmarkService",
    "CaseRetrievalService",
    "create_case_retrieval_service",
    "CitationVerifier",
    "ContractClassifier",
    "create_contract_classifier",
    "CourtPredictor",
    "create_court_predictor",
    "ConversationStore",
    "EntityExtractor",
    "create_entity_extractor",
    "GlossaryService",
    "LegalQAService",
    "LLMClient",
    "RetrievedChunk",
    "RetrievalOrchestrator",
    "SourceType",
    "RomeStatuteService",
    "create_rome_statute_service",
    "StatuteService",
    "ToSScanner",
    "create_tos_scanner",
    "get_llm_client",
    "get_llm_model_name",
]
