"""File-first context substrate helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CONTEXT_DIR = ".poor-cli/context"
SCHEMA_VERSION = "1.0"

JSONL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "decisions.jsonl": {
        "_schema": "decision",
        "_version": SCHEMA_VERSION,
        "_description": "Append-only project decisions with alternatives, reasoning, and outcomes.",
    },
    "failures.jsonl": {
        "_schema": "failure",
        "_version": SCHEMA_VERSION,
        "_description": "Append-only failures, root causes, and prevention notes.",
    },
    "runs.jsonl": {
        "_schema": "run_summary",
        "_version": SCHEMA_VERSION,
        "_description": "Append-only agent run summaries and context handoffs.",
    },
}

MARKDOWN_FILES: Dict[str, str] = {
    "MAP.md": "# Context Map\n\n- goals: goals.yaml\n- decisions: decisions.jsonl\n- failures: failures.jsonl\n- runs: runs.jsonl\n- open questions: open_questions.md\n",
    "open_questions.md": "# Open Questions\n\n",
}

YAML_FILES: Dict[str, str] = {
    "goals.yaml": "schema: goals\nversion: \"1.0\"\ngoals: []\n",
}


@dataclass
class ContextDoctorFinding:
    severity: str
    path: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


def context_root(repo_root: Optional[Path] = None) -> Path:
    return (Path(repo_root or Path.cwd()) / CONTEXT_DIR).resolve()


def init_context(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    root = context_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    created: List[str] = []
    existing: List[str] = []
    for name, text in {**MARKDOWN_FILES, **YAML_FILES}.items():
        path = root / name
        if path.exists():
            existing.append(str(path))
            continue
        path.write_text(text, encoding="utf-8")
        created.append(str(path))
    for name, schema in JSONL_SCHEMAS.items():
        path = root / name
        if path.exists():
            existing.append(str(path))
            continue
        path.write_text(json.dumps(schema, sort_keys=True) + "\n", encoding="utf-8")
        created.append(str(path))
    return {"root": str(root), "created": created, "existing": existing}


def _jsonl_lines(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: JSONL row must be object")
        rows.append(row)
    return rows


def append_jsonl_record(
    filename: str,
    record: Dict[str, Any],
    *,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    if filename not in JSONL_SCHEMAS:
        raise ValueError(f"unknown context JSONL file: {filename}")
    root = context_root(repo_root)
    if not root.exists():
        init_context(repo_root)
    path = root / filename
    if not path.exists():
        path.write_text(json.dumps(JSONL_SCHEMAS[filename], sort_keys=True) + "\n", encoding="utf-8")
    rows = _jsonl_lines(path)
    if not rows or rows[0].get("_schema") != JSONL_SCHEMAS[filename]["_schema"]:
        raise ValueError(f"{path}: missing schema header")
    enriched = dict(record)
    enriched.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(enriched, sort_keys=True) + "\n")
    return {"path": str(path), "record": enriched}


def _doctor_jsonl(path: Path, expected: Dict[str, Any]) -> Iterable[ContextDoctorFinding]:
    try:
        rows = _jsonl_lines(path)
    except ValueError as exc:
        yield ContextDoctorFinding("error", str(path), str(exc))
        return
    if not rows:
        yield ContextDoctorFinding("error", str(path), "empty JSONL file")
        return
    first = rows[0]
    if first.get("_schema") != expected["_schema"]:
        yield ContextDoctorFinding("error", str(path), "missing or wrong schema header")
    if len(rows) > 1:
        field_counts: Dict[str, int] = {}
        for row in rows[1:]:
            for key, value in row.items():
                if value not in ("", None, [], {}):
                    field_counts[key] = field_counts.get(key, 0) + 1
        sparse = [key for key, count in field_counts.items() if count <= max(1, len(rows[1:]) // 10)]
        if len(sparse) >= 5:
            yield ContextDoctorFinding("warn", str(path), f"many sparse fields: {', '.join(sorted(sparse)[:8])}")


def doctor_context(repo_root: Optional[Path] = None, *, max_file_bytes: int = 64_000) -> Dict[str, Any]:
    root = context_root(repo_root)
    findings: List[ContextDoctorFinding] = []
    if not root.exists():
        findings.append(ContextDoctorFinding("error", str(root), "context substrate not initialized"))
        return {"root": str(root), "ok": False, "findings": [f.to_dict() for f in findings]}
    for name in sorted([*MARKDOWN_FILES.keys(), *YAML_FILES.keys(), *JSONL_SCHEMAS.keys()]):
        path = root / name
        if not path.exists():
            findings.append(ContextDoctorFinding("error", str(path), "missing context file"))
            continue
        size = path.stat().st_size
        if size > max_file_bytes:
            findings.append(ContextDoctorFinding("warn", str(path), f"large file ({size} bytes); consider splitting"))
    for name, schema in JSONL_SCHEMAS.items():
        path = root / name
        if path.exists():
            findings.extend(_doctor_jsonl(path, schema))
    return {
        "root": str(root),
        "ok": not any(f.severity == "error" for f in findings),
        "findings": [f.to_dict() for f in findings],
    }


def context_map(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    root = context_root(repo_root)
    if not root.exists():
        return {"root": str(root), "files": []}
    files = []
    for path in sorted(root.iterdir()):
        if path.is_file():
            files.append({"path": str(path), "bytes": path.stat().st_size})
    return {"root": str(root), "files": files}
