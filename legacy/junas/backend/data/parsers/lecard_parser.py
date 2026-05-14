from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

CANDIDATE_ARCHIVES = ("candidates1.zip", "candidates2.zip")


def discover_lecard_data_root() -> Path:
    candidates = [
        Path("LeCaRD/data"),
        Path("vendor-data/LeCaRD/data"),
        Path("../vendor-data/LeCaRD/data"),
        Path("../../vendor-data/LeCaRD/data"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("vendor-data/LeCaRD/data")


def _load_json_or_jsonl(path: Path) -> Any:
    content = path.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        return []
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows


def load_queries(data_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    query_path = root / "query" / "query.json"
    rows = _load_json_or_jsonl(query_path)
    queries: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        query = dict(row)
        query["ridx"] = str(query.get("ridx", "")).strip()
        query["q"] = str(query.get("q", ""))
        crimes = query.get("crime", [])
        if not isinstance(crimes, list):
            crimes = []
        query["crime"] = [str(item) for item in crimes if str(item).strip()]
        if query["ridx"] and query["q"]:
            queries.append(query)
    return queries


def _label_path(root: Path) -> Path:
    candidates = [
        root / "label" / "label_top30.json",
        root / "label" / "label_top30_dict.json",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return root / "label" / "label_top30_dict.json"


def load_labels(data_root: str | Path | None = None) -> dict[str, dict[str, int]]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    path = _label_path(root)
    raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    labels: dict[str, dict[str, int]] = {}
    for ridx, candidate_scores in raw.items() if isinstance(raw, dict) else []:
        if not isinstance(candidate_scores, dict):
            continue
        labels[str(ridx)] = {
            str(case_id): int(score)
            for case_id, score in candidate_scores.items()
        }
    return labels


def load_stopwords(data_root: str | Path | None = None) -> set[str]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    path = root / "others" / "stopword.txt"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        return {line.strip() for line in handle if line.strip()}


def load_criminal_charges(data_root: str | Path | None = None) -> list[str]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    candidates = [
        root / "others" / "criminal_charges.txt",
        root / "others" / "criminal charges.txt",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            charges = [line.strip() for line in handle if line.strip()]
        return sorted(set(charges))
    return []


def _has_extracted_candidates(candidates_root: Path) -> bool:
    for path in candidates_root.rglob("*"):
        if path.is_dir() and any(path.glob("*.json")):
            return True
    return False


def unzip_candidates(data_root: str | Path | None = None, force: bool = False) -> dict[str, Any]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    candidates_root = root / "candidates"
    if not candidates_root.exists():
        return {"extracted": 0, "archives": []}

    if not force and _has_extracted_candidates(candidates_root):
        return {"extracted": 0, "archives": []}

    extracted_archives: list[str] = []
    extracted_files = 0
    for archive_name in CANDIDATE_ARCHIVES:
        archive_path = candidates_root / archive_name
        if not archive_path.exists():
            continue
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.namelist() if member.endswith(".json")]
            archive.extractall(candidates_root)
            extracted_files += len(members)
            extracted_archives.append(archive_name)
    return {"extracted": extracted_files, "archives": extracted_archives}


def discover_candidate_directories(data_root: str | Path | None = None) -> dict[str, Path]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    candidates_root = root / "candidates"
    directories: dict[str, Path] = {}
    if not candidates_root.exists():
        return directories

    for path in candidates_root.rglob("*"):
        if not path.is_dir():
            continue
        if not any(path.glob("*.json")):
            continue
        directories[path.name] = path
    return directories


def load_candidates(
    query_ridx: str,
    data_root: str | Path | None = None,
    candidate_directories: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    directories = candidate_directories if candidate_directories is not None else discover_candidate_directories(root)
    target = directories.get(str(query_ridx))
    if target is None:
        return []

    candidates: list[dict[str, Any]] = []
    for path in sorted(target.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["case_id"] = path.stem
        row["ridx"] = str(query_ridx)
        candidates.append(row)
    return candidates


def load_all_candidates(
    queries: list[dict[str, Any]] | None = None,
    data_root: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    unzip_candidates(root)
    resolved_queries = queries if queries is not None else load_queries(root)
    directories = discover_candidate_directories(root)

    all_candidates: dict[str, list[dict[str, Any]]] = {}
    for query in resolved_queries:
        ridx = str(query.get("ridx", "")).strip()
        if not ridx:
            continue
        all_candidates[ridx] = load_candidates(ridx, root, candidate_directories=directories)
    return all_candidates


def build_corpus(all_candidates: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    corpus: dict[str, dict[str, Any]] = {}
    for candidate_rows in all_candidates.values():
        for row in candidate_rows:
            case_id = str(row.get("case_id", "")).strip()
            if not case_id:
                continue
            if case_id not in corpus:
                corpus[case_id] = row
    return corpus


def build_candidate_charge_map(
    queries: list[dict[str, Any]],
    all_candidates: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    crimes_by_query = {
        str(query.get("ridx", "")): [str(crime) for crime in query.get("crime", [])]
        for query in queries
        if str(query.get("ridx", "")).strip()
    }

    charge_map: dict[str, set[str]] = {}
    for ridx, candidate_rows in all_candidates.items():
        crimes = crimes_by_query.get(ridx, [])
        if not crimes:
            continue
        for row in candidate_rows:
            case_id = str(row.get("case_id", "")).strip()
            if not case_id:
                continue
            charge_map.setdefault(case_id, set()).update(crimes)

    return {case_id: sorted(charges) for case_id, charges in charge_map.items()}


def attach_candidate_charges(
    corpus: dict[str, dict[str, Any]],
    candidate_charges: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    enriched: dict[str, dict[str, Any]] = {}
    for case_id, row in corpus.items():
        enriched_row = dict(row)
        enriched_row["charges"] = candidate_charges.get(case_id, [])
        enriched[case_id] = enriched_row
    return enriched


def load_prediction_file(
    filename: str,
    data_root: str | Path | None = None,
) -> dict[str, list[str]]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    path = root / "prediction" / filename
    if not path.exists():
        return {}

    raw_loaded = _load_json_or_jsonl(path)
    if isinstance(raw_loaded, list):
        raw = raw_loaded[0] if raw_loaded and isinstance(raw_loaded[0], dict) else {}
    elif isinstance(raw_loaded, dict):
        raw = raw_loaded
    else:
        raw = {}

    predictions: dict[str, list[str]] = {}
    for ridx, candidate_ids in raw.items():
        if not isinstance(candidate_ids, list):
            continue
        predictions[str(ridx)] = [str(candidate_id) for candidate_id in candidate_ids]
    return predictions


def load_baseline_predictions(data_root: str | Path | None = None) -> dict[str, dict[str, list[str]]]:
    return {
        "bm25": load_prediction_file("bm25_top100.json", data_root),
        "tfidf": load_prediction_file("tfidf_top100.json", data_root),
        "lm": load_prediction_file("lm_top100.json", data_root),
        "bert": load_prediction_file("bert.json", data_root),
    }
