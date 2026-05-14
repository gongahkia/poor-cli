from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from typing import Any

from prefect import flow, task

from data.parsers.glossary_parser import (
    discover_dataset_root,
    discover_glossary_files,
    parse_glossary_file,
)

INDEX_NAME = "junas_glossary"
BATCH_SIZE = 500

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
            "phrase": {
                "type": "text",
                "analyzer": "legal_english",
                "fields": {
                    "keyword": {"type": "keyword"},
                    "suggest": {"type": "completion"},
                },
            },
            "definition_text": {"type": "text", "analyzer": "legal_english"},
            "definition_html": {"type": "text", "index": False},
            "jurisdiction": {"type": "keyword"},
            "domain": {"type": "keyword"},
            "source_title": {"type": "keyword"},
            "source_url": {"type": "keyword", "index": False},
            "source_creator": {"type": "keyword"},
            "language": {"type": "keyword"},
            "license": {"type": "keyword", "index": False},
            "last_modified": {"type": "keyword"},
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


@task
def discover_files(dataset_root: str | None = None) -> list[str]:
    root = Path(dataset_root) if dataset_root else discover_dataset_root()
    files = discover_glossary_files(root)
    return [str(path) for path in files]


@task
async def create_index(es: Any) -> None:
    if await es.indices.exists(index=INDEX_NAME):
        await es.indices.delete(index=INDEX_NAME)
    await es.indices.create(index=INDEX_NAME, body=MAPPING)


@task
async def index_file(es: Any, filepath: str) -> int:
    entries = parse_glossary_file(filepath)
    if not entries:
        return 0

    operations: list[dict] = []
    for entry in entries:
        operations.append({"index": {"_index": INDEX_NAME}})
        operations.append(entry.to_document())

    await es.bulk(operations=operations, refresh="wait_for")
    return len(entries)


async def _index_file_batch(es: Any, filepaths: list[str]) -> int:
    total = 0
    for filepath in filepaths:
        total += await index_file.fn(es, filepath)
    return total


@flow(name="ingest-glossaries")
async def ingest_glossaries(dataset_root: str | None = None) -> int:
    if AsyncElasticsearch is None:
        raise RuntimeError("elasticsearch client is not installed")

    files = discover_files(dataset_root)
    es = AsyncElasticsearch("http://localhost:9200")
    await create_index(es)

    total = 0
    for start in range(0, len(files), BATCH_SIZE):
        batch = files[start : start + BATCH_SIZE]
        total += await _index_file_batch(es, batch)

    await es.close()
    return total


def run() -> int:
    return asyncio.run(ingest_glossaries())


if __name__ == "__main__":
    print(run())
