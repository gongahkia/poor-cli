"""Intelligent model routing engine.

Classifies task complexity and routes to the cheapest capable model,
cascading to more expensive models on low-confidence responses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import setup_logger
from .provider_catalog import (
    canonical_provider_name,
    _catalog_payload,
)

logger = setup_logger(__name__)


class TaskComplexity(Enum):
    TRIVIAL = "trivial"   # typo fix, simple rename, "what does X do"
    SIMPLE = "simple"     # single-file edit, straightforward bug fix
    MODERATE = "moderate" # multi-file change, needs reasoning
    COMPLEX = "complex"   # architectural decision, multi-step agent loop


# ── heuristic patterns ───────────────────────────────────────────────

_TRIVIAL_PATTERNS = re.compile(
    r"^(fix\s+typo|rename\s+\w+|what\s+(does|is)\s+\w+|yes|no|ok|thanks|hi|hello)\b",
    re.I,
)
_COMPLEX_VERBS = frozenset({
    "refactor", "implement", "migrate", "restructure", "optimize",
    "redesign", "rewrite", "architect", "integrate", "convert",
    "overhaul", "consolidate", "modularize", "parallelize",
    "design", "plan", "analyze",
})
_TOOL_KEYWORDS = frozenset({
    "file", "write", "create", "edit", "delete", "run", "execute",
    "bash", "shell", "command", "patch", "install", "build", "test",
    "deploy", "mkdir", "grep", "find", "git",
})
_QUESTION_RE = re.compile(
    r"^(what|how|why|where|when|which|can|does|is|are|do|explain|describe)\b", re.I
)
_FILE_PATH_RE = re.compile(r"[\w\-]+\.\w{1,6}")
_CODE_BLOCK_RE = re.compile(r"```")
_MULTI_FILE_RE = re.compile(r"([\w\-]+\.\w{1,6})", re.I)


@dataclass
class ClassifierContext:
    """Optional session context fed into the classifier."""
    conversation_depth: int = 0 # number of prior turns
    files_in_context: int = 0   # files currently pinned/referenced
    tool_calls_so_far: int = 0  # cumulative tool calls this session


def classify_complexity(
    prompt: str,
    ctx: Optional[ClassifierContext] = None,
) -> TaskComplexity:
    """Classify user prompt into a complexity tier using structural heuristics."""
    ctx = ctx or ClassifierContext()
    stripped = prompt.strip()
    length = len(stripped)
    lower = stripped.lower()

    # trivial: very short or matches trivial patterns
    if length < 30 and _TRIVIAL_PATTERNS.match(stripped):
        return TaskComplexity.TRIVIAL
    if length < 15:
        return TaskComplexity.TRIVIAL

    complex_hits = sum(1 for v in _COMPLEX_VERBS if v in lower)
    tool_hits = sum(1 for kw in _TOOL_KEYWORDS if kw in lower)
    has_code_block = bool(_CODE_BLOCK_RE.search(stripped))
    file_refs = len(_MULTI_FILE_RE.findall(stripped))
    is_question = bool(_QUESTION_RE.match(stripped))

    # complex: explicit complex verbs, code blocks, many file refs, or long prompt
    if complex_hits >= 2 or (complex_hits >= 1 and file_refs >= 2):
        return TaskComplexity.COMPLEX
    if has_code_block and tool_hits >= 2:
        return TaskComplexity.COMPLEX
    if length > 2000:
        return TaskComplexity.COMPLEX
    if ctx.conversation_depth >= 10 and tool_hits >= 2:
        return TaskComplexity.COMPLEX

    # moderate: some file refs, tool keywords, or moderate length
    if complex_hits >= 1:
        return TaskComplexity.MODERATE
    if file_refs >= 2 or tool_hits >= 2:
        return TaskComplexity.MODERATE
    if length > 800:
        return TaskComplexity.MODERATE
    if ctx.files_in_context >= 3 and tool_hits >= 1:
        return TaskComplexity.MODERATE

    # simple: questions, single file ops, short prompts
    if is_question and tool_hits == 0:
        return TaskComplexity.TRIVIAL
    if tool_hits >= 1 or file_refs >= 1:
        return TaskComplexity.SIMPLE

    return TaskComplexity.SIMPLE


# ── routing table ────────────────────────────────────────────────────

# tier ordering within a provider: cheap → balanced → quality
_TIER_ORDER = {"cheap": 0, "private": 0, "balanced": 1, "quality": 2}


def _build_default_routing_table(provider: str) -> Dict[TaskComplexity, str]:
    """Build routing table from provider_catalog.json model tiers."""
    canonical = canonical_provider_name(provider)
    payload = _catalog_payload().get("providers", {}).get(canonical, {})
    tiers = payload.get("modelTiers", {})
    if not tiers:
        return {}

    # sort models by cost (ascending)
    sorted_models: List[Tuple[str, Dict]] = sorted(
        tiers.items(), key=lambda x: float(x[1].get("cost_1k_in", 0))
    )
    if not sorted_models:
        return {}

    cheapest = sorted_models[0][0]
    mid = sorted_models[len(sorted_models) // 2][0] if len(sorted_models) > 1 else cheapest
    expensive = sorted_models[-1][0]

    return {
        TaskComplexity.TRIVIAL: cheapest,
        TaskComplexity.SIMPLE: cheapest,
        TaskComplexity.MODERATE: mid,
        TaskComplexity.COMPLEX: expensive,
    }


def _get_next_tier_model(provider: str, current_model: str) -> Optional[str]:
    """Get the next more expensive model for cascade escalation."""
    canonical = canonical_provider_name(provider)
    payload = _catalog_payload().get("providers", {}).get(canonical, {})
    tiers = payload.get("modelTiers", {})
    if not tiers:
        return None
    sorted_models = sorted(
        tiers.items(), key=lambda x: float(x[1].get("cost_1k_in", 0))
    )
    model_names = [m[0] for m in sorted_models]
    try:
        idx = model_names.index(current_model)
    except ValueError:
        return None
    if idx + 1 < len(model_names):
        return model_names[idx + 1]
    return None # already at top tier


# ── confidence detection ─────────────────────────────────────────────

_LOW_CONFIDENCE_PATTERNS = [
    re.compile(r"\bi'?m not sure\b", re.I),
    re.compile(r"\bi don'?t know\b", re.I),
    re.compile(r"\bI cannot verify\b", re.I),
    re.compile(r"\bmight be\b", re.I),
    re.compile(r"\bpossibly\b", re.I),
    re.compile(r"\bI think\b", re.I),
    re.compile(r"\bnot confident\b", re.I),
    re.compile(r"\[Speculation\]"),
    re.compile(r"\[Unverified\]"),
    re.compile(r"\[Inference\]"),
]


def detect_low_confidence(response_text: str) -> bool:
    """Check if response contains low-confidence markers."""
    if not response_text or len(response_text) < 20:
        return True # empty/stub response = low confidence
    hits = sum(1 for p in _LOW_CONFIDENCE_PATTERNS if p.search(response_text))
    return hits >= 2


# ── routing decision ─────────────────────────────────────────────────

@dataclass
class RoutingDecision:
    """Record of a routing decision for logging/analytics."""
    complexity: TaskComplexity
    selected_model: str
    provider: str
    escalated: bool = False
    escalated_from: Optional[str] = None
    economy_mode: str = "balanced"
    reason: str = ""


@dataclass
class RouterConfig:
    """Configurable router settings."""
    enabled: bool = True
    max_cascade_retries: int = 1 # max escalation steps
    custom_routing_table: Optional[Dict[str, Dict[str, str]]] = None # provider -> {complexity -> model}


class ModelRouter:
    """Routes queries to the cheapest capable model."""

    def __init__(self, config: Optional[RouterConfig] = None):
        self._config = config or RouterConfig()
        self._routing_log: List[RoutingDecision] = []
        self._tables_cache: Dict[str, Dict[TaskComplexity, str]] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def routing_log(self) -> List[RoutingDecision]:
        return self._routing_log

    def get_routing_table(self, provider: str) -> Dict[TaskComplexity, str]:
        """Get or build routing table for a provider."""
        canonical = canonical_provider_name(provider)
        if canonical in self._tables_cache:
            return self._tables_cache[canonical]

        # check custom overrides first
        custom = self._config.custom_routing_table
        if custom and canonical in custom:
            table = {}
            for complexity_str, model in custom[canonical].items():
                try:
                    table[TaskComplexity(complexity_str)] = model
                except ValueError:
                    logger.warning("unknown complexity level in custom table: %s", complexity_str)
            self._tables_cache[canonical] = table
            return table

        table = _build_default_routing_table(canonical)
        self._tables_cache[canonical] = table
        return table

    def select_model(
        self,
        prompt: str,
        provider: str,
        current_model: str,
        economy_preset: str = "balanced",
        user_explicit_model: bool = False,
        ctx: Optional[ClassifierContext] = None,
    ) -> RoutingDecision:
        """Select the best model for this prompt.

        Returns a RoutingDecision. Caller decides whether to actually switch.
        """
        # user explicitly set model via /switch -> no routing
        if user_explicit_model or not self.enabled:
            decision = RoutingDecision(
                complexity=TaskComplexity.SIMPLE,
                selected_model=current_model,
                provider=provider,
                economy_mode=economy_preset,
                reason="user_override" if user_explicit_model else "routing_disabled",
            )
            return decision

        # quality mode -> always use current (top-tier) model
        if economy_preset == "quality":
            decision = RoutingDecision(
                complexity=TaskComplexity.COMPLEX,
                selected_model=current_model,
                provider=provider,
                economy_mode=economy_preset,
                reason="quality_mode",
            )
            return decision

        complexity = classify_complexity(prompt, ctx)
        table = self.get_routing_table(provider)

        if not table:
            decision = RoutingDecision(
                complexity=complexity,
                selected_model=current_model,
                provider=provider,
                economy_mode=economy_preset,
                reason="no_routing_table",
            )
            return decision

        # frugal mode: bias toward cheaper tier
        effective_complexity = complexity
        if economy_preset == "frugal":
            if complexity == TaskComplexity.MODERATE:
                effective_complexity = TaskComplexity.SIMPLE
            elif complexity == TaskComplexity.COMPLEX:
                effective_complexity = TaskComplexity.MODERATE

        selected = table.get(effective_complexity, current_model)
        decision = RoutingDecision(
            complexity=complexity,
            selected_model=selected,
            provider=provider,
            economy_mode=economy_preset,
            reason=f"routed_{complexity.value}",
        )
        self._routing_log.append(decision)
        logger.info(
            "routing: complexity=%s model=%s provider=%s preset=%s",
            complexity.value, selected, provider, economy_preset,
        )
        return decision

    def should_cascade(
        self,
        response_text: str,
        current_decision: RoutingDecision,
    ) -> Optional[RoutingDecision]:
        """Check if response warrants escalation to a more expensive model.

        Returns a new RoutingDecision if escalation needed, None otherwise.
        """
        if not self.enabled:
            return None
        if current_decision.economy_mode == "quality":
            return None
        if current_decision.escalated:
            return None # already escalated once

        # check cascade retry limit
        recent_escalations = sum(1 for d in self._routing_log[-5:] if d.escalated)
        if recent_escalations >= self._config.max_cascade_retries:
            return None

        if not detect_low_confidence(response_text):
            return None

        next_model = _get_next_tier_model(
            current_decision.provider,
            current_decision.selected_model,
        )
        if not next_model or next_model == current_decision.selected_model:
            return None

        escalated = RoutingDecision(
            complexity=current_decision.complexity,
            selected_model=next_model,
            provider=current_decision.provider,
            escalated=True,
            escalated_from=current_decision.selected_model,
            economy_mode=current_decision.economy_mode,
            reason=f"cascade_from_{current_decision.selected_model}",
        )
        self._routing_log.append(escalated)
        logger.info(
            "cascade: %s -> %s (low confidence detected)",
            current_decision.selected_model, next_model,
        )
        return escalated

    def get_routing_stats(self) -> Dict[str, Any]:
        """Return routing analytics for /cost display."""
        if not self._routing_log:
            return {"total_decisions": 0}
        total = len(self._routing_log)
        escalations = sum(1 for d in self._routing_log if d.escalated)
        by_complexity = {}
        for d in self._routing_log:
            key = d.complexity.value
            by_complexity[key] = by_complexity.get(key, 0) + 1
        return {
            "total_decisions": total,
            "escalations": escalations,
            "by_complexity": by_complexity,
        }

    def clear_log(self) -> None:
        self._routing_log.clear()
