"""User-selectable strategy overrides for features that have swap-able
implementations. Persisted per-repo at ``.poor-cli/strategies.json``.

Features covered:
- ``memory_reranker_strategy``: one of ``mmr``, ``cross_encoder``, ``score_order``.
- ``memory_reranker_cross_encoder_model``: HF model id for the cross-encoder.
- ``adaptive_tool_scoring``: ``auto`` | ``on`` | ``off``.

All features default to conservative picks (MMR, default model, auto). Values
outside the known enum fall back to the default.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

STRATEGIES_FILENAME = "strategies.json"

DEFAULTS: Dict[str, Any] = {
    "memory_reranker_strategy": "mmr",
    "memory_reranker_cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "adaptive_tool_scoring": "auto",
}

RERANKER_CHOICES = ("mmr", "cross_encoder", "score_order")
ADAPTIVE_CHOICES = ("auto", "on", "off")


def _path(repo_root: Optional[Path] = None) -> Path:
    root = Path(repo_root) if repo_root else Path.cwd()
    return root / ".poor-cli" / STRATEGIES_FILENAME


def load(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    path = _path(repo_root)
    merged = dict(DEFAULTS)
    if not path.exists():
        return merged
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return merged
    if not isinstance(raw, dict):
        return merged
    for k, v in raw.items():
        if k in DEFAULTS and isinstance(v, (str, int, bool, float)):
            merged[k] = v
    # enforce enums
    if merged["memory_reranker_strategy"] not in RERANKER_CHOICES:
        merged["memory_reranker_strategy"] = DEFAULTS["memory_reranker_strategy"]
    if merged["adaptive_tool_scoring"] not in ADAPTIVE_CHOICES:
        merged["adaptive_tool_scoring"] = DEFAULTS["adaptive_tool_scoring"]
    return merged


def save(strategies: Dict[str, Any], repo_root: Optional[Path] = None) -> None:
    path = _path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(strategies, indent=2, sort_keys=True))
    tmp.replace(path)


def set_value(name: str, value: Any, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    if name not in DEFAULTS:
        raise ValueError(f"unknown strategy: {name!r}")
    # enum validation
    if name == "memory_reranker_strategy" and value not in RERANKER_CHOICES:
        raise ValueError(f"{name} must be one of {RERANKER_CHOICES}")
    if name == "adaptive_tool_scoring" and value not in ADAPTIVE_CHOICES:
        raise ValueError(f"{name} must be one of {ADAPTIVE_CHOICES}")
    current = load(repo_root)
    current[name] = value
    save(current, repo_root)
    return current


def adaptive_override_from_str(value: str) -> Optional[bool]:
    v = str(value or "auto").strip().lower()
    if v == "on":
        return True
    if v == "off":
        return False
    return None  # auto
