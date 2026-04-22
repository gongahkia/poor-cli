from __future__ import annotations

from pathlib import Path

from seuss.config import resolve_path


def resolve_training_queue_path(
    config: dict,
    config_path: Path,
    workspace: Path,
) -> Path:
    live_training_cfg = config.get("adaptation", {}).get("live_training_data", {})
    queue_path_value = live_training_cfg.get("queue_path")
    if not queue_path_value:
        return workspace / "training_queue.jsonl"
    return resolve_path(str(queue_path_value), config_path)


def resolve_approved_training_path(workspace: Path) -> Path:
    return workspace / "approved_training.jsonl"
