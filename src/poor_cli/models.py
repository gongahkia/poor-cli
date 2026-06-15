from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


@dataclass(frozen=True)
class Budget:
    mode: str = "balanced"
    max_usd: float | None = None
    max_parallel_agents: int = 1
    max_calls: int | None = None
    max_tokens: int | None = None
    max_wall_seconds: int | None = None
    strict_pricing: bool = False


@dataclass(frozen=True)
class AgentInfo:
    agent_id: str
    name: str
    command: str
    version: str = "unknown"
    provider: str = "local"
    capabilities: list[str] = field(default_factory=list)
    default_model: str | None = None
    context_window_hint: int | None = None
    cost_profile: dict[str, Any] = field(default_factory=dict)
    invocation_adapter: str = "generic"


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    objective: str
    task_type: str = "implementation"
    complexity: str = "medium"
    risk: str = "medium"
    required_context: str = "small"
    dependencies: list[str] = field(default_factory=list)
    suggested_agent: str | None = None
    validation: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    plan_id: str
    problem_summary: str
    architecture_assessment: str
    assumptions: list[str]
    risks: list[str]
    tasks: list[TaskSpec]
    validation_strategy: list[str]
    routing_strategy: str
    estimated_cost: dict[str, Any]
    requires_user_confirmation: bool = True


@dataclass(frozen=True)
class ContextPacket:
    packet_id: str
    run_id: str
    task_id: str
    token_estimate: int
    included_files: list[str]
    included_summaries: list[str]
    constraints: list[str]
    task_prompt: str
    validation_instructions: list[str]
    handoff_instructions: list[str]


@dataclass(frozen=True)
class Event:
    event_id: str
    run_id: str
    task_id: str | None
    type: str
    created_at: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    run_id: str
    task_id: str | None
    kind: str
    sha256: str
    size: int
    media_type: str
    created_at: str
    path: str


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value
