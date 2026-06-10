"""MemGPT-style working memory with delta-based context updates.

Instead of re-sending full conversation history every turn, the agent
maintains a working memory snapshot and receives only diffs (deltas)
between turns. Hybrid mode uses full history for the first N turns,
then switches to deltas once context pressure builds.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

CHARS_PER_TOKEN = 4 # rough estimate
DEFAULT_HYBRID_TURN_THRESHOLD = 5
DEFAULT_HYBRID_PRESSURE_THRESHOLD = 0.50
DEFAULT_RESUMMARIZE_INTERVAL = 10 # turns between re-summarization
PERSIST_DIR_NAME = "working_memory"

_CONFUSION_PATTERNS = re.compile(
    r"(?:I don.t have (?:access|context|that file)|"
    r"what file are you referring to|"
    r"could you (?:share|provide|show) (?:the|that) (?:file|code|context)|"
    r"I.m not sure which (?:file|code|function)|"
    r"I don.t see (?:that|the) (?:file|code|context)|"
    r"I.m unable to (?:access|view|see)|"
    r"no (?:file|code|context) (?:was )?provided)",
    re.IGNORECASE,
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]


def _unified_diff(old: str, new: str, filepath: str = "") -> str:
    """Compute unified diff between two strings."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=filepath, tofile=filepath, n=3)
    return "".join(diff)


# ── data models ─────────────────────────────────────────────────────────


@dataclass
class WorkingMemory:
    """Snapshot of what the agent 'knows' at a given turn."""
    session_summary: str = "" # compressed summary of session so far
    active_files: Dict[str, str] = field(default_factory=dict) # path → content
    active_file_hashes: Dict[str, str] = field(default_factory=dict) # path → hash
    key_decisions: List[str] = field(default_factory=list)
    pending_tasks: List[str] = field(default_factory=list)
    tool_state: Dict[str, Any] = field(default_factory=dict) # recent tool call state
    last_turn_id: int = 0
    turn_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""
    total_tokens_saved: int = 0 # cumulative tokens saved by delta mode

    def estimate_tokens(self) -> int:
        """Estimate token footprint of full working memory."""
        total = _estimate_tokens(self.session_summary)
        for content in self.active_files.values():
            total += _estimate_tokens(content)
        for d in self.key_decisions:
            total += _estimate_tokens(d)
        for t in self.pending_tasks:
            total += _estimate_tokens(t)
        return total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_summary": self.session_summary,
            "active_files": {k: _content_hash(v) for k, v in self.active_files.items()}, # store hashes only for persistence size
            "active_file_hashes": dict(self.active_file_hashes),
            "key_decisions": list(self.key_decisions),
            "pending_tasks": list(self.pending_tasks),
            "tool_state": dict(self.tool_state),
            "last_turn_id": self.last_turn_id,
            "turn_count": self.turn_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_tokens_saved": self.total_tokens_saved,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkingMemory":
        return cls(
            session_summary=data.get("session_summary", ""),
            active_files={}, # files not persisted in full — reloaded lazily
            active_file_hashes=data.get("active_file_hashes", {}),
            key_decisions=data.get("key_decisions", []),
            pending_tasks=data.get("pending_tasks", []),
            tool_state=data.get("tool_state", {}),
            last_turn_id=data.get("last_turn_id", 0),
            turn_count=data.get("turn_count", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            total_tokens_saved=data.get("total_tokens_saved", 0),
        )


@dataclass
class ContextDelta:
    """What changed between two consecutive turns."""
    new_user_message: str = ""
    files_changed: Dict[str, str] = field(default_factory=dict) # path → unified diff
    files_added: Dict[str, str] = field(default_factory=dict) # path → content
    files_removed: List[str] = field(default_factory=list)
    new_tool_results: List[Dict[str, Any]] = field(default_factory=list)
    memory_updates: List[str] = field(default_factory=list) # textual memory updates

    def estimate_tokens(self) -> int:
        total = _estimate_tokens(self.new_user_message)
        for diff in self.files_changed.values():
            total += _estimate_tokens(diff)
        for content in self.files_added.values():
            total += _estimate_tokens(content)
        for r in self.new_tool_results:
            total += _estimate_tokens(str(r))
        for u in self.memory_updates:
            total += _estimate_tokens(u)
        return total

    def is_empty(self) -> bool:
        return (
            not self.new_user_message
            and not self.files_changed
            and not self.files_added
            and not self.files_removed
            and not self.new_tool_results
            and not self.memory_updates
        )


@dataclass
class DeltaModeMetrics:
    """Token usage comparison for delta vs full-history mode."""
    full_history_tokens: int = 0
    delta_tokens: int = 0
    working_memory_tokens: int = 0
    tokens_saved: int = 0
    savings_pct: float = 0.0
    mode: str = "full" # "full" | "delta" | "recovery"
    turn: int = 0


# ── delta computation ───────────────────────────────────────────────────


def compute_delta(
    prev_memory: WorkingMemory,
    current_files: Dict[str, str],
    new_user_message: str = "",
    new_tool_results: Optional[List[Dict[str, Any]]] = None,
) -> ContextDelta:
    """Compute what changed between prev working memory state and current state."""
    delta = ContextDelta(new_user_message=new_user_message)
    if new_tool_results:
        delta.new_tool_results = new_tool_results
    for path, content in current_files.items():
        cur_hash = _content_hash(content)
        if path not in prev_memory.active_files and path not in prev_memory.active_file_hashes:
            delta.files_added[path] = content
        elif path in prev_memory.active_files:
            old_content = prev_memory.active_files[path]
            if _content_hash(old_content) != cur_hash:
                diff = _unified_diff(old_content, content, filepath=path)
                if diff:
                    delta.files_changed[path] = diff
        elif prev_memory.active_file_hashes.get(path) != cur_hash:
            delta.files_added[path] = content # hash mismatch, treat as new (full content not available)
    for path in prev_memory.active_files:
        if path not in current_files:
            delta.files_removed.append(path)
    return delta


# ── prompt construction ─────────────────────────────────────────────────


def build_delta_prompt(memory: WorkingMemory, delta: ContextDelta) -> str:
    """Build a prompt from working memory summary + delta instead of full history."""
    parts: List[str] = []
    # working memory header
    parts.append("[Working Memory]")
    parts.append(f"You are mid-session (turn {memory.turn_count}).")
    if memory.session_summary:
        parts.append(f"Session context: {memory.session_summary}")
    if memory.key_decisions:
        parts.append("Key decisions:")
        for d in memory.key_decisions[-10:]: # cap at recent 10
            parts.append(f"  - {d}")
    if memory.pending_tasks:
        parts.append("Pending tasks:")
        for t in memory.pending_tasks[-5:]:
            parts.append(f"  - {t}")
    if memory.active_files:
        parts.append(f"Active files ({len(memory.active_files)}): {', '.join(sorted(memory.active_files.keys()))}")
    # delta section
    parts.append("")
    parts.append("[Since Last Turn]")
    if delta.new_user_message:
        parts.append(f"User: {delta.new_user_message}")
    if delta.files_added:
        parts.append(f"Files added ({len(delta.files_added)}):")
        for path, content in delta.files_added.items():
            parts.append(f"--- {path} ---")
            parts.append(content)
    if delta.files_changed:
        parts.append(f"Files changed ({len(delta.files_changed)}):")
        for path, diff in delta.files_changed.items():
            parts.append(f"--- {path} (diff) ---")
            parts.append(diff)
    if delta.files_removed:
        parts.append(f"Files removed: {', '.join(delta.files_removed)}")
    if delta.new_tool_results:
        parts.append(f"Tool results ({len(delta.new_tool_results)}):")
        for r in delta.new_tool_results:
            name = r.get("tool", r.get("name", "tool"))
            output = str(r.get("output", r.get("result", "")))
            if len(output) > 2000:
                output = output[:2000] + "\n... [truncated]"
            parts.append(f"[{name}] {output}")
    if delta.memory_updates:
        parts.append("Memory updates:")
        for u in delta.memory_updates:
            parts.append(f"  - {u}")
    return "\n".join(parts)


# ── confusion detection ─────────────────────────────────────────────────


def detect_confusion(response_text: str) -> bool:
    """Check if model response indicates lost context."""
    return bool(_CONFUSION_PATTERNS.search(response_text))


# ── working memory manager ──────────────────────────────────────────────


class WorkingMemoryManager:
    """Manages working memory lifecycle: creation, updates, persistence, hybrid switching."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        max_context_tokens: int = 100_000,
        hybrid_turn_threshold: int = DEFAULT_HYBRID_TURN_THRESHOLD,
        hybrid_pressure_threshold: float = DEFAULT_HYBRID_PRESSURE_THRESHOLD,
        resummarize_interval: int = DEFAULT_RESUMMARIZE_INTERVAL,
    ):
        self._repo_root = (repo_root or Path.cwd()).resolve()
        self._persist_dir = self._repo_root / ".poor-cli" / PERSIST_DIR_NAME
        self._max_context_tokens = max_context_tokens
        self._hybrid_turn_threshold = hybrid_turn_threshold
        self._hybrid_pressure_threshold = hybrid_pressure_threshold
        self._resummarize_interval = resummarize_interval
        self._memory: Optional[WorkingMemory] = None
        self._delta_mode_active: bool = False
        self._recovery_turn: bool = False # if True, next turn uses full history
        self._metrics_log: List[DeltaModeMetrics] = []
        self._summary_callback: Optional[Callable] = None # async callback for LLM summarization

    @property
    def memory(self) -> Optional[WorkingMemory]:
        return self._memory

    @property
    def is_delta_mode(self) -> bool:
        return self._delta_mode_active and not self._recovery_turn

    @property
    def metrics(self) -> List[DeltaModeMetrics]:
        return list(self._metrics_log)

    def set_summary_callback(self, callback: Callable) -> None:
        """Set async callback for LLM-powered re-summarization.
        Signature: async def callback(history_text: str, current_summary: str) -> str
        """
        self._summary_callback = callback

    # ── lifecycle ────────────────────────────────────────────────────────

    def init_session(self, session_id: str = "") -> WorkingMemory:
        """Start or resume a working memory session."""
        loaded = self._load_from_disk(session_id)
        if loaded:
            self._memory = loaded
            logger.info("resumed working memory (turn %d)", loaded.turn_count)
        else:
            self._memory = WorkingMemory()
            logger.info("initialized fresh working memory")
        self._delta_mode_active = False
        self._recovery_turn = False
        return self._memory

    def reset(self, new_summary: str = "") -> WorkingMemory:
        """Reset working memory (called by /compact)."""
        self._memory = WorkingMemory(session_summary=new_summary)
        self._delta_mode_active = False
        self._recovery_turn = False
        self._persist_to_disk()
        logger.info("working memory reset")
        return self._memory

    # ── per-turn flow ───────────────────────────────────────────────────

    def should_switch_to_delta(self, context_pressure: float) -> bool:
        """Check if we should switch from full-history to delta mode.
        Args:
            context_pressure: current context usage ratio (0.0-1.0)
        """
        if self._memory is None:
            return False
        if self._memory.turn_count >= self._hybrid_turn_threshold:
            return True
        if context_pressure >= self._hybrid_pressure_threshold:
            return True
        return False

    def pre_turn(
        self,
        user_message: str,
        current_files: Dict[str, str],
        context_pressure: float,
        full_history_tokens: int,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, DeltaModeMetrics]:
        """Called before sending a turn to the provider.
        Returns (prompt_content, metrics) — either full history marker or delta prompt.
        """
        if self._memory is None:
            self.init_session()
        mem = self._memory
        assert mem is not None
        mem.turn_count += 1
        mem.last_turn_id = mem.turn_count
        # check hybrid switch
        if not self._delta_mode_active:
            if self.should_switch_to_delta(context_pressure):
                self._delta_mode_active = True
                logger.info("switching to delta mode at turn %d (pressure=%.2f)", mem.turn_count, context_pressure)
        # recovery: use full history this turn, then resume delta
        if self._recovery_turn:
            self._recovery_turn = False
            metrics = DeltaModeMetrics(
                full_history_tokens=full_history_tokens,
                delta_tokens=full_history_tokens,
                working_memory_tokens=mem.estimate_tokens(),
                tokens_saved=0,
                savings_pct=0.0,
                mode="recovery",
                turn=mem.turn_count,
            )
            self._metrics_log.append(metrics)
            self._update_files(current_files)
            return "", metrics # empty string signals "use full history"
        if not self._delta_mode_active:
            metrics = DeltaModeMetrics(
                full_history_tokens=full_history_tokens,
                delta_tokens=full_history_tokens,
                working_memory_tokens=mem.estimate_tokens(),
                tokens_saved=0,
                savings_pct=0.0,
                mode="full",
                turn=mem.turn_count,
            )
            self._metrics_log.append(metrics)
            self._update_files(current_files)
            return "", metrics # use full history
        # delta mode
        delta = compute_delta(mem, current_files, user_message, tool_results)
        prompt = build_delta_prompt(mem, delta)
        delta_tokens = _estimate_tokens(prompt) + mem.estimate_tokens()
        saved = max(0, full_history_tokens - delta_tokens)
        pct = (saved / full_history_tokens * 100) if full_history_tokens > 0 else 0.0
        mem.total_tokens_saved += saved
        metrics = DeltaModeMetrics(
            full_history_tokens=full_history_tokens,
            delta_tokens=delta_tokens,
            working_memory_tokens=mem.estimate_tokens(),
            tokens_saved=saved,
            savings_pct=pct,
            mode="delta",
            turn=mem.turn_count,
        )
        self._metrics_log.append(metrics)
        self._update_files(current_files)
        return prompt, metrics

    def post_turn(self, assistant_response: str, history_text: str = "") -> None:
        """Called after receiving the assistant response.
        Updates working memory, checks for confusion, triggers re-summarization.
        """
        if self._memory is None:
            return
        # confusion detection
        if self._delta_mode_active and detect_confusion(assistant_response):
            self._recovery_turn = True
            logger.warning("confusion detected at turn %d — will recover with full history next turn", self._memory.turn_count)
        # extract decisions from response
        self._extract_decisions(assistant_response)
        # periodic re-summarization
        if (
            self._memory.turn_count > 0
            and self._memory.turn_count % self._resummarize_interval == 0
            and history_text
        ):
            self._trigger_resummarize(history_text)
        # persist
        self._memory.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist_to_disk()

    # ── internal helpers ────────────────────────────────────────────────

    def _update_files(self, current_files: Dict[str, str]) -> None:
        """Update active files in working memory."""
        if self._memory is None:
            return
        self._memory.active_files = dict(current_files)
        self._memory.active_file_hashes = {p: _content_hash(c) for p, c in current_files.items()}

    def _extract_decisions(self, response: str) -> None:
        """Extract key decisions from assistant response (heuristic)."""
        if self._memory is None:
            return
        decision_re = re.compile(
            r"\b(decided|choosing|switched to|using|created|deleted|renamed|refactored|fixed|implemented)\b\s+(.{10,80})",
            re.IGNORECASE,
        )
        for match in decision_re.finditer(response):
            decision = match.group(0).strip()
            if decision not in self._memory.key_decisions:
                self._memory.key_decisions.append(decision)
        # cap decisions list
        if len(self._memory.key_decisions) > 30:
            self._memory.key_decisions = self._memory.key_decisions[-20:]

    def _trigger_resummarize(self, history_text: str) -> None:
        """Trigger re-summarization of session (sync path — async handled externally)."""
        if self._memory is None:
            return
        # basic extractive summary as fallback (LLM summary set via callback externally)
        lines = history_text.splitlines()
        user_lines = [line for line in lines if line.strip().startswith("User:") or line.strip().startswith("user:")]
        if user_lines:
            topics = "; ".join(line.strip()[:80] for line in user_lines[-5:])
            self._memory.session_summary = f"Recent topics: {topics}"
        logger.info("re-summarized working memory at turn %d", self._memory.turn_count)

    async def resummarize_with_llm(self, history_text: str) -> str:
        """Re-summarize using LLM callback if available."""
        if self._memory is None or not self._summary_callback:
            return self._memory.session_summary if self._memory else ""
        try:
            new_summary = await self._summary_callback(history_text, self._memory.session_summary)
            if new_summary and new_summary.strip():
                self._memory.session_summary = new_summary.strip()
                self._persist_to_disk()
                return self._memory.session_summary
        except Exception as e:
            logger.warning("LLM re-summarization failed: %s", e)
        return self._memory.session_summary if self._memory else ""

    # ── persistence ─────────────────────────────────────────────────────

    def _persist_to_disk(self, session_id: str = "current") -> None:
        """Save working memory state to disk."""
        if self._memory is None:
            return
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            path = self._persist_dir / f"wm-{session_id}.json"
            data = self._memory.to_dict()
            data["_persisted_at"] = datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("failed to persist working memory: %s", e)

    def _load_from_disk(self, session_id: str = "current") -> Optional[WorkingMemory]:
        """Load working memory state from disk."""
        path = self._persist_dir / f"wm-{session_id}.json"
        if not path.is_file():
            path = self._persist_dir / "wm-current.json" # fallback
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkingMemory.from_dict(data)
        except Exception as e:
            logger.warning("failed to load working memory: %s", e)
            return None

    # ── measurement ─────────────────────────────────────────────────────

    def get_savings_report(self) -> Dict[str, Any]:
        """Return token savings report for current session."""
        if not self._metrics_log:
            return {
                "turns": 0, "delta_turns": 0, "full_turns": 0,
                "recovery_turns": 0, "total_tokens_saved": 0,
                "avg_savings_pct": 0.0, "cumulative_saved": 0,
            }
        delta_metrics = [m for m in self._metrics_log if m.mode == "delta"]
        total_saved = sum(m.tokens_saved for m in delta_metrics)
        avg_pct = sum(m.savings_pct for m in delta_metrics) / len(delta_metrics) if delta_metrics else 0.0
        return {
            "turns": len(self._metrics_log),
            "delta_turns": len(delta_metrics),
            "full_turns": sum(1 for m in self._metrics_log if m.mode == "full"),
            "recovery_turns": sum(1 for m in self._metrics_log if m.mode == "recovery"),
            "total_tokens_saved": total_saved,
            "avg_savings_pct": round(avg_pct, 1),
            "cumulative_saved": self._memory.total_tokens_saved if self._memory else 0,
        }
