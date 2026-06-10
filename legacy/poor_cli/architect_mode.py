"""Architect/editor dual-model mode.

Splits reasoning (expensive model) from editing (cheap model) to optimize
cost while maintaining quality. The architect model generates a plan,
then the editor model executes it using tools.

Additions (M4, 2026-04-14):
- ``PRESET_PAIRS`` gives named architect/editor pairs so users can pick by
  name (``/architect preset ak-ge`` style) rather than filling four config
  fields.
- ``ArchitectPlan`` + ``validate_plan`` accept the architect's structured
  JSON output (or a free-text plan) and normalize it before handing to the
  editor. Invalid plans are rejected so the editor doesn't execute garbage.
- Per-phase cost tracking: ``record_cost(phase, tokens, usd)`` accumulates
  architect vs editor spend so ``/cost architect`` can show where the money
  went.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)


# Named preset pairs. Keys are stable; users flip presets without retyping.
# Provider choices here MUST exist in provider_catalog.json; models are
# expected to be available (keys present) at the user's environment.
PRESET_PAIRS: Dict[str, Dict[str, str]] = {
    "anthropic-gemini": {
        "architect_provider": "anthropic",
        "architect_model": "claude-sonnet-4-20250514",
        "editor_provider": "gemini",
        "editor_model": "gemini-2.5-flash",
    },
    "openai-gemini": {
        "architect_provider": "openai",
        "architect_model": "gpt-5.1",
        "editor_provider": "gemini",
        "editor_model": "gemini-2.5-flash",
    },
    "anthropic-ollama": {
        "architect_provider": "anthropic",
        "architect_model": "claude-sonnet-4-20250514",
        "editor_provider": "ollama",
        "editor_model": "qwen2.5-coder",
    },
    "all-local-hf": {
        "architect_provider": "hf_local",
        "architect_model": "Qwen/Qwen2.5-7B",
        "editor_provider": "hf_local",
        "editor_model": "Qwen/Qwen2.5-3B",
    },
}


@dataclass
class ArchitectConfig:
    """Configuration for architect/editor dual-model mode."""
    enabled: bool = False
    architect_provider: str = "" # e.g. "anthropic"
    architect_model: str = "" # e.g. "claude-sonnet-4-20250514"
    editor_provider: str = "" # e.g. "gemini"
    editor_model: str = "" # e.g. "gemini-2.5-flash"

    def apply_preset(self, preset_name: str) -> bool:
        """Copy fields from a named preset. Returns True on success."""
        preset = PRESET_PAIRS.get(preset_name)
        if preset is None:
            return False
        self.architect_provider = preset["architect_provider"]
        self.architect_model = preset["architect_model"]
        self.editor_provider = preset["editor_provider"]
        self.editor_model = preset["editor_model"]
        return True


# ---------------------------------------------------------------------------
# Plan contract (M4): structured format the architect returns, validated
# before handing to the editor.
# ---------------------------------------------------------------------------

ARCHITECT_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["goal", "steps"],
    "properties": {
        "goal": {"type": "string"},
        "rationale": {"type": "string"},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "description"],
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "files": {"type": "array", "items": {"type": "string"}},
                    "acceptance": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


@dataclass
class ArchitectPlanStep:
    id: str
    description: str
    tools: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    acceptance: str = ""


@dataclass
class ArchitectPlan:
    goal: str
    steps: List[ArchitectPlanStep]
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "rationale": self.rationale,
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "tools": list(s.tools),
                    "files": list(s.files),
                    "acceptance": s.acceptance,
                }
                for s in self.steps
            ],
        }

    def render_prefix(self) -> str:
        """Human-readable plan prefix for the editor."""
        lines = ["## Plan from architect", f"Goal: {self.goal}"]
        if self.rationale:
            lines.append(f"Rationale: {self.rationale}")
        lines.append("")
        lines.append("Steps:")
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. ({step.id}) {step.description}")
            if step.files:
                lines.append(f"   files: {', '.join(step.files)}")
            if step.tools:
                lines.append(f"   tools: {', '.join(step.tools)}")
            if step.acceptance:
                lines.append(f"   acceptance: {step.acceptance}")
        lines.append("")
        lines.append("Execute each step with the appropriate tool.")
        return "\n".join(lines)


def validate_plan(raw: Any) -> Tuple[Optional[ArchitectPlan], List[str]]:
    """Parse + validate an architect response into a normalized ArchitectPlan.

    Accepts either a dict or a JSON string. Returns (plan, errors). If errors
    is non-empty, plan is None. Unknown keys are ignored (not errors). The
    ``steps`` array must have at least one entry with ``id`` and ``description``.
    """
    errors: List[str] = []
    if isinstance(raw, str):
        raw_stripped = raw.strip()
        # try to locate the JSON payload — architects sometimes wrap in ```json blocks
        block = re.search(r"```json\s*(.*?)\s*```", raw_stripped, re.DOTALL)
        payload_str = block.group(1).strip() if block else raw_stripped
        try:
            data = json.loads(payload_str)
        except (json.JSONDecodeError, ValueError):
            errors.append("invalid_json")
            return None, errors
    elif isinstance(raw, dict):
        data = raw
    else:
        errors.append("plan_must_be_object_or_json_string")
        return None, errors

    goal = str(data.get("goal", "")).strip()
    if not goal:
        errors.append("missing_goal")
    rationale = str(data.get("rationale", "")).strip()
    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        errors.append("steps_must_be_nonempty_array")
        return None, errors

    steps: List[ArchitectPlanStep] = []
    for i, entry in enumerate(steps_raw):
        if not isinstance(entry, dict):
            errors.append(f"step_{i}_not_object")
            continue
        step_id = str(entry.get("id", "")).strip()
        description = str(entry.get("description", "")).strip()
        if not step_id:
            errors.append(f"step_{i}_missing_id")
            continue
        if not description:
            errors.append(f"step_{i}_missing_description")
            continue
        steps.append(ArchitectPlanStep(
            id=step_id,
            description=description,
            tools=[str(t) for t in entry.get("tools", []) if isinstance(t, (str, bytes))],
            files=[str(f) for f in entry.get("files", []) if isinstance(f, (str, bytes))],
            acceptance=str(entry.get("acceptance", "")).strip(),
        ))
    if not steps:
        errors.append("no_valid_steps")
        return None, errors
    if errors:
        # soft errors (individual step skips) don't block the plan; only report
        return ArchitectPlan(goal=goal, steps=steps, rationale=rationale), errors
    return ArchitectPlan(goal=goal, steps=steps, rationale=rationale), []


class ArchitectMode:
    """Manages architect/editor model switching within a session."""

    def __init__(self, config: ArchitectConfig, lifecycle_service: Any = None):
        self._config = config
        self._lifecycle = lifecycle_service
        self._phase: str = "architect" # "architect" or "editor"
        self._current_plan: str = ""
        self._parsed_plan: Optional[ArchitectPlan] = None
        # per-phase cost tracking (M4)
        self._costs: Dict[str, Dict[str, float]] = {
            "architect": {"tokens": 0, "usd": 0.0, "calls": 0},
            "editor": {"tokens": 0, "usd": 0.0, "calls": 0},
        }

    def record_cost(self, phase: str, *, tokens: int = 0, usd: float = 0.0) -> None:
        """Track architect vs editor spend for `/cost architect` breakdown."""
        if phase not in self._costs:
            return
        bucket = self._costs[phase]
        bucket["tokens"] += int(max(0, tokens))
        bucket["usd"] += float(max(0.0, usd))
        bucket["calls"] += 1

    def cost_breakdown(self) -> Dict[str, Any]:
        """Return per-phase cost + total + ratio."""
        total_usd = self._costs["architect"]["usd"] + self._costs["editor"]["usd"]
        total_tokens = self._costs["architect"]["tokens"] + self._costs["editor"]["tokens"]
        return {
            "architect": dict(self._costs["architect"]),
            "editor": dict(self._costs["editor"]),
            "totalUsd": round(total_usd, 6),
            "totalTokens": total_tokens,
            "architectShare": round(
                self._costs["architect"]["usd"] / total_usd, 3
            ) if total_usd > 0 else 0.0,
        }

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.architect_provider) and bool(self._config.editor_provider)

    @property
    def phase(self) -> str:
        return self._phase

    def get_plan_prefix(self) -> str:
        """Return plan instruction prefix for the editor model."""
        if self._parsed_plan is not None:
            # structured form — cleaner for the editor
            return self._parsed_plan.render_prefix()
        if not self._current_plan:
            return ""
        return (
            "## Plan from architect model\n"
            "Execute the following plan using tools. Do not deviate.\n\n"
            f"{self._current_plan}\n\n"
            "## Your task\n"
            "Implement the plan above step by step."
        )

    async def switch_to_architect(self, core: Any) -> bool:
        """Switch to the architect (reasoning) model."""
        if not self.enabled:
            return False
        try:
            if self._lifecycle:
                await self._lifecycle.switch_provider(
                    self._config.architect_provider,
                    self._config.architect_model,
                )
            else:
                core.provider.switch_model(self._config.architect_model)
            self._phase = "architect"
            logger.info("switched to architect model: %s/%s", self._config.architect_provider, self._config.architect_model)
            return True
        except Exception as e:
            logger.warning("failed to switch to architect model: %s", e)
            return False

    async def switch_to_editor(self, core: Any, plan: str) -> bool:
        """Switch to the editor (cheap) model with the plan as context.

        When the plan parses as a valid structured ArchitectPlan, the editor
        receives the normalized ``render_prefix`` form — clearer, more scannable,
        and validated. Free-text plans still work; they bypass structure.
        """
        if not self.enabled:
            return False
        self._current_plan = plan
        parsed, errors = validate_plan(plan)
        if parsed is not None:
            self._parsed_plan = parsed
            if errors:
                logger.info("architect plan accepted with soft errors: %s", errors)
        elif errors:
            logger.warning("architect plan failed validation: %s", errors)
            self._parsed_plan = None
        try:
            if self._lifecycle:
                await self._lifecycle.switch_provider(
                    self._config.editor_provider,
                    self._config.editor_model,
                )
            else:
                core.provider.switch_model(self._config.editor_model)
            self._phase = "editor"
            logger.info("switched to editor model: %s/%s", self._config.editor_provider, self._config.editor_model)
            return True
        except Exception as e:
            logger.warning("failed to switch to editor model: %s", e)
            return False

    async def reset_to_architect(self, core: Any) -> bool:
        """Reset back to architect for next user turn."""
        self._current_plan = ""
        return await self.switch_to_architect(core)

    def should_switch_to_editor(self, response_text: str) -> bool:
        """Heuristic: if architect response looks like a plan, switch to editor."""
        if not self.enabled or self._phase != "architect":
            return False
        plan_indicators = ["## plan", "## steps", "step 1", "1.", "- [ ]", "first,", "implementation plan"]
        text_lower = response_text.lower()
        return any(indicator in text_lower for indicator in plan_indicators)

    async def try_latent_bridge(self, task: str) -> Optional[str]:
        """Attempt latent tensor passing between architect→editor via local models.
        Returns editor output if latent_comm is enabled and compatible, else None."""
        try:
            from .research_loader import load_research_module
            latent_communication = load_research_module("latent_communication")
            if latent_communication is None:
                return None
            compat = latent_communication.is_latent_compatible()
            if not compat.get("feasible", False):
                return None
            bridge = latent_communication.ArchitectLatentBridge()
            result = bridge.architect_to_editor(task)
            return result
        except Exception as e:
            logger.debug("latent bridge not available: %s", e)
            return None

    @property
    def parsed_plan(self) -> Optional[ArchitectPlan]:
        """Return the structured plan if validation succeeded, else None."""
        return self._parsed_plan

    def format_status(self) -> Dict[str, Any]:
        latent_available = False
        try:
            from .research_loader import load_research_module
            latent_communication = load_research_module("latent_communication")
            if latent_communication is not None:
                latent_available = latent_communication.is_latent_compatible().get("feasible", False)
        except Exception:
            pass
        return {
            "enabled": self.enabled,
            "phase": self._phase,
            "architect": f"{self._config.architect_provider}/{self._config.architect_model}",
            "editor": f"{self._config.editor_provider}/{self._config.editor_model}",
            "has_plan": bool(self._current_plan),
            "plan_validated": self._parsed_plan is not None,
            "plan_step_count": len(self._parsed_plan.steps) if self._parsed_plan else 0,
            "latent_bridge_available": latent_available,
            "cost_breakdown": self.cost_breakdown(),
        }
