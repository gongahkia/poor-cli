"""Economy mode: proactive cost reduction for poor-cli."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, Tuple


@dataclass
class EconomyConfig:
    """Economy mode settings — toggleable cost-reduction knobs."""
    preset: str = "balanced" # frugal | balanced | quality | custom
    auto_downshift: bool = True # auto-pick cheaper model for simple prompts
    downshift_threshold_chars: int = 500 # prompts shorter than this -> cheap model
    downshift_exclude_tools: bool = True # skip downshift if tools likely needed
    prompt_distill: bool = True # strip whitespace, dedup before sending
    strip_code_comments: bool = False # aggressive: remove // and # comments from context
    dedup_context: bool = True # deduplicate file content already in history
    terse_system_prompt: bool = False # inject "be extremely concise" directive
    economy_max_tokens: int = 0 # cap output tokens in economy mode (0 = model default)
    tool_call_budget: int = 0 # max tool calls per request (0 = use agentic.max_iterations)
    prefer_batched_reads: bool = True # combine multiple file reads
    context_dedup: bool = True # skip re-reading files already in conversation
    response_cache: bool = False # cache identical prompts
    response_cache_ttl: int = 300 # seconds
    diff_only_reads: bool = False # only include changed lines vs last read
    idle_compact_seconds: int = 0 # auto-compact after N seconds idle (0 = disabled)
    compress_after_turns: int = 0 # override ContextCompressionConfig.compress_after_turns (0 = use default)
    tool_strip_chars: int = 200 # max chars per tool result in compressed history
    auto_compress_pressure_pct: float = 70.0 # auto-compress when context pressure exceeds this %
    budget_downshift_pct: float = 60.0 # auto-downshift to cheapest model when session cost hits this % of budget


ECONOMY_PRESETS: Dict[str, Dict[str, Any]] = {
    "frugal": {
        "auto_downshift": True,
        "downshift_threshold_chars": 300,
        "prompt_distill": True,
        "strip_code_comments": True,
        "dedup_context": True,
        "terse_system_prompt": True,
        "economy_max_tokens": 2048,
        "tool_call_budget": 8,
        "prefer_batched_reads": True,
        "context_dedup": True,
        "response_cache": True,
        "diff_only_reads": True,
        "idle_compact_seconds": 60,
        "compress_after_turns": 6,
        "tool_strip_chars": 50,
        "auto_compress_pressure_pct": 60.0,
        "budget_downshift_pct": 50.0,
    },
    "balanced": {
        "auto_downshift": True,
        "downshift_threshold_chars": 500,
        "prompt_distill": True,
        "strip_code_comments": False,
        "dedup_context": True,
        "terse_system_prompt": False,
        "economy_max_tokens": 0,
        "tool_call_budget": 0,
        "prefer_batched_reads": True,
        "context_dedup": True,
        "response_cache": True, # safe: hash-keyed, TTL-bounded, skipped for mutation prompts
        "diff_only_reads": True, # first read returns full; re-reads return diff or [unchanged]
        "idle_compact_seconds": 180, # auto-compact after 3 min idle
        "compress_after_turns": 10,
        "tool_strip_chars": 200,
        "auto_compress_pressure_pct": 70.0,
        "budget_downshift_pct": 60.0,
    },
    "quality": {
        "auto_downshift": False,
        "downshift_threshold_chars": 500,
        "prompt_distill": False,
        "strip_code_comments": False,
        "dedup_context": False,
        "terse_system_prompt": False,
        "economy_max_tokens": 0,
        "tool_call_budget": 0,
        "prefer_batched_reads": False,
        "context_dedup": False,
        "response_cache": False,
        "diff_only_reads": False,
        "idle_compact_seconds": 0,
        "compress_after_turns": 0, # 0 = use default (no override)
        "tool_strip_chars": 500,
        "auto_compress_pressure_pct": 0, # disabled in quality mode
        "budget_downshift_pct": 0, # disabled in quality mode
    },
}


def apply_economy_preset(config: EconomyConfig, preset: str) -> None:
    """Apply a named preset to an EconomyConfig in-place."""
    values = ECONOMY_PRESETS.get(preset)
    if not values:
        return
    config.preset = preset
    for k, v in values.items():
        if hasattr(config, k):
            setattr(config, k, v)


# ── Prompt complexity classification ──────────────────────────────────

_TOOL_KEYWORDS = frozenset({
    "file", "write", "create", "edit", "delete", "run", "execute",
    "bash", "shell", "command", "patch", "install", "build", "test",
    "deploy", "mkdir", "touch", "grep", "find", "git",
})
_COMPLEX_VERBS = frozenset({
    "refactor", "implement", "migrate", "restructure", "optimize",
    "redesign", "rewrite", "architect", "integrate", "convert",
    "overhaul", "consolidate", "modularize", "parallelize",
})
_QUESTION_RE = re.compile(r"^(what|how|why|where|when|which|can|does|is|are|do|explain|describe)\b", re.I)
_FILE_PATH_RE = re.compile(r"[\w\-]+\.\w{1,6}") # e.g. foo.py, bar.ts
_CODE_BLOCK_RE = re.compile(r"```")
_INDENTED_LINE_RE = re.compile(r"^[ \t]{4,}", re.M)


def classify_prompt_complexity(prompt: str) -> str:
    """Classify prompt as 'simple', 'moderate', or 'complex'.

    Structural heuristics: complex verbs, question patterns, file paths, paste detection.
    """
    length = len(prompt)
    lower = prompt.lower()
    has_code_block = bool(_CODE_BLOCK_RE.search(prompt))
    tool_hits = sum(1 for kw in _TOOL_KEYWORDS if kw in lower)
    question_marks = prompt.count("?")
    complex_verb_hits = sum(1 for v in _COMPLEX_VERBS if v in lower)
    has_file_path = bool(_FILE_PATH_RE.search(prompt))
    is_question_only = bool(_QUESTION_RE.match(prompt.strip()))

    # detect paste-like content: if >60% of lines are indented, actual instruction is short
    lines = prompt.splitlines()
    indented_count = sum(1 for line in lines if _INDENTED_LINE_RE.match(line))
    paste_ratio = indented_count / max(len(lines), 1)

    # complex verbs strongly signal multi-step work regardless of length
    if complex_verb_hits >= 1 or has_code_block or tool_hits >= 3 or length > 2000:
        return "complex"
    # pure questions with no tool keywords are simple even if long
    if is_question_only and tool_hits == 0 and not has_file_path:
        return "simple"
    # paste-heavy prompts: the instruction itself is likely short
    if paste_ratio > 0.6 and tool_hits == 0:
        return "simple"
    if has_file_path or tool_hits >= 1 or length > 800 or question_marks >= 3:
        return "moderate"
    return "simple"


# ── Prompt distillation ───────────────────────────────────────────────

_MULTISPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_LINE_COMMENT_RE = re.compile(r"(?m)^\s*(?://|#)[^\n]*\n?")
# duplicate stack trace frames: Python "File ...", Node "at ...", Go "goroutine"
_PY_TRACE_RE = re.compile(r"((?:^\s+File\s+\"[^\n]+\n\s+\w[^\n]*\n){3,})", re.M)
_NODE_TRACE_RE = re.compile(r"((?:^\s+at\s+[^\n]+\n){4,})", re.M)
_FENCED_BLOCK_RE = re.compile(r"(```\w*\n)((?:[^\n]*\n){51,}?)(```)", re.M)


def _collapse_trace(match: re.Match) -> str:
    """Collapse repeated trace frames, keeping first+last."""
    lines = match.group(0).strip().splitlines(keepends=True)
    if len(lines) <= 4:
        return match.group(0)
    return "".join(lines[:2]) + f"  [... {len(lines)-4} similar frames ...]\n" + "".join(lines[-2:])


def _collapse_fenced(match: re.Match) -> str:
    """Collapse large fenced code blocks to first+last 10 lines."""
    opener, body, closer = match.group(1), match.group(2), match.group(3)
    lines = body.splitlines(keepends=True)
    if len(lines) <= 50:
        return match.group(0)
    head = "".join(lines[:10])
    tail = "".join(lines[-10:])
    return f"{opener}{head}[... {len(lines)-20} lines omitted, use read_file ...]\n{tail}{closer}"


def distill_prompt(prompt: str, context: str, config: EconomyConfig) -> Tuple[str, int]:
    """Distill prompt+context by stripping redundant whitespace, traces, and optionally comments.

    Returns (distilled_text, estimated_tokens_saved).
    """
    original_len = len(prompt) + len(context)
    text = f"{prompt}\n{context}" if context else prompt

    # collapse redundant whitespace
    text = _MULTISPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)

    # collapse duplicate stack trace frames
    text = _PY_TRACE_RE.sub(_collapse_trace, text)
    text = _NODE_TRACE_RE.sub(_collapse_trace, text)

    # collapse large fenced code blocks (frugal mode only)
    if config.strip_code_comments:
        text = _FENCED_BLOCK_RE.sub(_collapse_fenced, text)

    # optionally strip line comments from code context
    if config.strip_code_comments:
        text = _LINE_COMMENT_RE.sub("", text)

    text = text.strip()
    new_len = len(text)
    tokens_saved = max(0, (original_len - new_len) // 4) # rough char-to-token
    return text, tokens_saved


# ── Savings tracker ───────────────────────────────────────────────────

@dataclass
class EconomyTurnReport:
    """Per-turn economy optimization report — reset each turn."""
    distillation_tokens_saved: int = 0
    downshifted: bool = False
    downshift_model: str = ""
    cache_hit: bool = False
    dedup_tokens_saved: int = 0
    diff_only_applied: bool = False
    sequential_reads_detected: int = 0 # read_file calls across separate iterations (inefficient)


@dataclass
class EconomySavings:
    """Accumulated economy savings metrics."""
    tokens_saved_by_distillation: int = 0
    tokens_saved_by_downshift: int = 0
    tokens_saved_by_dedup: int = 0
    tokens_saved_by_terse: int = 0
    tokens_saved_by_truncation: int = 0
    tool_calls_avoided: int = 0
    cache_hits: int = 0
    estimated_money_saved_usd: float = 0.0


class EconomySavingsTracker:
    """Tracks economy savings across a session."""

    def __init__(self) -> None:
        self._savings = EconomySavings()

    def record_distillation(self, tokens_before: int, tokens_after: int) -> None:
        saved = max(0, tokens_before - tokens_after)
        self._savings.tokens_saved_by_distillation += saved

    def record_downshift(self, quality_cost: float, cheap_cost: float) -> None:
        saved_tokens = max(0, int((quality_cost - cheap_cost) * 1000 / max(quality_cost, 0.0001)))
        self._savings.tokens_saved_by_downshift += saved_tokens
        self._savings.estimated_money_saved_usd += max(0.0, quality_cost - cheap_cost)

    def record_dedup(self, tokens_avoided: int) -> None:
        self._savings.tokens_saved_by_dedup += tokens_avoided

    def record_terse(self, tokens_saved: int) -> None:
        self._savings.tokens_saved_by_terse += tokens_saved

    def record_truncation(self, tokens_saved: int) -> None:
        self._savings.tokens_saved_by_truncation += tokens_saved

    def record_cache_hit(self) -> None:
        self._savings.cache_hits += 1

    def record_tool_calls_avoided(self, count: int) -> None:
        self._savings.tool_calls_avoided += count

    def get_summary(self) -> Dict[str, Any]:
        return asdict(self._savings)

    def get_money_saved(self, cost_per_1k_in: float = 0.0005, cost_per_1k_out: float = 0.0015) -> float:
        """Estimate total money saved using average token pricing."""
        total_tokens_saved = (
            self._savings.tokens_saved_by_distillation
            + self._savings.tokens_saved_by_downshift
            + self._savings.tokens_saved_by_dedup
            + self._savings.tokens_saved_by_terse
            + self._savings.tokens_saved_by_truncation
        )
        avg_cost = (cost_per_1k_in + cost_per_1k_out) / 2
        return (total_tokens_saved / 1000) * avg_cost + self._savings.estimated_money_saved_usd
