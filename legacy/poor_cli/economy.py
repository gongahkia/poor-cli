"""Economy mode: proactive cost reduction for poor-cli."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Tuple

from .persisted import run_sqlite_migrations


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

OUTPUT_VERBOSITY_BY_PRESET = {
    "frugal": "caveman",
    "balanced": "normal",
    "quality": "comprehensive",
}

SAVINGS_SOURCE_ORDER = (
    "prompt_caching",
    "semantic_cache",
    "compaction",
    "rtk",
    "model_downshift",
    "safe_pretokenization",
)

SAVINGS_METHODOLOGY = {
    "prompt_caching": "provider cache-read tokens, falling back to block-cache hit tokens",
    "semantic_cache": "cached response tokens recorded by semantic cache",
    "compaction": "distillation, dedup, truncation, terse, and failure-amnesia token deltas",
    "rtk": "RTK-lite shell filter before/after token delta",
    "model_downshift": "price delta between original and cheaper selected model",
    "safe_pretokenization": "pre/post tokenizer estimate for context code files",
}

_DEFAULT_SAVINGS_COST_PER_1K = 0.001


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _estimate_usd(tokens: int, estimator: Callable[[int], float] | None = None) -> float:
    if tokens <= 0:
        return 0.0
    if estimator is not None:
        try:
            return max(0.0, float(estimator(tokens)))
        except Exception:
            pass
    return (tokens / 1000) * _DEFAULT_SAVINGS_COST_PER_1K


def _source_entry(
    source: str,
    tokens: int,
    usd: float,
    *,
    methodology: str | None = None,
) -> Dict[str, Any]:
    return {
        "source": source,
        "tokens_saved": _as_int(tokens),
        "usd_saved": round(_as_float(usd), 6),
        "methodology": methodology or SAVINGS_METHODOLOGY.get(source, "estimated token delta"),
    }


def block_cache_tokens_saved(block_cache_stats: Dict[str, Any]) -> int:
    total = 0
    for item in block_cache_stats.get("by_block", []) or []:
        if isinstance(item, dict):
            total += _as_int(item.get("hits")) * _as_int(item.get("tokens"))
    return total


def build_savings_summary(
    economy_summary: Dict[str, Any] | None = None,
    session_summary: Dict[str, Any] | None = None,
    *,
    semantic_cache_stats: Dict[str, Any] | None = None,
    block_cache_stats: Dict[str, Any] | None = None,
    token_usd_estimator: Callable[[int], float] | None = None,
    source_order: Iterable[str] = SAVINGS_SOURCE_ORDER,
) -> Dict[str, Any]:
    economy = dict(economy_summary or {})
    session = dict(session_summary or {})
    semantic = dict(semantic_cache_stats or economy.get("semantic_cache") or {})
    block = dict(block_cache_stats or session.get("block_cache") or economy.get("block_cache") or {})

    provider_cache_tokens = _as_int(session.get("cache_read_input_tokens") or session.get("cacheReadInputTokens"))
    block_tokens = block_cache_tokens_saved(block)
    prompt_tokens = max(provider_cache_tokens, block_tokens)
    prompt_usd = _as_float(session.get("estimated_cache_savings_usd") or session.get("estimatedCacheSavingsUSD"))
    if prompt_usd <= 0:
        prompt_usd = _estimate_usd(prompt_tokens, token_usd_estimator)

    semantic_tokens = _as_int(semantic.get("estimated_tokens_saved"))
    semantic_usd = _as_float(semantic.get("estimated_cost_saved_usd"))
    if semantic_usd <= 0:
        semantic_usd = _estimate_usd(semantic_tokens, token_usd_estimator)

    compaction_tokens = sum(
        _as_int(economy.get(key))
        for key in (
            "tokens_saved_by_distillation",
            "tokens_saved_by_dedup",
            "tokens_saved_by_terse",
            "tokens_saved_by_truncation",
            "tokens_saved_by_failure_amnesia",
        )
    )

    rtk_tokens = _as_int(economy.get("tokens_saved_by_shell_filter"))
    downshift_tokens = _as_int(economy.get("tokens_saved_by_downshift"))
    pretok_tokens = _as_int(economy.get("tokens_saved_by_safe_pretokenization"))
    downshift_usd = _as_float(economy.get("estimated_money_saved_usd"))

    raw = {
        "prompt_caching": _source_entry("prompt_caching", prompt_tokens, prompt_usd),
        "semantic_cache": _source_entry("semantic_cache", semantic_tokens, semantic_usd),
        "compaction": _source_entry("compaction", compaction_tokens, _estimate_usd(compaction_tokens, token_usd_estimator)),
        "rtk": _source_entry("rtk", rtk_tokens, _estimate_usd(rtk_tokens, token_usd_estimator)),
        "model_downshift": _source_entry(
            "model_downshift",
            downshift_tokens,
            downshift_usd if downshift_usd > 0 else _estimate_usd(downshift_tokens, token_usd_estimator),
        ),
        "safe_pretokenization": _source_entry(
            "safe_pretokenization",
            pretok_tokens,
            _estimate_usd(pretok_tokens, token_usd_estimator),
        ),
    }
    by_source = [raw[source] for source in source_order if source in raw]
    total_tokens = sum(item["tokens_saved"] for item in by_source)
    total_usd = round(sum(item["usd_saved"] for item in by_source), 6)
    tokens_after = _as_int(session.get("total_tokens") or session.get("totalTokens"))
    return {
        "by_source": by_source,
        "all_sources": by_source,
        "source_order": list(source_order),
        "tokens_saved": total_tokens,
        "usd_saved": total_usd,
        "session_delta": {
            "tokens_before": tokens_after + total_tokens,
            "tokens_after": tokens_after,
            "tokens_saved": total_tokens,
            "usd_saved": total_usd,
        },
        "methodology": {source: SAVINGS_METHODOLOGY[source] for source in SAVINGS_SOURCE_ORDER},
    }


class SavingsHistoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path.home() / ".poor-cli" / "savings_history.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS savings_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tokens_saved INTEGER NOT NULL DEFAULT 0,
                    usd_saved REAL NOT NULL DEFAULT 0,
                    methodology TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_savings_history_timestamp ON savings_history(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_savings_history_source ON savings_history(source)")
            run_sqlite_migrations(conn, "savings")

    def record_snapshot(self, snapshot: Dict[str, Any], *, timestamp: str | None = None) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        rows = []
        for item in snapshot.get("all_sources") or snapshot.get("by_source") or []:
            if not isinstance(item, dict):
                continue
            tokens = _as_int(item.get("tokens_saved"))
            usd = _as_float(item.get("usd_saved"))
            if tokens <= 0 and usd <= 0:
                continue
            rows.append((
                ts,
                str(item.get("source") or ""),
                tokens,
                usd,
                str(item.get("methodology") or ""),
            ))
        if not rows:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO savings_history
                (timestamp, source, tokens_saved, usd_saved, methodology)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

    def history(self, *, days: int = 30) -> Dict[str, Any]:
        days = max(1, int(days or 30))
        start = datetime.now(timezone.utc) - timedelta(days=days - 1)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, source, tokens_saved, usd_saved
                FROM savings_history
                WHERE timestamp >= ?
                ORDER BY timestamp ASC, id ASC
                """,
                (start.isoformat(),),
            ).fetchall()
        return rollup_savings_rows(rows, days=days)


def rollup_savings_rows(rows: Iterable[Tuple[Any, Any, Any, Any]], *, days: int = 30) -> Dict[str, Any]:
    daily: Dict[str, float] = {}
    weekly: Dict[str, Dict[str, float]] = {}
    by_day_source: Dict[str, Dict[str, float]] = {}
    for timestamp, source, _tokens, usd in rows:
        ts = str(timestamp or "")
        day = ts[:10]
        if len(day) != 10:
            continue
        source_name = str(source or "unknown")
        amount = _as_float(usd)
        daily[day] = round(daily.get(day, 0.0) + amount, 6)
        by_day_source.setdefault(day, {})
        by_day_source[day][source_name] = round(by_day_source[day].get(source_name, 0.0) + amount, 6)
        try:
            week = datetime.fromisoformat(day).date().isocalendar()
            week_key = f"{week.year}-W{week.week:02d}"
        except ValueError:
            week_key = day
        weekly.setdefault(week_key, {})
        weekly[week_key][source_name] = round(weekly[week_key].get(source_name, 0.0) + amount, 6)
    ordered_days = sorted(daily.keys())[-max(1, int(days or 30)):]
    top_weeks = []
    for week_key in sorted(weekly.keys())[-6:]:
        top = [
            {"source": source, "usd_saved": usd}
            for source, usd in sorted(weekly[week_key].items(), key=lambda item: item[1], reverse=True)[:3]
        ]
        top_weeks.append({"week": week_key, "top": top})
    return {
        "daily": {day: daily[day] for day in ordered_days},
        "by_day_source": {day: by_day_source.get(day, {}) for day in ordered_days},
        "top_contributors_by_week": top_weeks,
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


def resolve_output_verbosity(config: EconomyConfig) -> str:
    """Map economy state to output verbosity."""
    if getattr(config, "terse_system_prompt", False):
        return "caveman"
    return OUTPUT_VERBOSITY_BY_PRESET.get(getattr(config, "preset", ""), "normal")


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
_FENCED_LANG_BLOCK_RE = re.compile(r"(```(\w*)\n)(.*?)(```)", re.S) # captures lang + body
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


_LANG_TO_EXT = {"python": ".py", "py": ".py", "lua": ".lua", "typescript": ".ts", "ts": ".ts", "javascript": ".js", "js": ".js", "tsx": ".tsx", "jsx": ".js"}

def _strip_fenced_block(match: re.Match) -> str:
    """Apply language-aware comment stripping + indentation collapse to a fenced code block."""
    from .code_tokenizer import strip_comments_python, strip_comments_lua, strip_comments_ts, collapse_indentation, collapse_blank_lines
    opener, lang, body, closer = match.group(1), match.group(2), match.group(3), match.group(4)
    ext = _LANG_TO_EXT.get(lang.lower(), "") if lang else ""
    if ext == ".py":
        body = strip_comments_python(body)
    elif ext == ".lua":
        body = strip_comments_lua(body)
    elif ext in (".ts", ".js", ".tsx"):
        body = strip_comments_ts(body)
    else:
        return match.group(0) # unknown lang, leave as-is
    body = collapse_indentation(body)
    body = collapse_blank_lines(body)
    return f"{opener}{body}{closer}"

def _strip_code_comments_lang_aware(text: str) -> str:
    """Strip comments from fenced code blocks using language-aware tokenizer."""
    return _FENCED_LANG_BLOCK_RE.sub(_strip_fenced_block, text)

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

    # language-aware comment stripping via code_tokenizer for fenced blocks
    if config.strip_code_comments:
        text = _strip_code_comments_lang_aware(text)

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
    routed: bool = False
    routed_model: str = ""
    routed_complexity: str = ""


@dataclass
class EconomySavings:
    """Accumulated economy savings metrics."""
    tokens_saved_by_distillation: int = 0
    tokens_saved_by_downshift: int = 0
    tokens_saved_by_dedup: int = 0
    tokens_saved_by_terse: int = 0
    tokens_saved_by_truncation: int = 0
    tokens_saved_by_failure_amnesia: int = 0
    tokens_saved_by_safe_pretokenization: int = 0
    tokens_saved_by_shell_filter: int = 0
    safe_pretokenization_files: int = 0
    safe_pretokenization_original_tokens: int = 0
    safe_pretokenization_compressed_tokens: int = 0
    safe_pretokenization_by_file: Dict[str, int] = field(default_factory=dict)
    tool_calls_avoided: int = 0
    cache_hits: int = 0
    estimated_money_saved_usd: float = 0.0
    routing_decisions: int = 0
    routing_escalations: int = 0


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

    def record_failure_amnesia(self, tokens_saved: int) -> None:
        self._savings.tokens_saved_by_failure_amnesia += tokens_saved

    def record_safe_pretokenization(self, path: str, original_tokens: int, compressed_tokens: int) -> None:
        saved = max(0, int(original_tokens) - int(compressed_tokens))
        if saved <= 0:
            return
        self._savings.tokens_saved_by_safe_pretokenization += saved
        self._savings.safe_pretokenization_files += 1
        self._savings.safe_pretokenization_original_tokens += max(0, int(original_tokens))
        self._savings.safe_pretokenization_compressed_tokens += max(0, int(compressed_tokens))
        key = str(path or "<unknown>")
        current = self._savings.safe_pretokenization_by_file.get(key, 0)
        self._savings.safe_pretokenization_by_file[key] = current + saved

    def record_shell_filter(self, tokens_saved: int) -> None:
        self._savings.tokens_saved_by_shell_filter += max(0, int(tokens_saved))

    def record_cache_hit(self) -> None:
        self._savings.cache_hits += 1

    def record_tool_calls_avoided(self, count: int) -> None:
        self._savings.tool_calls_avoided += count

    def record_routing_decision(self, escalated: bool = False) -> None:
        self._savings.routing_decisions += 1
        if escalated:
            self._savings.routing_escalations += 1

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
            + self._savings.tokens_saved_by_failure_amnesia
            + self._savings.tokens_saved_by_safe_pretokenization
            + self._savings.tokens_saved_by_shell_filter
        )
        avg_cost = (cost_per_1k_in + cost_per_1k_out) / 2
        return (total_tokens_saved / 1000) * avg_cost + self._savings.estimated_money_saved_usd
