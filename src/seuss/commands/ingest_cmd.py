from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from seuss.config import load_config, resolve_path, resolve_workspace
from seuss.jsonl_store import append_jsonl, read_jsonl, write_jsonl
from seuss.provenance import validate_provenance
from seuss.utils import now_iso, stable_hash

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{7,}\d")
URL_RE = re.compile(r"https?://\S+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
PHRASE_SPLIT_RE = re.compile(r"[,;:]+\s*")
WORD_RE = re.compile(r"\b\w+\b")


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _redact(text: str, redact_cfg: dict) -> tuple[str, dict[str, int]]:
    counts = {"emails": 0, "phone_numbers": 0, "urls": 0, "custom_patterns": 0}
    out = text

    if redact_cfg.get("emails", False):
        out, counts["emails"] = EMAIL_RE.subn("[REDACTED_EMAIL]", out)
    if redact_cfg.get("phone_numbers", False):
        out, counts["phone_numbers"] = PHONE_RE.subn("[REDACTED_PHONE]", out)
    if redact_cfg.get("urls", False):
        out, counts["urls"] = URL_RE.subn("[REDACTED_URL]", out)

    patterns = redact_cfg.get("custom_patterns", [])
    for pattern in patterns:
        out, n = re.subn(pattern, "[REDACTED_CUSTOM]", out)
        counts["custom_patterns"] += n

    return out, counts


def _segment_text(text: str, segmentation: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if segmentation.get("paragraph", True):
        result["paragraph"] = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if segmentation.get("sentence", True):
        result["sentence"] = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if segmentation.get("phrase", True):
        result["phrase"] = [p.strip() for p in PHRASE_SPLIT_RE.split(text) if p.strip()]
    if segmentation.get("word", True):
        result["word"] = WORD_RE.findall(text)
    if segmentation.get("character", True):
        result["character"] = [ch for ch in text if ch.strip()]
    return result


def _iter_directory_source(source: dict, config_path: Path) -> Iterable[dict]:
    source_path = resolve_path(source["path"], config_path)
    include = source.get("include", ["*.txt", "*.md"])
    seen: set[Path] = set()

    for pattern in include:
        for file_path in source_path.rglob(pattern):
            if not file_path.is_file() or file_path in seen:
                continue
            seen.add(file_path)
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            yield {
                "source_path": str(file_path),
                "text": text,
                "metadata": {},
            }


def _iter_single_file_source(source: dict, _config_path: Path) -> Iterable[dict]:
    file_path = Path(source["path"]).resolve()
    if not file_path.exists() or not file_path.is_file():
        return
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    yield {
        "source_path": str(file_path),
        "text": text,
        "metadata": {},
    }


def _iter_jsonl_source_with_stats(
    source: dict,
    config_path: Path,
    stats: dict[str, int],
) -> Iterable[dict]:
    source_path = resolve_path(source["path"], config_path)
    if not source_path.exists():
        stats["missing_source_path"] += 1
        return
    text_field = source.get("text_field", "text")
    timestamp_field = source.get("timestamp_field")
    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                stats["empty_rows"] += 1
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                stats["invalid_json_rows"] += 1
                continue
            if not isinstance(row, dict):
                stats["non_object_rows"] += 1
                continue
            text = str(row.get(text_field, "")).strip()
            if not text:
                stats["missing_text_rows"] += 1
                continue
            event_timestamp = None
            if timestamp_field:
                raw_ts = row.get(timestamp_field)
                if raw_ts is not None:
                    event_timestamp = str(raw_ts)
            yield {
                "source_path": str(source_path),
                "text": text,
                "metadata": row,
                "event_timestamp": event_timestamp,
            }


def _iter_source_records(
    source: dict,
    config_path: Path,
    stats: dict[str, int],
) -> Iterable[dict]:
    src_type = source.get("type")
    if src_type == "directory":
        yield from _iter_directory_source(source, config_path)
        return
    if src_type == "single_file":
        yield from _iter_single_file_source(source, config_path)
        return
    if src_type == "jsonl":
        yield from _iter_jsonl_source_with_stats(source, config_path, stats)
        return
    raise ValueError(f"Unsupported source type: {src_type}")


def _source_from_direct_path(direct_path: Path) -> dict:
    resolved = direct_path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Direct ingest path not found: {resolved}")

    # Stable source identity for dedupe behavior and inspect output.
    source_name = f"path_{abs(hash(str(resolved))) % 10_000_000}"

    if resolved.is_file():
        if resolved.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("Direct file ingest currently supports only .md or .txt files")
        return {
            "name": source_name,
            "type": "single_file",
            "path": str(resolved),
            "enabled": True,
            "provenance": "human_original",
        }

    if resolved.is_dir():
        return {
            "name": source_name,
            "type": "directory",
            "path": str(resolved),
            "enabled": True,
            "include": ["*.md", "*.txt"],
            "provenance": "human_original",
        }

    raise ValueError(f"Unsupported direct ingest path: {resolved}")


def _split_label(normalized_text: str, split_cfg: dict) -> str:
    train_ratio = float(split_cfg.get("train_ratio", 0.8))
    seed = int(split_cfg.get("seed", 42))
    digest = stable_hash([seed, normalized_text])
    bucket = int(digest[:8], 16) % 10000
    threshold = int(train_ratio * 10000)
    return "train" if bucket < threshold else "eval"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _assign_splits(records: list[dict], split_cfg: dict) -> None:
    strategy = str(split_cfg.get("strategy", "time")).lower()
    train_ratio = float(split_cfg.get("train_ratio", 0.8))

    if strategy != "time":
        for row in records:
            row["split"] = _split_label(row.get("normalized_text", ""), split_cfg)
        return

    with_time: list[dict] = []
    without_time: list[dict] = []
    for row in records:
        parsed = _parse_time(row.get("event_timestamp"))
        if parsed is None:
            without_time.append(row)
            continue
        row["_parsed_event_time"] = parsed
        with_time.append(row)

    with_time.sort(key=lambda row: row["_parsed_event_time"])
    cutoff = int(len(with_time) * train_ratio)
    for idx, row in enumerate(with_time):
        row["split"] = "train" if idx < cutoff else "eval"
        row.pop("_parsed_event_time", None)

    for row in without_time:
        row["split"] = _split_label(row.get("normalized_text", ""), split_cfg)


def run_ingest(
    config_path: Path,
    source_name: str | None,
    direct_path: str | None,
    dry_run: bool,
    rebuild: bool,
) -> int:
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    fragments_path = workspace / "corpus" / "fragments.jsonl"
    existing = [] if rebuild else read_jsonl(fragments_path)
    existing_keys = {
        (
            row.get("segment_type"),
            row.get("normalized_text"),
            row.get("source"),
            row.get("source_path"),
        )
        for row in existing
    }

    if direct_path and source_name:
        raise ValueError("Use either --source or --path, not both.")

    if direct_path:
        enabled_sources = [_source_from_direct_path(Path(direct_path))]
    else:
        sources = config.get("sources", [])
        enabled_sources = [src for src in sources if src.get("enabled", False)]
        if source_name:
            enabled_sources = [src for src in enabled_sources if src.get("name") == source_name]

    if not enabled_sources:
        print("No enabled sources matched.")
        return 0

    min_chars = int(config.get("segmentation", {}).get("min_fragment_chars", 3))
    max_chars = int(config.get("segmentation", {}).get("max_fragment_chars", 2000))
    redact_cfg = config.get("privacy", {}).get("redact", {})
    split_cfg = config.get("splits", {})
    segmentation = config.get("segmentation", {})

    created: list[dict] = []
    skipped_duplicates = 0
    redaction_totals = {"emails": 0, "phone_numbers": 0, "urls": 0, "custom_patterns": 0}
    per_source_stats: dict[str, dict[str, int]] = {}

    for source in enabled_sources:
        provenance = source.get("provenance", "human_original")
        validate_provenance(provenance)
        stats = {
            "records_seen": 0,
            "created_fragments": 0,
            "duplicates_skipped": 0,
            "filtered_by_length": 0,
            "invalid_json_rows": 0,
            "non_object_rows": 0,
            "missing_text_rows": 0,
            "empty_rows": 0,
            "missing_source_path": 0,
            "redacted_emails": 0,
            "redacted_phone_numbers": 0,
            "redacted_urls": 0,
            "redacted_custom_patterns": 0,
        }
        per_source_stats[source["name"]] = stats

        for source_record in _iter_source_records(source, config_path, stats):
            stats["records_seen"] += 1
            raw_text = source_record["text"]
            normalized = _normalize(raw_text)
            if not normalized:
                continue
            redacted, redaction_counts = _redact(normalized, redact_cfg)
            for key, value in redaction_counts.items():
                redaction_totals[key] += value
                stats[f"redacted_{key}"] += value

            segmented = _segment_text(redacted, segmentation)
            for segment_type, entries in segmented.items():
                for entry in entries:
                    normalized_entry = _normalize(entry)
                    if len(normalized_entry) < min_chars or len(normalized_entry) > max_chars:
                        stats["filtered_by_length"] += 1
                        continue
                    dedupe_key = (
                        segment_type,
                        normalized_entry,
                        source["name"],
                        source_record["source_path"],
                    )
                    if dedupe_key in existing_keys:
                        skipped_duplicates += 1
                        stats["duplicates_skipped"] += 1
                        continue
                    existing_keys.add(dedupe_key)
                    stats["created_fragments"] += 1
                    created.append(
                        {
                            "id": f"frag_{uuid.uuid4().hex[:12]}",
                            "source": source["name"],
                            "source_path": source_record["source_path"],
                            "provenance": provenance,
                            "text": entry,
                            "normalized_text": normalized_entry,
                            "segment_type": segment_type,
                            "event_timestamp": source_record.get("event_timestamp"),
                            "created_at": now_iso(),
                            "metadata": source_record.get("metadata", {}),
                        }
                    )

    _assign_splits(created, split_cfg)

    if dry_run:
        print("Dry run complete.")
        print(f"Would create fragments: {len(created)}")
        print(f"Skipped duplicates: {skipped_duplicates}")
        print(f"Redactions: {redaction_totals}")
        for source_name, stats in per_source_stats.items():
            print(f"source={source_name} stats={stats}")
        return 0

    if rebuild:
        write_jsonl(fragments_path, created)
    else:
        append_jsonl(fragments_path, created)

    print(f"Fragments written: {len(created)}")
    print(f"Skipped duplicates: {skipped_duplicates}")
    print(f"Redactions: {redaction_totals}")
    for source_name, stats in per_source_stats.items():
        print(f"source={source_name} stats={stats}")

    stats_payload = {
        "run_at": now_iso(),
        "redaction_totals": redaction_totals,
        "per_source_stats": per_source_stats,
        "fragments_written": len(created),
        "skipped_duplicates": skipped_duplicates,
    }
    stats_path = workspace / "corpus" / "ingest_stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return 0
