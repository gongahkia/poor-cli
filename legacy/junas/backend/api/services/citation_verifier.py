from __future__ import annotations

import re
from typing import Any

from api.services.retrieval_orchestrator import RetrievedChunk, SourceType

ORS_CITATION_PATTERN = re.compile(r"\[ORS\s+([0-9]{1,4}[A-Z]?\.[0-9]{3,4})\]", re.IGNORECASE)
GLOSSARY_CITATION_PATTERN = re.compile(r"\[([^\[\]]*?(?:Glossary|Courts|Dictionary)):\s*\"([^\"]+)\"\]", re.IGNORECASE)
GENERIC_CITATION_PATTERN = re.compile(r"\[([^\[\]]{2,80})\]")
# Singapore citation patterns (ported from Junas)
SG_SLR_R_PATTERN = re.compile(r"\[(\d{4})\]\s+(\d+)\s+SLR\(R\)\s+(\d+)")
SG_SLR_PATTERN = re.compile(r"\[(\d{4})\]\s+(\d+)\s+SLR\s+(\d+)")
SG_SGCA_PATTERN = re.compile(r"\[(\d{4})\]\s+SGCA\s+(\d+)")
SG_SGHC_PATTERN = re.compile(r"\[(\d{4})\]\s+SGHC\s+(\d+)")
SG_STATUTE_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&'/-]*(?:\s+[A-Z][A-Za-z0-9&'/-]*)*\s+Act)\s*\((Cap\.?\s*[0-9A-Z]+(?:\s*,\s*\d{4}\s+Rev\s+Ed)?)\)")
# Malaysia citation patterns (ported from Junas)
MY_MLJ_PATTERN = re.compile(r"\[(\d{4})\]\s+(\d+)\s+MLJ\s+(\d+)")
MY_CLJ_PATTERN = re.compile(r"\[(\d{4})\]\s+(\d+)\s+CLJ\s+(\d+)")
MY_MLJU_PATTERN = re.compile(r"\[(\d{4})\]\s+MLJU\s+(\d+)")
MY_MLRA_PATTERN = re.compile(r"\[(\d{4})\]\s+MLRA\s+(\d+)")


class CitationVerifier:
    def __init__(self, es_client: Any):
        self.es = es_client

    async def extract_and_verify(
        self,
        answer: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> dict[str, Any]:
        citations: list[dict[str, Any]] = []
        retrieved_ids = {chunk.source_id for chunk in retrieved_chunks}

        for match in ORS_CITATION_PATTERN.finditer(answer):
            section_num = match.group(1)
            citation_id = f"ORS {section_num}"
            in_context = citation_id in retrieved_ids
            exists = in_context or await self._section_exists(section_num)
            citations.append(
                {
                    "citation": citation_id,
                    "type": SourceType.STATUTE.value,
                    "in_context": in_context,
                    "exists_in_index": exists,
                    "position": list(match.span()),
                }
            )

        for match in GLOSSARY_CITATION_PATTERN.finditer(answer):
            source = match.group(1).strip()
            term = match.group(2).strip()
            in_context = any(
                chunk.source_type == SourceType.GLOSSARY and chunk.source_id.lower() == term.lower()
                for chunk in retrieved_chunks
            )
            exists = in_context or await self._term_exists(term)
            citations.append(
                {
                    "citation": f"{source}: \"{term}\"",
                    "type": SourceType.GLOSSARY.value,
                    "in_context": in_context,
                    "exists_in_index": exists,
                    "position": list(match.span()),
                }
            )

        # Singapore case law citations
        sg_case_patterns = [
            ("sg_slr_r", SG_SLR_R_PATTERN), ("sg_slr", SG_SLR_PATTERN),
            ("sg_sgca", SG_SGCA_PATTERN), ("sg_sghc", SG_SGHC_PATTERN),
        ]
        for ctype, pattern in sg_case_patterns:
            for match in pattern.finditer(answer):
                citations.append({
                    "citation": match.group(0), "type": ctype,
                    "in_context": match.group(0) in retrieved_ids, "exists_in_index": True,
                    "position": list(match.span()),
                })
        for match in SG_STATUTE_PATTERN.finditer(answer):
            citations.append({
                "citation": match.group(0), "type": "sg_statute",
                "in_context": match.group(0) in retrieved_ids, "exists_in_index": True,
                "position": list(match.span()),
            })
        # Malaysia case law citations
        my_case_patterns = [
            ("my_mlj", MY_MLJ_PATTERN), ("my_clj", MY_CLJ_PATTERN),
            ("my_mlju", MY_MLJU_PATTERN), ("my_mlra", MY_MLRA_PATTERN),
        ]
        for ctype, pattern in my_case_patterns:
            for match in pattern.finditer(answer):
                citations.append({
                    "citation": match.group(0), "type": ctype,
                    "in_context": match.group(0) in retrieved_ids, "exists_in_index": True,
                    "position": list(match.span()),
                })

        known_spans = {(row["position"][0], row["position"][1]) for row in citations}
        for match in GENERIC_CITATION_PATTERN.finditer(answer):
            span = match.span()
            if span in known_spans:
                continue
            raw = match.group(1).strip()
            if not raw or len(raw) > 60:
                continue
            in_context = raw in retrieved_ids
            citations.append(
                {
                    "citation": raw,
                    "type": "generic",
                    "in_context": in_context,
                    "exists_in_index": in_context,
                    "position": list(span),
                }
            )

        citations.sort(key=lambda row: tuple(row["position"]))
        hallucinated = [row for row in citations if not row["in_context"] and not row["exists_in_index"]]
        verified = [row for row in citations if row["exists_in_index"]]

        sentence_count = max(1, len(re.findall(r"[.!?](?:\s|$)", answer)))

        return {
            "citations": citations,
            "total_citations": len(citations),
            "verified_citations": len(verified),
            "hallucinated_citations": hallucinated,
            "citation_rate": len(citations) / sentence_count,
        }

    async def _section_exists(self, section_num: str) -> bool:
        if self.es is None:
            return False

        result = await self.es.search(
            index="junas_statutes",
            body={"query": {"term": {"number": section_num}}},
            size=1,
        )
        return bool(result.get("hits", {}).get("hits", []))

    async def _term_exists(self, term: str) -> bool:
        if self.es is None:
            return False

        result = await self.es.search(
            index="junas_glossary",
            body={
                "query": {
                    "term": {
                        "phrase.keyword": {
                            "value": term,
                            "case_insensitive": True,
                        }
                    }
                }
            },
            size=1,
        )
        return bool(result.get("hits", {}).get("hits", []))
