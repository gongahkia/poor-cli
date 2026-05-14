from __future__ import annotations

import importlib
import math
import time
from pathlib import Path
from typing import Any, Iterable

from data.parsers.lecard_parser import discover_lecard_data_root

QDRANT_COLLECTION = "lecard_cases"
DEFAULT_BIENCODER_MODEL = "models/case-retrieval-biencoder"
DEFAULT_CROSS_ENCODER_MODEL = "models/case-retrieval-crossencoder"


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None
    if attr_name is None:
        return module
    return getattr(module, attr_name, None)


def tokenize_chinese(text: str, stopwords: set[str], jieba_module: Any | None = None) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []

    tokens: list[str]
    if jieba_module is not None:
        try:
            tokens = list(jieba_module.lcut(value))
        except Exception:
            tokens = []
    else:
        tokens = list(value)

    filtered = [token.strip() for token in tokens if token and token.strip()]
    return [token for token in filtered if token not in stopwords]


def _fallback_overlap_score(query_tokens: set[str], doc_tokens: set[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = query_tokens & doc_tokens
    if not overlap:
        return 0.0
    return float(len(overlap) / math.sqrt(len(query_tokens) * len(doc_tokens)))


class BM25Retriever:
    def __init__(self, corpus: dict[str, dict[str, Any]], stopwords: set[str]):
        self.corpus = corpus
        self.stopwords = stopwords
        self.doc_ids = list(corpus.keys())
        self.jieba = _optional_import("jieba")
        self._bm25 = None

        self._tokenized_corpus = [
            tokenize_chinese(corpus[case_id].get("ajjbqk", ""), stopwords, self.jieba)
            for case_id in self.doc_ids
        ]
        self._token_set_corpus = [set(tokens) for tokens in self._tokenized_corpus]

        bm25_cls = _optional_import("rank_bm25", "BM25Okapi")
        if bm25_cls is not None:
            try:
                self._bm25 = bm25_cls(self._tokenized_corpus)
            except Exception:
                self._bm25 = None

    def search(self, query_text: str, top_k: int = 100) -> list[tuple[str, float]]:
        query_tokens = tokenize_chinese(query_text, self.stopwords, self.jieba)
        if not query_tokens:
            return []

        if self._bm25 is not None:
            raw_scores = self._bm25.get_scores(query_tokens)
            scored = list(zip(self.doc_ids, [float(score) for score in raw_scores]))
        else:
            query_token_set = set(query_tokens)
            scored = []
            for index, doc_id in enumerate(self.doc_ids):
                score = _fallback_overlap_score(query_token_set, self._token_set_corpus[index])
                scored.append((doc_id, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


class CaseRetrievalPipeline:
    def __init__(
        self,
        corpus: dict[str, dict[str, Any]],
        stopwords: set[str],
        qdrant_url: str = "http://localhost:6333",
        biencoder_model_path: str = DEFAULT_BIENCODER_MODEL,
        cross_encoder_model_path: str = DEFAULT_CROSS_ENCODER_MODEL,
        qdrant_collection: str = QDRANT_COLLECTION,
    ):
        self.corpus = corpus
        self.stopwords = stopwords
        self.bm25 = BM25Retriever(corpus, stopwords)

        self.qdrant_url = qdrant_url
        self.biencoder_model_path = biencoder_model_path
        self.cross_encoder_model_path = cross_encoder_model_path
        self.qdrant_collection = qdrant_collection

        self._dense_model: Any | None = None
        self._cross_encoder: Any | None = None
        self._qdrant_client: Any | None = None

    def _load_dense_components(self) -> tuple[Any | None, Any | None]:
        if self._dense_model is not None and self._qdrant_client is not None:
            return self._dense_model, self._qdrant_client

        sentence_transformer_cls = _optional_import("sentence_transformers", "SentenceTransformer")
        qdrant_client_cls = _optional_import("qdrant_client", "QdrantClient")
        if sentence_transformer_cls is None or qdrant_client_cls is None:
            return None, None

        model_path = Path(self.biencoder_model_path)
        if not model_path.exists() or not model_path.is_dir():
            return None, None

        try:
            self._dense_model = sentence_transformer_cls(str(model_path))
            self._qdrant_client = qdrant_client_cls(url=self.qdrant_url)
        except Exception:
            self._dense_model = None
            self._qdrant_client = None
        return self._dense_model, self._qdrant_client

    def dense_search(self, query_text: str, top_k: int = 100) -> list[tuple[str, float]]:
        model, qdrant = self._load_dense_components()
        if model is None or qdrant is None:
            return []

        try:
            query_vector = model.encode(query_text).tolist()
            if hasattr(qdrant, "search"):
                hits = qdrant.search(
                    collection_name=self.qdrant_collection,
                    query_vector=query_vector,
                    limit=top_k,
                )
            else:
                response = qdrant.query_points(
                    collection_name=self.qdrant_collection,
                    query=query_vector,
                    limit=top_k,
                )
                hits = getattr(response, "points", response)
        except Exception:
            return []

        results: list[tuple[str, float]] = []
        for hit in hits:
            payload = getattr(hit, "payload", {}) or {}
            case_id = str(payload.get("case_id", "")).strip()
            if not case_id:
                continue
            score = float(getattr(hit, "score", 0.0))
            results.append((case_id, score))
        return results

    def _load_cross_encoder(self) -> Any | None:
        if self._cross_encoder is not None:
            return self._cross_encoder

        cross_encoder_cls = _optional_import("sentence_transformers", "CrossEncoder")
        if cross_encoder_cls is None:
            return None

        model_path = Path(self.cross_encoder_model_path)
        if not model_path.exists() or not model_path.is_dir():
            return None

        try:
            self._cross_encoder = cross_encoder_cls(str(model_path))
        except Exception:
            self._cross_encoder = None
        return self._cross_encoder

    @staticmethod
    def _rrf_merge(rankings: Iterable[list[tuple[str, float]]], top_k: int) -> list[tuple[str, float]]:
        rrf_k = 60
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, (case_id, _) in enumerate(ranking):
                scores[case_id] = scores.get(case_id, 0.0) + 1.0 / (rrf_k + rank + 1)
        merged = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return merged[:top_k]

    def _rerank(
        self,
        query_text: str,
        case_ids: list[str],
        base_scores: dict[str, float],
        top_k: int,
    ) -> list[tuple[str, float]]:
        cross_encoder = self._load_cross_encoder()
        if cross_encoder is None:
            ranked = sorted(
                [(case_id, base_scores.get(case_id, 0.0)) for case_id in case_ids],
                key=lambda item: item[1],
                reverse=True,
            )
            return ranked[:top_k]

        pairs = [(query_text, self.corpus[case_id].get("ajjbqk", "")) for case_id in case_ids if case_id in self.corpus]
        if not pairs:
            return []

        try:
            scores = cross_encoder.predict(pairs)
        except Exception:
            ranked = sorted(
                [(case_id, base_scores.get(case_id, 0.0)) for case_id in case_ids],
                key=lambda item: item[1],
                reverse=True,
            )
            return ranked[:top_k]

        reranked = []
        for idx, case_id in enumerate(case_ids):
            if idx >= len(scores):
                break
            reranked.append((case_id, float(scores[idx])))
        reranked.sort(key=lambda item: item[1], reverse=True)
        return reranked[:top_k]

    def search(
        self,
        query_text: str,
        top_k: int = 30,
        stages: list[str] | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        normalized_stages = stages or ["bm25", "dense", "rerank"]

        bm25_results: list[tuple[str, float]] = []
        dense_results: list[tuple[str, float]] = []

        if "bm25" in normalized_stages:
            bm25_results = self.bm25.search(query_text, top_k=100)
        if "dense" in normalized_stages:
            dense_results = self.dense_search(query_text, top_k=100)

        combined_rank = self._rrf_merge([bm25_results, dense_results], top_k=200)
        if not combined_rank and bm25_results:
            combined_rank = bm25_results[:200]
        if not combined_rank and dense_results:
            combined_rank = dense_results[:200]

        candidate_ids = [case_id for case_id, _ in combined_rank if case_id in self.corpus]
        base_scores = {case_id: score for case_id, score in combined_rank}

        final_stage = "bm25"
        if "rerank" in normalized_stages and candidate_ids:
            reranked = self._rerank(query_text, candidate_ids, base_scores, top_k=top_k)
            final_rank = reranked
            final_stage = "rerank"
        else:
            final_rank = combined_rank[:top_k]
            if "dense" in normalized_stages:
                final_stage = "dense"

        results = []
        for case_id, score in final_rank:
            row = self.corpus.get(case_id)
            if row is None:
                continue
            results.append(
                {
                    "case_id": case_id,
                    "case_name": row.get("ajName", ""),
                    "facts": str(row.get("ajjbqk", ""))[:500],
                    "judgment": str(row.get("pjjg", ""))[:300],
                    "charges": row.get("charges", []),
                    "relevance_score": float(score),
                    "retrieval_stage": final_stage,
                }
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "results": results,
            "retrieval_info": {
                "stages_used": normalized_stages,
                "bm25_candidates": len(bm25_results),
                "dense_candidates": len(dense_results),
                "total_time_ms": elapsed_ms,
            },
        }


def index_corpus_to_qdrant(
    corpus: dict[str, dict[str, Any]],
    model_path: str | Path = DEFAULT_BIENCODER_MODEL,
    qdrant_url: str = "http://localhost:6333",
    collection_name: str = QDRANT_COLLECTION,
    batch_size: int = 100,
) -> int:
    sentence_transformer_cls = _optional_import("sentence_transformers", "SentenceTransformer")
    qdrant_client_cls = _optional_import("qdrant_client", "QdrantClient")
    distance_cls = _optional_import("qdrant_client.models", "Distance")
    vector_params_cls = _optional_import("qdrant_client.models", "VectorParams")
    point_struct_cls = _optional_import("qdrant_client.models", "PointStruct")

    if (
        sentence_transformer_cls is None
        or qdrant_client_cls is None
        or distance_cls is None
        or vector_params_cls is None
        or point_struct_cls is None
    ):
        raise RuntimeError("sentence-transformers and qdrant-client are required for dense indexing")

    model_dir = Path(model_path)
    if not model_dir.exists() or not model_dir.is_dir():
        raise RuntimeError(f"bi-encoder model path not found: {model_dir}")

    model = sentence_transformer_cls(str(model_dir))
    client = qdrant_client_cls(url=qdrant_url)

    case_ids = list(corpus.keys())
    texts = [str(corpus[case_id].get("ajjbqk", "")) for case_id in case_ids]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)

    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=vector_params_cls(size=len(embeddings[0]), distance=distance_cls.COSINE),
    )

    total = 0
    for start in range(0, len(case_ids), batch_size):
        end = min(start + batch_size, len(case_ids))
        points = []
        for idx in range(start, end):
            case_id = case_ids[idx]
            row = corpus[case_id]
            points.append(
                point_struct_cls(
                    id=idx + 1,
                    vector=embeddings[idx].tolist(),
                    payload={
                        "case_id": case_id,
                        "ajId": row.get("ajId", ""),
                        "ajName": row.get("ajName", ""),
                        "charges": row.get("charges", []),
                        "text_snippet": str(row.get("ajjbqk", ""))[:300],
                    },
                )
            )
        client.upsert(collection_name=collection_name, points=points)
        total += len(points)

    client.close()
    return total


def default_lecard_data_root() -> Path:
    return discover_lecard_data_root()
