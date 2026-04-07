"""Architect/editor dual-model mode.

Splits reasoning (expensive model) from editing (cheap model) to optimize
cost while maintaining quality. The architect model generates a plan,
then the editor model executes it using tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class ArchitectConfig:
    """Configuration for architect/editor dual-model mode."""
    enabled: bool = False
    architect_provider: str = "" # e.g. "anthropic"
    architect_model: str = "" # e.g. "claude-sonnet-4-20250514"
    editor_provider: str = "" # e.g. "gemini"
    editor_model: str = "" # e.g. "gemini-2.5-flash"


class ArchitectMode:
    """Manages architect/editor model switching within a session."""

    def __init__(self, config: ArchitectConfig, lifecycle_service: Any = None):
        self._config = config
        self._lifecycle = lifecycle_service
        self._phase: str = "architect" # "architect" or "editor"
        self._current_plan: str = ""

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.architect_provider) and bool(self._config.editor_provider)

    @property
    def phase(self) -> str:
        return self._phase

    def get_plan_prefix(self) -> str:
        """Return plan instruction prefix for the editor model."""
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
        """Switch to the editor (cheap) model with the plan as context."""
        if not self.enabled:
            return False
        self._current_plan = plan
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

    def format_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "phase": self._phase,
            "architect": f"{self._config.architect_provider}/{self._config.architect_model}",
            "editor": f"{self._config.editor_provider}/{self._config.editor_model}",
            "has_plan": bool(self._current_plan),
        }
