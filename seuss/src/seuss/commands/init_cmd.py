from __future__ import annotations

from pathlib import Path

from seuss.config import load_config, resolve_workspace, write_default_config
from seuss.jsonl_store import touch_jsonl
from seuss.pathing import resolve_training_queue_path


def ensure_workspace_layout(workspace: Path) -> None:
    (workspace / "corpus").mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(parents=True, exist_ok=True)
    (workspace / "evals").mkdir(parents=True, exist_ok=True)
    (workspace / "runs").mkdir(parents=True, exist_ok=True)

    touch_jsonl(workspace / "training_queue.jsonl")
    touch_jsonl(workspace / "approved_training.jsonl")
    touch_jsonl(workspace / "corpus" / "fragments.jsonl")
    touch_jsonl(workspace / "memory" / "memories.jsonl")


def run_init(config_path: Path, force: bool) -> int:
    write_default_config(config_path, force=force)
    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    ensure_workspace_layout(workspace)
    touch_jsonl(resolve_training_queue_path(config, config_path, workspace))

    print(f"Initialized config: {config_path}")
    print(f"Workspace: {workspace}")
    return 0
