from __future__ import annotations

from typing import Any

JURISDICTION_NAMES = {
    "AUS": "Australia",
    "CAN": "Canada",
    "GBR": "United Kingdom",
    "IRL": "Ireland",
    "NZL": "New Zealand",
    "USA": "United States",
    "USA-CA": "United States (California)",
}


class GlossaryService:
    def __init__(self, es: Any):
        self.es = es
        self.index = "junas_glossary"

    async def search(
        self,
        q: str,
        jurisdiction: list[str] | None,
        domain: list[str] | None,
        page: int,
        per_page: int,
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if jurisdiction:
            filters.append({"terms": {"jurisdiction": jurisdiction}})
        if domain:
            filters.append({"terms": {"domain": domain}})

        body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": q,
                                "fields": ["phrase^3", "definition_text"],
                                "type": "best_fields",
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
            "aggs": {
                "jurisdictions": {"terms": {"field": "jurisdiction", "size": 25}},
                "domains": {"terms": {"field": "domain", "size": 25}},
            },
            "from": (page - 1) * per_page,
            "size": per_page,
        }
        response = await self.es.search(index=self.index, body=body)

        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {}).get("value", 0)

        results = []
        for hit in hits:
            source = hit.get("_source", {})
            results.append(
                {
                    "phrase": source.get("phrase", ""),
                    "definition_html": source.get("definition_html", ""),
                    "definition_text": source.get("definition_text", ""),
                    "jurisdiction": source.get("jurisdiction", ""),
                    "domain": source.get("domain", ""),
                    "source_title": source.get("source_title", ""),
                    "source_url": source.get("source_url", ""),
                    "score": hit.get("_score", 0.0),
                }
            )

        jurisdiction_buckets = response.get("aggregations", {}).get("jurisdictions", {}).get("buckets", [])
        domain_buckets = response.get("aggregations", {}).get("domains", {}).get("buckets", [])

        aggregations = {
            "jurisdictions": {bucket["key"]: bucket["doc_count"] for bucket in jurisdiction_buckets},
            "domains": {bucket["key"]: bucket["doc_count"] for bucket in domain_buckets},
        }

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "results": results,
            "aggregations": aggregations,
        }

    async def get_term(self, phrase: str) -> dict[str, Any]:
        body = {
            "query": {
                "term": {
                    "phrase.keyword": {
                        "value": phrase,
                        "case_insensitive": True,
                    }
                }
            },
            "size": 200,
            "sort": [{"jurisdiction": {"order": "asc"}}, {"domain": {"order": "asc"}}],
        }
        response = await self.es.search(index=self.index, body=body)
        hits = response.get("hits", {}).get("hits", [])

        definitions = []
        canonical_phrase = phrase
        for hit in hits:
            source = hit.get("_source", {})
            if source.get("phrase") and canonical_phrase == phrase:
                canonical_phrase = source.get("phrase")
            definitions.append(
                {
                    "jurisdiction": source.get("jurisdiction", ""),
                    "domain": source.get("domain", ""),
                    "definition_html": source.get("definition_html", ""),
                    "definition_text": source.get("definition_text", ""),
                    "source_title": source.get("source_title", ""),
                    "source_url": source.get("source_url", ""),
                }
            )

        return {"phrase": canonical_phrase, "definitions": definitions}

    async def compare(self, term: str, jurisdictions: list[str] | None) -> dict[str, Any]:
        term_data = await self.get_term(term)
        definitions = term_data["definitions"]

        available_in = sorted({item["jurisdiction"] for item in definitions})
        target = jurisdictions or sorted(JURISDICTION_NAMES.keys())
        filtered = [item for item in definitions if item["jurisdiction"] in target]
        not_found_in = sorted(set(target) - {item["jurisdiction"] for item in filtered})

        comparisons = [
            {
                "jurisdiction": item["jurisdiction"],
                "domain": item["domain"],
                "definition_text": item["definition_text"],
            }
            for item in filtered
        ]

        return {
            "term": term_data["phrase"],
            "comparisons": comparisons,
            "available_in": available_in,
            "not_found_in": not_found_in,
        }

    async def suggest(self, prefix: str, size: int) -> list[str]:
        body = {
            "suggest": {
                "phrase-suggest": {
                    "prefix": prefix,
                    "completion": {
                        "field": "phrase.suggest",
                        "size": size,
                        "skip_duplicates": True,
                    },
                }
            }
        }
        response = await self.es.search(index=self.index, body=body)
        suggestion_groups = response.get("suggest", {}).get("phrase-suggest", [])
        if not suggestion_groups:
            return []
        options = suggestion_groups[0].get("options", [])
        return [option.get("text", "") for option in options if option.get("text")]

    async def get_jurisdictions(self) -> list[dict[str, Any]]:
        body = {
            "size": 0,
            "aggs": {
                "jurisdictions": {
                    "terms": {"field": "jurisdiction", "size": 25},
                    "aggs": {"domains": {"terms": {"field": "domain", "size": 25}}},
                }
            },
        }
        response = await self.es.search(index=self.index, body=body)
        buckets = response.get("aggregations", {}).get("jurisdictions", {}).get("buckets", [])

        result = []
        for bucket in buckets:
            domain_buckets = bucket.get("domains", {}).get("buckets", [])
            result.append(
                {
                    "code": bucket["key"],
                    "name": JURISDICTION_NAMES.get(bucket["key"], bucket["key"]),
                    "count": bucket["doc_count"],
                    "domains": sorted([domain_bucket["key"] for domain_bucket in domain_buckets]),
                }
            )

        return sorted(result, key=lambda item: item["code"])


def parse_csv_list(raw_value: str | None) -> list[str] | None:
    if raw_value is None:
        return None
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    return values or None
