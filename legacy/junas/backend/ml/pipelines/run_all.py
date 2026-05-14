from __future__ import annotations

from ml.pipelines.ingest_glossaries import run as run_glossary_ingest
from ml.pipelines.ingest_lecard import run as run_lecard_ingest
from ml.pipelines.ingest_statutes import run as run_statute_ingest


def main() -> int:
    total = 0
    total += run_glossary_ingest()
    total += run_statute_ingest()
    run_lecard_ingest()
    return total


if __name__ == "__main__":
    print(main())
