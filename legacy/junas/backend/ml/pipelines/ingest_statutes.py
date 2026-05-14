from __future__ import annotations

import asyncio
import importlib
import re
from itertools import count
from typing import Any

from prefect import flow, task

from data.parsers.statute_parser import StatuteSection, discover_ors_file, parse_ors_file, strip_html

INDEX_NAME = "junas_statutes"
COLLECTION_NAME = "junas_statutes"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
ES_BATCH_SIZE = 500
QDRANT_BATCH_SIZE = 256
MAX_EMBED_CHARS = 2000

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "legal_english": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "english_stemmer", "english_stop"],
                }
            },
            "filter": {
                "english_stemmer": {"type": "stemmer", "language": "english"},
                "english_stop": {"type": "stop", "stopwords": "_english_"},
            },
        },
    },
    "mappings": {
        "properties": {
            "number": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "legal_english",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "chapter_number": {"type": "keyword"},
            "edition": {"type": "integer"},
            "kind": {"type": "keyword"},
            "text_plain": {"type": "text", "analyzer": "legal_english"},
            "text_html": {"type": "text", "index": False},
            "amendment_history": {"type": "text", "index": False},
            "cross_references": {"type": "keyword"},
        }
    },
}


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
        return None
    if attr_name is None:
        return module
    return getattr(module, attr_name, None)


AsyncElasticsearch = _optional_import("elasticsearch", "AsyncElasticsearch")
QdrantClient = _optional_import("qdrant_client", "QdrantClient")
Distance = _optional_import("qdrant_client.models", "Distance")
PointStruct = _optional_import("qdrant_client.models", "PointStruct")
VectorParams = _optional_import("qdrant_client.models", "VectorParams")
SentenceTransformer = _optional_import("sentence_transformers", "SentenceTransformer")


@task
def load_sections(path: str | None = None) -> list[StatuteSection]:
    source = discover_ors_file() if path is None else path
    return list(parse_ors_file(source))


@task
async def create_es_index(es: Any) -> None:
    if await es.indices.exists(index=INDEX_NAME):
        await es.indices.delete(index=INDEX_NAME)
    await es.indices.create(index=INDEX_NAME, body=MAPPING)


@task
async def index_es_batch(es: Any, batch: list[StatuteSection]) -> int:
    operations: list[dict[str, Any]] = []
    for section in batch:
        operations.append({"index": {"_index": INDEX_NAME, "_id": section.number}})
        operations.append(section.to_document())
    if operations:
        await es.bulk(operations=operations, refresh=False)
    return len(batch)


def _paragraph_chunks(section: StatuteSection) -> list[str]:
    if len(section.text_plain) <= MAX_EMBED_CHARS:
        return [section.text_plain]

    raw_parts = re.split(r"</p>", section.text_html)
    parts = [strip_html(part) for part in raw_parts]
    parts = [part for part in parts if part]
    if not parts:
        return [section.text_plain[:MAX_EMBED_CHARS]]

    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + " " + part).strip() if current else part
        if len(candidate) <= MAX_EMBED_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = part[:MAX_EMBED_CHARS]
    if current:
        chunks.append(current)
    return chunks


def _build_qdrant_rows(sections: list[StatuteSection]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in sections:
        for chunk_index, chunk_text in enumerate(_paragraph_chunks(section)):
            rows.append(
                {
                    "number": section.number,
                    "name": section.name,
                    "chapter_number": section.chapter_number,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "text_snippet": chunk_text[:200],
                }
            )
    return rows


def _create_qdrant_collection(client: Any) -> None:
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )


def _index_qdrant(rows: list[dict[str, Any]]) -> int:
    if QdrantClient is None or VectorParams is None or Distance is None or PointStruct is None:
        raise RuntimeError("qdrant client is not installed")
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers is not installed")

    client = QdrantClient(url="http://localhost:6333")
    _create_qdrant_collection(client)

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    total = 0
    id_counter = count(start=1)

    for start in range(0, len(rows), QDRANT_BATCH_SIZE):
        batch = rows[start : start + QDRANT_BATCH_SIZE]
        texts = [row["text"] for row in batch]
        embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)

        points = []
        for i, row in enumerate(batch):
            points.append(
                PointStruct(
                    id=next(id_counter),
                    vector=embeddings[i].tolist(),
                    payload={
                        "number": row["number"],
                        "name": row["name"],
                        "chapter_number": row["chapter_number"],
                        "chunk_index": row["chunk_index"],
                        "text_snippet": row["text_snippet"],
                    },
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        total += len(points)

    client.close()
    return total


@flow(name="ingest-statutes")
async def ingest_statutes(path: str | None = None) -> int:
    if AsyncElasticsearch is None:
        raise RuntimeError("elasticsearch client is not installed")

    sections = load_sections(path)

    es = AsyncElasticsearch("http://localhost:9200")
    await create_es_index(es)

    for start in range(0, len(sections), ES_BATCH_SIZE):
        batch = sections[start : start + ES_BATCH_SIZE]
        await index_es_batch(es, batch)

    await es.indices.refresh(index=INDEX_NAME)
    await es.close()

    rows = _build_qdrant_rows(sections)
    _index_qdrant(rows)

    return len(sections)


def run() -> int:
    return asyncio.run(ingest_statutes())


if __name__ == "__main__":
    print(run())
