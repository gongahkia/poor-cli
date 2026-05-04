"""Spec/PRD-driven development mode orchestration."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Subtask:
    id: str
    title: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    estimated_tokens: int = 0
    status: SubtaskStatus = SubtaskStatus.PENDING
    checkpoint_id: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "dependsOn": list(self.depends_on),
            "successCriteria": list(self.success_criteria),
            "estimatedTokens": self.estimated_tokens,
            "status": self.status.value,
            "checkpointId": self.checkpoint_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subtask":
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            depends_on=[str(item) for item in data.get("dependsOn", data.get("depends_on", []))],
            success_criteria=[str(item) for item in data.get("successCriteria", data.get("success_criteria", []))],
            estimated_tokens=int(data.get("estimatedTokens", data.get("estimated_tokens", 0)) or 0),
            status=SubtaskStatus(str(data.get("status") or SubtaskStatus.PENDING.value)),
            checkpoint_id=data.get("checkpointId") or data.get("checkpoint_id"),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class SpecRun:
    spec_id: str
    spec_path: str
    title: str
    subtasks: List[Subtask]
    status: str = "pending"
    current_subtask_id: Optional[str] = None
    auto_advance: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "specId": self.spec_id,
            "specPath": self.spec_path,
            "title": self.title,
            "status": self.status,
            "currentSubtaskId": self.current_subtask_id,
            "autoAdvance": self.auto_advance,
            "subtasks": [task.to_dict() for task in self.subtasks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpecRun":
        return cls(
            spec_id=str(data.get("specId") or data.get("spec_id") or ""),
            spec_path=str(data.get("specPath") or data.get("spec_path") or ""),
            title=str(data.get("title") or ""),
            status=str(data.get("status") or "pending"),
            current_subtask_id=data.get("currentSubtaskId") or data.get("current_subtask_id"),
            auto_advance=bool(data.get("autoAdvance", data.get("auto_advance", False))),
            subtasks=[Subtask.from_dict(item) for item in data.get("subtasks", []) if isinstance(item, dict)],
        )


class SpecMode:
    def __init__(
        self,
        repo_root: Optional[Path] = None,
        checkpoint_manager: Any = None,
        subagent_runner: Optional[Callable[[str, str, SpecRun, Subtask], str]] = None,
    ):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.specs_dir = self.repo_root / ".poor-cli" / "specs"
        self.checkpoint_manager = checkpoint_manager
        self.subagent_runner = subagent_runner or _default_subagent_runner
        self.specs_dir.mkdir(parents=True, exist_ok=True)

    def new(self, path: Path) -> Path:
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path
        path.write_text(
            "---\nauto_advance: false\n---\n\n# New Spec\n\n## Goals\n\n## Requirements\n\n## Success Criteria\n",
            encoding="utf-8",
        )
        return path

    def plan(self, spec_path: Path) -> SpecRun:
        metadata, title, body = parse_spec(spec_path)
        spec_id = f"spec-{uuid.uuid4().hex[:10]}"
        subtasks = _fallback_plan(body)
        run = SpecRun(
            spec_id=spec_id,
            spec_path=str(spec_path),
            title=title,
            subtasks=subtasks,
            status="pending",
            auto_advance=bool(metadata.get("auto_advance", False)),
        )
        self._save(run)
        self._event(run.spec_id, "planned", {"subtasks": len(run.subtasks)})
        return run

    def run(self, spec_path: Path) -> SpecRun:
        run = self.plan(spec_path)
        run.status = "running"
        self._save(run)
        return self.resume(run.spec_id)

    def resume(self, spec_id: str) -> SpecRun:
        run = self.load(spec_id)
        run.status = "running"
        for subtask in topological_subtasks(run.subtasks):
            if subtask.status != SubtaskStatus.PENDING:
                continue
            if any(_by_id(run.subtasks, dep).status != SubtaskStatus.DONE for dep in subtask.depends_on):
                subtask.status = SubtaskStatus.BLOCKED
                subtask.notes = "dependency not done"
                continue
            run.current_subtask_id = subtask.id
            subtask.status = SubtaskStatus.RUNNING
            subtask.checkpoint_id = self._create_checkpoint(run, subtask)
            self._save(run)
            executor_notes = self.subagent_runner("executor", subtask.description, run, subtask)
            reviewer_notes = self.subagent_runner("reviewer", "\n".join(subtask.success_criteria), run, subtask)
            subtask.notes = "\n".join(item for item in [executor_notes, reviewer_notes] if item)
            if "BLOCKER" in reviewer_notes.upper() or "FAIL" in executor_notes.upper():
                subtask.status = SubtaskStatus.BLOCKED
                run.status = "paused"
                self._event(run.spec_id, "blocked", {"subtask": subtask.id, "notes": subtask.notes})
                self._save(run)
                return run
            subtask.status = SubtaskStatus.DONE
            self._event(run.spec_id, "subtask_done", {"subtask": subtask.id, "checkpointId": subtask.checkpoint_id})
            self._save(run)
        run.current_subtask_id = None
        run.status = "completed" if all(task.status == SubtaskStatus.DONE for task in run.subtasks) else "paused"
        self._save(run)
        return run

    def status(self, spec_id: str) -> SpecRun:
        return self.load(spec_id)

    def abort(self, spec_id: str) -> SpecRun:
        run = self.load(spec_id)
        run.status = "aborted"
        checkpoint = latest_checkpoint(run)
        if checkpoint and self.checkpoint_manager and hasattr(self.checkpoint_manager, "restore_checkpoint"):
            self.checkpoint_manager.restore_checkpoint(checkpoint)
        self._event(run.spec_id, "aborted", {"restoredCheckpointId": checkpoint or ""})
        self._save(run)
        return run

    def load(self, spec_id: str) -> SpecRun:
        path = self.specs_dir / spec_id / "spec.json"
        return SpecRun.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _save(self, run: SpecRun) -> None:
        root = self.specs_dir / run.spec_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "spec.json").write_text(json.dumps(run.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _event(self, spec_id: str, event: str, payload: Dict[str, Any]) -> None:
        root = self.specs_dir / spec_id
        root.mkdir(parents=True, exist_ok=True)
        with (root / "events.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": event, **payload}, ensure_ascii=False) + "\n")

    def _create_checkpoint(self, run: SpecRun, subtask: Subtask) -> Optional[str]:
        if not self.checkpoint_manager or not hasattr(self.checkpoint_manager, "create_checkpoint"):
            return None
        try:
            checkpoint = self.checkpoint_manager.create_checkpoint(
                [str(self.repo_root)],
                f"Before spec {run.spec_id} subtask {subtask.id}",
                "spec_subtask",
                ["spec", run.spec_id, subtask.id],
            )
            return getattr(checkpoint, "checkpoint_id", None)
        except Exception:
            return None


def parse_spec(path: Path) -> tuple[Dict[str, Any], str, str]:
    text = path.read_text(encoding="utf-8")
    metadata: Dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            loaded = yaml.safe_load(text[4:end]) or {}
            metadata = loaded if isinstance(loaded, dict) else {}
            body = text[end + 5:]
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    return metadata, title, body.strip()


def topological_subtasks(subtasks: List[Subtask]) -> List[Subtask]:
    by_id = {task.id: task for task in subtasks}
    visited: set[str] = set()
    result: List[Subtask] = []

    def visit(task: Subtask) -> None:
        if task.id in visited:
            return
        for dep in task.depends_on:
            if dep in by_id:
                visit(by_id[dep])
        visited.add(task.id)
        result.append(task)

    for task in subtasks:
        visit(task)
    return result


def latest_checkpoint(run: SpecRun) -> Optional[str]:
    for task in reversed(run.subtasks):
        if task.checkpoint_id:
            return task.checkpoint_id
    return None


def _by_id(subtasks: Iterable[Subtask], subtask_id: str) -> Subtask:
    for task in subtasks:
        if task.id == subtask_id:
            return task
    return Subtask(id=subtask_id, title=subtask_id, description="", status=SubtaskStatus.FAILED)


def _fallback_plan(body: str) -> List[Subtask]:
    headings = [line.strip("# ").strip() for line in body.splitlines() if line.startswith("## ")]
    titles = [heading for heading in headings if heading.lower() not in {"goals", "requirements", "success criteria"}]
    if not titles:
        titles = ["Plan implementation", "Implement changes", "Review and verify"]
    tasks: List[Subtask] = []
    previous = ""
    for index, title in enumerate(titles[:8], start=1):
        subtask_id = f"task-{index}"
        tasks.append(Subtask(
            id=subtask_id,
            title=title,
            description=f"Work on spec section: {title}",
            depends_on=[previous] if previous else [],
            success_criteria=[f"{title} is addressed"],
            estimated_tokens=1000,
        ))
        previous = subtask_id
    return tasks


def _default_subagent_runner(agent_name: str, prompt: str, run: SpecRun, subtask: Subtask) -> str:
    return f"{agent_name} completed {subtask.id}: {prompt[:120]}"
