from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import Plan, TaskSpec, to_jsonable
from .store import RunStore


def run_artifact_dir(store: RunStore, run_id: str) -> Path:
    return store.root / "runs" / run_id / "artifacts"


def write_plan_artifacts(store: RunStore, run_id: str, plan: Plan) -> None:
    data = to_jsonable(plan)
    _write(store, run_id, "PLAN.json", "artifact.plan.json", data)
    md = ["# Plan", "", plan.problem_summary, "", "## Tasks"]
    for index, task in enumerate(plan.tasks, 1):
        route = task.metadata.get("route_policy") if isinstance(task.metadata, dict) else None
        md.append(f"{index}. {task.title} [{task.task_type}/{task.complexity}/{task.risk}] route={_route_name(route)}")
    md.extend(["", "## Verification", *[f"- {item}" for item in plan.validation_strategy]])
    _write(store, run_id, "PLAN.md", "artifact.plan.md", "\n".join(md) + "\n", media_type="text/markdown")


def write_worker_artifacts(
    store: RunStore,
    run_id: str,
    task: TaskSpec,
    ordinal: int,
    result: dict[str, Any],
    repo: Path,
    *,
    preexisting_dirty: list[str],
) -> None:
    root = f"tasks/{ordinal:03d}-{task.task_id}"
    changed = _git_lines(repo, ["diff", "--name-only", "--"]) + _git_lines(repo, ["ls-files", "--others", "--exclude-standard"])
    payload = {"task_id": task.task_id, "changed_files": sorted(set(changed)), "preexisting_dirty_files": preexisting_dirty}
    _write(store, run_id, f"{root}/changed-files.json", "artifact.worker.changed_files", payload, task.task_id)
    patch = _git_text(repo, ["diff", "--no-ext-diff", "--binary", "--"])
    _write(store, run_id, f"{root}/PATCH.diff", "artifact.worker.patch", patch, task.task_id, "text/x-diff")
    body = [
        f"# Result: {task.title}",
        "",
        f"status: {'pass' if int(result.get('returncode') or 0) == 0 else 'fail'}",
        f"returncode: {result.get('returncode')}",
        f"agent: {result.get('agent_id', '')}",
        "",
        "## Output",
        str(result.get("stdout") or "").strip(),
        "",
        "## Errors",
        str(result.get("stderr") or "").strip(),
        "",
        "## Tests",
        *[f"- {item}" for item in task.validation],
        "",
        "## Risks",
        *[f"- preexisting dirty: {item}" for item in preexisting_dirty],
    ]
    _write(store, run_id, f"{root}/RESULT.md", "artifact.worker.result", "\n".join(body).rstrip() + "\n", task.task_id, "text/markdown")


def write_review_verify_artifacts(store: RunStore, run_id: str, *, status: str, summary: str) -> None:
    review: dict[str, Any] = {
        "findings": [],
        "finding_fields": ["severity", "file", "line", "evidence", "recommendation"],
        "recommendation": "accept" if status == "completed" else "reject",
    }
    verify: dict[str, Any] = {
        "status": status,
        "summary": summary,
        "commands": [],
        "benchmark_deltas": {},
        "pass": status == "completed",
    }
    _write(store, run_id, "review/REVIEW.json", "artifact.review", review)
    _write(store, run_id, "verify/VERIFY.json", "artifact.verify", verify)


def artifact_manifest(store: RunStore, run_id: str) -> list[dict[str, Any]]:
    base = run_artifact_dir(store, run_id)
    if not base.exists():
        return []
    return [
        {"path": str(path.relative_to(base)), "size": path.stat().st_size}
        for path in sorted(base.rglob("*"))
        if path.is_file()
    ]


def cleanup_run(store: RunStore, run_id: str) -> list[str]:
    removed = []
    for name in ("tmp", "worktrees"):
        path = store.root / "runs" / run_id / name
        if path.exists():
            shutil.rmtree(path)
            removed.append(name)
    store.append_event(run_id, "artifacts.cleanup", {"removed": removed, "preserved": "artifacts, cas, events, replay"})
    return removed


def _write(
    store: RunStore,
    run_id: str,
    relpath: str,
    kind: str,
    data: str | dict[str, Any],
    task_id: str | None = None,
    media_type: str = "application/json",
) -> None:
    path = run_artifact_dir(store, run_id) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    store.put_artifact(run_id=run_id, task_id=task_id, kind=kind, data=text, media_type=media_type)


def _route_name(route: Any) -> str:
    return str(route.get("policy")) if isinstance(route, dict) else "unknown"


def _git_text(repo: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, timeout=5, check=False)
    except Exception as exc:
        return f"git failed: {exc}\n"
    return result.stdout if result.returncode == 0 else result.stderr


def _git_lines(repo: Path, args: list[str]) -> list[str]:
    return [line for line in _git_text(repo, args).splitlines() if line]
