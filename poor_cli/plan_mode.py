"""
Plan and Preview Mode for poor-cli

Allows users to preview AI actions before execution for enhanced safety.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

PLAN_BOARD_COLUMNS = ("todo", "doing", "blocked", "done")


def _normalize_board_status(value: Any) -> str:
    raw = str(value or "todo").strip().lower().replace("_", "-")
    if raw in {"pending", "todo", "to-do"}:
        return "todo"
    if raw in {"running", "doing", "in-progress", "inprogress"}:
        return "doing"
    if raw in {"blocked", "block"}:
        return "blocked"
    if raw in {"done", "complete", "completed", "skipped"}:
        return "done"
    return "todo"


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class PlanBoardStep:
    id: str
    description: str
    status: str = "todo"
    details: str = ""
    dependencies: List[int] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_raw(cls, raw: Any, index: int, existing: Optional["PlanBoardStep"] = None) -> "PlanBoardStep":
        if isinstance(raw, dict):
            description = str(raw.get("description") or raw.get("title") or raw.get("text") or raw.get(1) or "").strip()
            status = _normalize_board_status(raw.get("status") or (existing.status if existing else "todo"))
            details = str(raw.get("details") or raw.get("body") or "")
            deps = raw.get("dependencies") if isinstance(raw.get("dependencies"), list) else []
            step_id = str(raw.get("id") or raw.get("stepId") or (existing.id if existing else "")).strip()
        else:
            description = str(raw or "").strip()
            status = existing.status if existing else "todo"
            details = existing.details if existing else ""
            deps = list(existing.dependencies) if existing else []
            step_id = existing.id if existing else ""
        if not step_id:
            step_id = f"step-{index}-{uuid.uuid4().hex[:8]}"
        return cls(
            id=step_id,
            description=description or f"step {index}",
            status=status,
            details=details,
            dependencies=[int(dep) for dep in deps if str(dep).lstrip("-").isdigit()],
            created_at=existing.created_at if existing else _now_iso(),
            updated_at=_now_iso(),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any], index: int) -> "PlanBoardStep":
        return cls.from_raw(data, index)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "details": self.details,
            "dependencies": list(self.dependencies),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class PlanBoardState:
    plan_id: str = ""
    summary: str = ""
    original_request: str = ""
    steps: List[PlanBoardStep] = field(default_factory=list)
    columns: List[str] = field(default_factory=lambda: list(PLAN_BOARD_COLUMNS))
    updated_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanBoardState":
        steps = data.get("steps") if isinstance(data.get("steps"), list) else []
        return cls(
            plan_id=str(data.get("planId") or data.get("plan_id") or ""),
            summary=str(data.get("summary") or ""),
            original_request=str(data.get("originalRequest") or data.get("original_request") or ""),
            steps=[PlanBoardStep.from_dict(step, idx + 1) for idx, step in enumerate(steps) if isinstance(step, dict)],
            columns=list(PLAN_BOARD_COLUMNS),
            updated_at=str(data.get("updatedAt") or data.get("updated_at") or _now_iso()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planId": self.plan_id,
            "summary": self.summary,
            "originalRequest": self.original_request,
            "columns": list(PLAN_BOARD_COLUMNS),
            "steps": [step.to_dict() for step in self.steps],
            "updatedAt": self.updated_at,
        }


class PlanBoardStore:
    """Durable plan board state for editor RPC clients."""

    def __init__(self, repo_root: Optional[Path] = None, path: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.path = path or (self.repo_root / ".poor-cli" / "plan_board.json")
        self.state = self._load()

    def _load(self) -> PlanBoardState:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return PlanBoardState.from_dict(data)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load plan board: %s", exc)
        return PlanBoardState()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> Dict[str, Any]:
        return self.state.to_dict()

    def seed(self, plan_id: str, summary: str, original_request: str, steps: List[Any]) -> Dict[str, Any]:
        by_id = {step.id: step for step in self.state.steps}
        by_description = {step.description: step for step in self.state.steps}
        same_plan = not plan_id or plan_id == self.state.plan_id
        new_steps: List[PlanBoardStep] = []
        for index, raw in enumerate(steps, start=1):
            raw_id = str(raw.get("id") or raw.get("stepId") or "") if isinstance(raw, dict) else ""
            raw_desc = str(raw.get("description") or raw.get("title") or raw.get("text") or "") if isinstance(raw, dict) else str(raw or "")
            existing = by_id.get(raw_id) if same_plan and raw_id else by_description.get(raw_desc) if same_plan else None
            new_steps.append(PlanBoardStep.from_raw(raw, index, existing=existing))
        self.state = PlanBoardState(
            plan_id=plan_id or self.state.plan_id or f"plan-{uuid.uuid4().hex[:8]}",
            summary=summary,
            original_request=original_request,
            steps=new_steps,
            columns=list(PLAN_BOARD_COLUMNS),
            updated_at=_now_iso(),
        )
        self._save()
        return self.list()

    def _find_step(self, params: Dict[str, Any]) -> PlanBoardStep:
        step_id = str(params.get("stepId") or params.get("step_id") or params.get("id") or "").strip()
        if step_id:
            for step in self.state.steps:
                if step.id == step_id:
                    return step
        raw_index = params.get("index")
        if raw_index is not None:
            try:
                idx = int(raw_index) - 1
                if 0 <= idx < len(self.state.steps):
                    return self.state.steps[idx]
            except (TypeError, ValueError):
                pass
        raise ValueError("stepId or valid index is required")

    def _set_status(self, step: PlanBoardStep, status: str) -> Dict[str, Any]:
        step.status = _normalize_board_status(status)
        step.updated_at = _now_iso()
        self.state.updated_at = _now_iso()
        self._save()
        return self.list()

    def advance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        step = self._find_step(params)
        next_status = {"todo": "doing", "doing": "done", "blocked": "doing", "done": "done"}[step.status]
        return self._set_status(step, next_status)

    def regress(self, params: Dict[str, Any]) -> Dict[str, Any]:
        step = self._find_step(params)
        next_status = {"todo": "todo", "doing": "todo", "blocked": "todo", "done": "doing"}[step.status]
        return self._set_status(step, next_status)

    def block(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._set_status(self._find_step(params), "blocked")

    def add(self, params: Dict[str, Any]) -> Dict[str, Any]:
        description = str(params.get("description") or params.get("text") or "").strip()
        if not description:
            raise ValueError("description is required")
        step = PlanBoardStep.from_raw(
            {"description": description, "status": params.get("status") or "todo", "details": params.get("details") or ""},
            len(self.state.steps) + 1,
        )
        self.state.steps.append(step)
        self.state.updated_at = _now_iso()
        self._save()
        return self.list()

    def delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        step = self._find_step(params)
        self.state.steps = [candidate for candidate in self.state.steps if candidate.id != step.id]
        self.state.updated_at = _now_iso()
        self._save()
        return self.list()


class PlanStepType(Enum):
    """Types of plan steps"""
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    DELETE_FILE = "delete_file"
    CREATE_DIR = "create_directory"
    BASH_COMMAND = "bash"
    GIT_OPERATION = "git"
    SEARCH = "search"
    OTHER = "other"


class RiskLevel(Enum):
    """Risk levels for operations"""
    SAFE = "safe"        # Read-only operations
    LOW = "low"          # Minor modifications
    MEDIUM = "medium"    # File modifications
    HIGH = "high"        # Destructive operations
    CRITICAL = "critical"  # System-level operations


@dataclass
class PlanStep:
    """A single step in an execution plan"""
    step_number: int
    step_type: PlanStepType
    description: str
    tool_name: str
    tool_args: Dict[str, Any]
    risk_level: RiskLevel
    affected_files: List[str] = field(default_factory=list)
    estimated_duration: str = "instant"
    dependencies: List[int] = field(default_factory=list)  # Step numbers this depends on

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "step_number": self.step_number,
            "step_type": self.step_type.value,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "risk_level": self.risk_level.value,
            "affected_files": self.affected_files,
            "estimated_duration": self.estimated_duration,
            "dependencies": self.dependencies
        }


@dataclass
class ExecutionPlan:
    """Complete execution plan for a user request"""
    plan_id: str
    user_request: str
    summary: str
    steps: List[PlanStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    estimated_total_duration: str = "unknown"
    overall_risk_level: RiskLevel = RiskLevel.SAFE

    def add_step(self, step: PlanStep):
        """Add a step to the plan"""
        self.steps.append(step)
        # Update overall risk level
        if step.risk_level.value == "critical":
            self.overall_risk_level = RiskLevel.CRITICAL
        elif step.risk_level.value == "high" and self.overall_risk_level != RiskLevel.CRITICAL:
            self.overall_risk_level = RiskLevel.HIGH
        elif step.risk_level.value == "medium" and self.overall_risk_level not in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            self.overall_risk_level = RiskLevel.MEDIUM
        elif step.risk_level.value == "low" and self.overall_risk_level == RiskLevel.SAFE:
            self.overall_risk_level = RiskLevel.LOW

    def get_affected_files(self) -> List[str]:
        """Get all files affected by this plan"""
        files = []
        for step in self.steps:
            files.extend(step.affected_files)
        return list(set(files))

    def get_high_risk_steps(self) -> List[PlanStep]:
        """Get all high-risk steps"""
        return [s for s in self.steps if s.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "plan_id": self.plan_id,
            "user_request": self.user_request,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
            "estimated_total_duration": self.estimated_total_duration,
            "overall_risk_level": self.overall_risk_level.value,
            "affected_files": self.get_affected_files(),
            "high_risk_steps": len(self.get_high_risk_steps())
        }
