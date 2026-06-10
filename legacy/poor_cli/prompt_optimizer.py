from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from .adaptive_budget import AdaptiveBudgetController


@dataclass(frozen=True)
class PromptDecision:
    system_prompt_level: str
    skill_whitelist: List[str]
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "level": self.system_prompt_level,
            "skillWhitelist": list(self.skill_whitelist),
            "reasoning": self.reasoning,
        }


class PromptOptimizer:
    """Choose smaller prompt surfaces when recent reward says it is safe."""

    def __init__(self, controller: AdaptiveBudgetController):
        self._ctl = controller
        self.last_decision = PromptDecision("full", [], "not evaluated")

    def choose(self, available_skills: Set[str], task_complexity: float) -> PromptDecision:
        stats = self._stats()
        recent = float(getattr(stats, "avg_reward_recent", 0.0) or 0.0)
        complexity = max(0.0, min(1.0, float(task_complexity or 0.0)))
        if complexity < 0.3 and recent > 0.7:
            self.last_decision = PromptDecision(
                "minimal",
                self._minimal_skills(available_skills),
                f"low complexity {complexity:.2f}, high reward {recent:.2f}",
            )
            return self.last_decision
        if complexity < 0.6 and recent > 0.4:
            self.last_decision = PromptDecision(
                "trim",
                self._trimmed_skills(available_skills),
                f"mid complexity {complexity:.2f}, ok reward {recent:.2f}",
            )
            return self.last_decision
        self.last_decision = PromptDecision(
            "full",
            sorted(available_skills),
            f"complexity {complexity:.2f}, reward {recent:.2f}",
        )
        return self.last_decision

    def _stats(self):
        stats = getattr(self._ctl, "stats", None)
        return stats() if callable(stats) else stats

    def _minimal_skills(self, available: Set[str]) -> List[str]:
        keep = {"core", "economy", "readonly"}
        return sorted(skill for skill in available if skill in keep)

    def _trimmed_skills(self, available: Set[str]) -> List[str]:
        drop = {"deployment", "review", "debugging"}
        return sorted(skill for skill in available if skill not in drop)
