from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class SourceType(str, Enum):
    STATUTE = "statute"
    GLOSSARY = "glossary"
    CASE_LAW = "case_law"
    TREATY = "treaty"


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source_type: SourceType
    source_id: str
    metadata: dict[str, Any]
    score: float


class RetrievalOrchestrator:
    _embedder: Any = None

    def __init__(self, es_client: Any, qdrant_client: Any, case_service: Any | None = None):
        self.es = es_client
        self.qdrant = qdrant_client
        self.case_service = case_service

    @classmethod
    def _get_embedder(cls) -> Any:
        if cls._embedder is not None:
            return cls._embedder

        module = importlib.import_module("sentence_transformers")
        sentence_transformer_cls = getattr(module, "SentenceTransformer", None)
        if sentence_transformer_cls is None:
            raise RuntimeError("sentence-transformers is unavailable")

        cls._embedder = sentence_transformer_cls("sentence-transformers/all-MiniLM-L6-v2")
        return cls._embedder

    async def retrieve(
        self,
        query: str,
        sources: list[SourceType] | None = None,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        selected_sources = sources or [SourceType.STATUTE, SourceType.GLOSSARY]
        chunks: list[RetrievedChunk] = []

        if SourceType.STATUTE in selected_sources:
            es_hits = await self._search_statutes_es(query, top_k * 2)
            vector_hits = await self._search_statutes_vector(query, top_k * 2)
            chunks.extend(self._rrf_merge(es_hits, vector_hits, top_k * 2))

        if SourceType.GLOSSARY in selected_sources:
            chunks.extend(await self._search_glossary(query, top_k))

        if SourceType.CASE_LAW in selected_sources:
            chunks.extend(await self._search_case_law(query, top_k))

        if SourceType.TREATY in selected_sources:
            chunks.extend(await self._search_treaty(query, top_k))

        unique_chunks = self._dedupe_keep_best(chunks)
        unique_chunks.sort(key=lambda item: item.score, reverse=True)
        return unique_chunks[:top_k]

    async def _search_statutes_es(self, query: str, limit: int) -> list[RetrievedChunk]:
        if self.es is None:
            return []

        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "text_plain^2", "cross_references"],
                    "type": "best_fields",
                }
            },
            "size": limit,
        }
        response = await self.es.search(index="junas_statutes", body=body)
        hits = response.get("hits", {}).get("hits", [])

        chunks: list[RetrievedChunk] = []
        for hit in hits:
            source = hit.get("_source", {})
            number = str(source.get("number", "")).strip()
            if not number:
                continue

            chunks.append(
                RetrievedChunk(
                    text=str(source.get("text_plain", ""))[:1600],
                    source_type=SourceType.STATUTE,
                    source_id=f"ORS {number}",
                    metadata={
                        "number": number,
                        "name": source.get("name", ""),
                        "chapter": source.get("chapter_number", ""),
                    },
                    score=float(hit.get("_score", 0.0)),
                )
            )

        return chunks

    async def _search_statutes_vector(self, query: str, limit: int) -> list[RetrievedChunk]:
        if self.qdrant is None:
            return []

        try:
            embedder = self._get_embedder()
        except Exception:
            return []

        raw_vector = embedder.encode(query)
        if hasattr(raw_vector, "tolist"):
            query_vector = raw_vector.tolist()
        else:
            query_vector = list(raw_vector)

        try:
            if hasattr(self.qdrant, "search"):
                hits = await self.qdrant.search(
                    collection_name="junas_statutes",
                    query_vector=query_vector,
                    limit=limit,
                )
            elif hasattr(self.qdrant, "query_points"):
                response = await self.qdrant.query_points(
                    collection_name="junas_statutes",
                    query=query_vector,
                    limit=limit,
                )
                hits = getattr(response, "points", response)
            else:
                return []
        except Exception:
            return []

        chunks: list[RetrievedChunk] = []
        for hit in hits:
            payload = getattr(hit, "payload", None) or {}
            number = str(payload.get("number", "")).strip()
            if not number:
                continue

            chunks.append(
                RetrievedChunk(
                    text=str(payload.get("text_snippet", "")),
                    source_type=SourceType.STATUTE,
                    source_id=f"ORS {number}",
                    metadata={
                        "number": number,
                        "name": payload.get("name", ""),
                        "chapter": payload.get("chapter_number", ""),
                    },
                    score=float(getattr(hit, "score", 0.0)),
                )
            )

        return chunks

    async def _search_glossary(self, query: str, limit: int) -> list[RetrievedChunk]:
        if self.es is None:
            return []

        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["phrase^3", "definition_text"],
                    "type": "best_fields",
                }
            },
            "size": limit,
        }
        response = await self.es.search(index="junas_glossary", body=body)
        hits = response.get("hits", {}).get("hits", [])

        chunks: list[RetrievedChunk] = []
        for hit in hits:
            source = hit.get("_source", {})
            phrase = str(source.get("phrase", "")).strip()
            if not phrase:
                continue

            definition = str(source.get("definition_text", "")).strip()
            chunks.append(
                RetrievedChunk(
                    text=f"{phrase}: {definition}" if definition else phrase,
                    source_type=SourceType.GLOSSARY,
                    source_id=phrase,
                    metadata={
                        "jurisdiction": source.get("jurisdiction", ""),
                        "domain": source.get("domain", ""),
                        "source_title": source.get("source_title", ""),
                    },
                    score=float(hit.get("_score", 0.0)),
                )
            )

        return chunks

    async def _search_treaty(self, query: str, limit: int) -> list[RetrievedChunk]:
        if self.es is None:
            return []

        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["article_title^3", "text^2", "part_title"],
                    "type": "best_fields",
                }
            },
            "size": limit,
        }

        try:
            response = await self.es.search(index="junas_rome_statute", body=body)
        except Exception:
            return []

        hits = response.get("hits", {}).get("hits", [])
        chunks: list[RetrievedChunk] = []
        for hit in hits:
            source = hit.get("_source", {})
            article_number = str(source.get("article_number", "")).strip()
            if not article_number:
                continue

            article_title = str(source.get("article_title", "")).strip()
            text = str(source.get("text", "")).strip()
            part_number = str(source.get("part_number", "")).strip()

            chunks.append(
                RetrievedChunk(
                    text=text[:1600],
                    source_type=SourceType.TREATY,
                    source_id=f"Rome Statute Art. {article_number}",
                    metadata={
                        "article_number": article_number,
                        "article_title": article_title,
                        "part_number": part_number,
                        "part_title": source.get("part_title", ""),
                    },
                    score=float(hit.get("_score", 0.0)),
                )
            )

        return chunks

    async def _search_case_law(self, query: str, limit: int) -> list[RetrievedChunk]:
        if self.case_service is not None:
            try:
                payload = self.case_service.search_cases(
                    query=query,
                    top_k=limit,
                    stages=["bm25", "dense", "rerank"],
                    include_scores=True,
                )
            except Exception:
                payload = None

            if isinstance(payload, dict):
                results = payload.get("results", [])
                chunks: list[RetrievedChunk] = []
                for row in results:
                    case_id = str(row.get("case_id", "")).strip()
                    if not case_id:
                        continue
                    facts = str(row.get("facts", "")).strip()
                    judgment = str(row.get("judgment", "")).strip()
                    text = facts if facts else judgment
                    if facts and judgment:
                        text = f"{facts[:800]}\n\nJudgment: {judgment[:400]}"

                    chunks.append(
                        RetrievedChunk(
                            text=text,
                            source_type=SourceType.CASE_LAW,
                            source_id=case_id,
                            metadata={
                                "case_name": row.get("case_name", ""),
                                "charges": row.get("charges", []),
                                "retrieval_stage": row.get("retrieval_stage", ""),
                            },
                            score=float(row.get("relevance_score", 0.0) or 0.0),
                        )
                    )
                return chunks

        if self.qdrant is None:
            return []

        try:
            embedder = self._get_embedder()
        except Exception:
            return []

        raw_vector = embedder.encode(query)
        if hasattr(raw_vector, "tolist"):
            query_vector = raw_vector.tolist()
        else:
            query_vector = list(raw_vector)

        try:
            if hasattr(self.qdrant, "search"):
                hits = await self.qdrant.search(
                    collection_name="lecard_cases",
                    query_vector=query_vector,
                    limit=limit,
                )
            elif hasattr(self.qdrant, "query_points"):
                response = await self.qdrant.query_points(
                    collection_name="lecard_cases",
                    query=query_vector,
                    limit=limit,
                )
                hits = getattr(response, "points", response)
            else:
                return []
        except Exception:
            return []

        vector_chunks: list[RetrievedChunk] = []
        for hit in hits:
            payload = getattr(hit, "payload", None) or {}
            case_id = str(payload.get("ajId", "")).strip()
            if not case_id:
                continue

            vector_chunks.append(
                RetrievedChunk(
                    text=str(payload.get("text_snippet", "")),
                    source_type=SourceType.CASE_LAW,
                    source_id=case_id,
                    metadata={
                        "case_name": payload.get("ajName", ""),
                    },
                    score=float(getattr(hit, "score", 0.0)),
                )
            )

        return vector_chunks

    @staticmethod
    def _rrf_merge(es_hits: list[RetrievedChunk], vector_hits: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        rrf_k = 60
        scores: dict[str, float] = {}
        chunks_by_id: dict[str, RetrievedChunk] = {}

        def _apply(hits: Iterable[RetrievedChunk]) -> None:
            for rank, chunk in enumerate(hits):
                score = 1.0 / (rrf_k + rank + 1)
                scores[chunk.source_id] = scores.get(chunk.source_id, 0.0) + score
                chunks_by_id[chunk.source_id] = chunk

        _apply(es_hits)
        _apply(vector_hits)

        merged = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                text=chunks_by_id[source_id].text,
                source_type=chunks_by_id[source_id].source_type,
                source_id=source_id,
                metadata=chunks_by_id[source_id].metadata,
                score=float(score),
            )
            for source_id, score in merged
        ]

    @staticmethod
    def _dedupe_keep_best(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        best: dict[tuple[str, str], RetrievedChunk] = {}
        for chunk in chunks:
            key = (chunk.source_type.value, chunk.source_id)
            previous = best.get(key)
            if previous is None or chunk.score > previous.score:
                best[key] = chunk
        return list(best.values())
