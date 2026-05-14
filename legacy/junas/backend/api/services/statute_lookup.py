from __future__ import annotations

import importlib
from typing import Any

INDEX_NAME = "junas_statutes"
COLLECTION_NAME = "junas_statutes"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

class StatuteService:
    _embedder: Any = None

    def __init__(self, es: Any, qdrant: Any):
        self.es = es
        self.qdrant = qdrant

    @classmethod
    def _get_embedder(cls) -> Any:
        if cls._embedder is not None:
            return cls._embedder
        try:
            module = importlib.import_module("sentence_transformers")
        except ModuleNotFoundError as exc:
            raise RuntimeError("sentence-transformers is not installed") from exc

        sentence_transformer_cls = getattr(module, "SentenceTransformer", None)
        if sentence_transformer_cls is None:
            raise RuntimeError("sentence-transformers is not installed")
        cls._embedder = sentence_transformer_cls(EMBEDDING_MODEL_NAME)
        return cls._embedder

    async def _keyword_hits(self, query: str, chapter: str | None, size: int) -> tuple[list[dict], int]:
        filters: list[dict[str, Any]] = []
        if chapter:
            filters.append({"term": {"chapter_number": chapter}})

        body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["name^3", "text_plain"],
                                "type": "best_fields",
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
            "size": size,
        }
        response = await self.es.search(index=INDEX_NAME, body=body)
        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {}).get("value", 0)

        result = []
        for hit in hits:
            source = hit.get("_source", {})
            result.append(
                {
                    "number": source.get("number", ""),
                    "name": source.get("name", ""),
                    "chapter_number": source.get("chapter_number", ""),
                    "text_html": source.get("text_html", ""),
                    "text_plain": source.get("text_plain", ""),
                    "cross_references": source.get("cross_references", []),
                    "score": float(hit.get("_score", 0.0)),
                    "search_mode": "keyword",
                }
            )

        return result, total

    async def _semantic_hits(self, query: str, chapter: str | None, size: int) -> list[dict]:
        if self.qdrant is None:
            return []

        embedder = self._get_embedder()
        query_vector = embedder.encode(query).tolist()

        if hasattr(self.qdrant, "search"):
            raw_hits = await self.qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=size,
            )
        elif hasattr(self.qdrant, "query_points"):
            response = await self.qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=size,
            )
            raw_hits = getattr(response, "points", response)
        else:
            return []

        scored_by_number: dict[str, float] = {}
        for hit in raw_hits:
            payload = getattr(hit, "payload", None) or {}
            number = str(payload.get("number", ""))
            if not number:
                continue
            score = float(getattr(hit, "score", 0.0))
            if number not in scored_by_number or score > scored_by_number[number]:
                scored_by_number[number] = score

        sections = await self._fetch_sections(list(scored_by_number.keys()))
        results = []
        for section in sections:
            if chapter and section.get("chapter_number") != chapter:
                continue
            number = str(section.get("number", ""))
            results.append(
                {
                    **section,
                    "score": scored_by_number.get(number, 0.0),
                    "search_mode": "semantic",
                }
            )
        results.sort(key=lambda row: row["score"], reverse=True)
        return results[:size]

    async def _fetch_sections(self, numbers: list[str]) -> list[dict]:
        if not numbers:
            return []

        body = {
            "query": {"terms": {"number": numbers}},
            "size": len(numbers),
        }
        response = await self.es.search(index=INDEX_NAME, body=body)
        hits = response.get("hits", {}).get("hits", [])
        by_number = {hit.get("_source", {}).get("number", ""): hit.get("_source", {}) for hit in hits}

        ordered = []
        for number in numbers:
            source = by_number.get(number)
            if source:
                ordered.append(source)
        return ordered

    def _rrf_merge(self, keyword_hits: list[dict], semantic_hits: list[dict], top_k: int) -> list[tuple[str, float]]:
        rrf_k = 60
        scores: dict[str, float] = {}

        for rank, hit in enumerate(keyword_hits):
            number = hit.get("number", "")
            if number:
                scores[number] = scores.get(number, 0.0) + 1.0 / (rrf_k + rank + 1)

        for rank, hit in enumerate(semantic_hits):
            number = hit.get("number", "")
            if number:
                scores[number] = scores.get(number, 0.0) + 1.0 / (rrf_k + rank + 1)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    async def search(
        self,
        q: str,
        chapter: str | None,
        mode: str,
        page: int,
        per_page: int,
    ) -> dict[str, Any]:
        fetch_size = page * per_page

        if mode == "keyword":
            keyword_hits, total = await self._keyword_hits(q, chapter, fetch_size)
            selected = keyword_hits[(page - 1) * per_page : page * per_page]
            return {"total": total, "results": selected}

        if mode == "semantic":
            semantic_hits = await self._semantic_hits(q, chapter, fetch_size)
            selected = semantic_hits[(page - 1) * per_page : page * per_page]
            return {"total": len(semantic_hits), "results": selected}

        keyword_hits, _ = await self._keyword_hits(q, chapter, fetch_size * 2)
        semantic_hits = await self._semantic_hits(q, chapter, fetch_size * 2)
        ranked = self._rrf_merge(keyword_hits, semantic_hits, fetch_size)
        numbers = [number for number, _ in ranked]
        sections = await self._fetch_sections(numbers)
        score_by_number = {number: score for number, score in ranked}

        fused = []
        for section in sections:
            number = section.get("number", "")
            fused.append(
                {
                    **section,
                    "score": score_by_number.get(number, 0.0),
                    "search_mode": "hybrid",
                }
            )

        selected = fused[(page - 1) * per_page : page * per_page]
        return {"total": len(fused), "results": selected}

    async def get_section(self, number: str) -> dict[str, Any] | None:
        body = {
            "query": {"term": {"number": number}},
            "size": 1,
        }
        response = await self.es.search(index=INDEX_NAME, body=body)
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return None

        source = hits[0].get("_source", {})
        referenced_by_body = {
            "query": {"terms": {"cross_references": [number]}},
            "_source": ["number"],
            "size": 2000,
        }
        referenced_by_response = await self.es.search(index=INDEX_NAME, body=referenced_by_body)
        refs = referenced_by_response.get("hits", {}).get("hits", [])
        referenced_by = sorted({hit.get("_source", {}).get("number", "") for hit in refs if hit.get("_source")})

        return {
            **source,
            "referenced_by": referenced_by,
        }

    async def list_chapters(self) -> list[dict[str, Any]]:
        body = {
            "size": 0,
            "aggs": {
                "chapters": {
                    "terms": {"field": "chapter_number", "size": 1000},
                    "aggs": {
                        "first_section": {
                            "top_hits": {
                                "_source": ["number"],
                                "size": 1,
                                "sort": [{"number": {"order": "asc"}}],
                            }
                        }
                    },
                }
            },
        }
        response = await self.es.search(index=INDEX_NAME, body=body)
        buckets = response.get("aggregations", {}).get("chapters", {}).get("buckets", [])

        chapters = []
        for bucket in buckets:
            first_hit = bucket.get("first_section", {}).get("hits", {}).get("hits", [])
            first_section = ""
            if first_hit:
                first_section = first_hit[0].get("_source", {}).get("number", "")
            chapters.append(
                {
                    "chapter_number": bucket.get("key", ""),
                    "section_count": bucket.get("doc_count", 0),
                    "first_section": first_section,
                }
            )

        chapters.sort(key=lambda row: row["chapter_number"])
        return chapters

    async def get_chapter_sections(self, chapter_number: str) -> list[dict[str, str]]:
        body = {
            "query": {"term": {"chapter_number": chapter_number}},
            "_source": ["number", "name"],
            "size": 5000,
            "sort": [{"number": {"order": "asc"}}],
        }
        response = await self.es.search(index=INDEX_NAME, body=body)
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "number": hit.get("_source", {}).get("number", ""),
                "name": hit.get("_source", {}).get("name", ""),
            }
            for hit in hits
        ]
