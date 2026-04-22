from __future__ import annotations

import shutil
from pathlib import Path

from seuss.config import load_config, resolve_workspace
from seuss.commands.init_cmd import ensure_workspace_layout
from seuss.jsonl_store import touch_jsonl, write_jsonl
from seuss.pathing import resolve_training_queue_path


def _clear_json_files(path: Path) -> int:
    removed = 0
    if not path.exists():
        return removed
    for file_path in path.glob("*.json"):
        file_path.unlink(missing_ok=True)
        removed += 1
    return removed


def run_reset_corpus(
    config_path: Path,
    yes: bool,
    keep_runs: bool,
    keep_evals: bool,
) -> int:
    if not yes:
        print("Refusing destructive reset. Re-run with --yes.")
        return 1

    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)
    ensure_workspace_layout(workspace)
    touch_jsonl(resolve_training_queue_path(config, config_path, workspace))

    fragments_path = workspace / "corpus" / "fragments.jsonl"
    write_jsonl(fragments_path, [])

    persona_profile = workspace / "memory" / "persona_profile.json"
    persona_profile.unlink(missing_ok=True)

    removed_runs = 0
    removed_evals = 0
    if not keep_runs:
        removed_runs = _clear_json_files(workspace / "runs")
    if not keep_evals:
        removed_evals = _clear_json_files(workspace / "evals")

    print("Corpus reset complete.")
    print(f"fragments_cleared={fragments_path}")
    print(f"runs_removed={removed_runs}")
    print(f"evals_removed={removed_evals}")
    return 0


def run_reset_workspace(config_path: Path, yes: bool) -> int:
    if not yes:
        print("Refusing destructive reset. Re-run with --yes.")
        return 1

    config = load_config(config_path)
    workspace = resolve_workspace(config, config_path)

    if workspace.exists():
        shutil.rmtree(workspace)

    ensure_workspace_layout(workspace)
    touch_jsonl(resolve_training_queue_path(config, config_path, workspace))
    print("Workspace reset complete.")
    print(f"workspace={workspace}")
    return 0
