"""importance-weighted history pruning for chat transcripts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .token_counter import get_token_counter
from .policy_hooks import emit_policy_hook_nowait

_FILE_RE = re.compile(r"(?:^|[\s`'\"])((?:[\w.\-]+/)*[\w.\-]+\.[A-Za-z0-9_]+)")
_DECISION_RE = re.compile(
    r"\b(decided|chosen|approved|rejected|confirmed|implemented|refactored|fixed|switched|kept|dropped)\b",
    re.IGNORECASE,
)
_PLAN_RE = re.compile(
    r"\b(plan|planned|next step|next steps|i will|we will|going to|approach|strategy)\b",
    re.IGNORECASE,
)
_FAILURE_RE = re.compile(
    r"\b(error|exception|traceback|failed|failure|permission denied|not found|timed out|timeout)\b",
    re.IGNORECASE,
)
_CORRECTION_RE = re.compile(
    r"\b(actually|instead|correction|ignore (?:that|previous)|i meant|use .+ instead)\b",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class PruningPolicy:
    mode: str = "balanced"
    economy_preset: str = "balanced"
    score_threshold: float = 0.45
    # soft-pinned turns are pruned only when current_tokens > target * factor.
    # Default 1.05: start evicting soft-pins once we exceed budget by >5%.
    soft_pin_evict_factor: float = 1.05
    # CB3 adaptive tool weighting — when True, the pruner multiplies a tool
    # turn's contribution by ToolSuccessTracker.tool_weight_multiplier(name).
    # Default off so legacy behavior is preserved.
    adaptive_tool_scoring: bool = False


# sentinel strings accepted by MessagePolicy.pinned / metadata.pinned
PIN_HARD = "hard"
PIN_SOFT = "soft"


def _apply_turn_pin_overlay(
    history: List[Dict[str, Any]],
    overlay: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return a copy of history with overlay pin states merged into
    ``metadata.pinned`` for messages whose ``metadata.turn_id`` appears in
    the overlay. Invalid overlay values are ignored.
    """
    if not overlay:
        return history
    result: List[Dict[str, Any]] = []
    for message in history:
        meta = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        turn_id = str(meta.get("turn_id") or meta.get("turnId") or "")
        state = overlay.get(turn_id)
        if turn_id and state in (PIN_SOFT, PIN_HARD):
            new_meta = dict(meta)
            new_meta["pinned"] = state
            new_msg = dict(message)
            new_msg["metadata"] = new_meta
            result.append(new_msg)
        else:
            result.append(message)
    return result


@dataclass(frozen=True)
class ScoredTurn:
    index: int
    message: Dict[str, Any]
    score: float
    token_count: int
    protected: bool
    superseded: bool
    primary_reason: str
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    file_refs: Tuple[str, ...] = field(default_factory=tuple)
    components: Dict[str, float] = field(default_factory=dict)
    soft_protected: bool = False  # pruned only under severe budget pressure

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "protected": self.protected,
            "softProtected": self.soft_protected,
            "superseded": self.superseded,
            "primaryReason": self.primary_reason,
            "reasonCodes": list(self.reason_codes),
            "fileRefs": list(self.file_refs),
            "components": {key: round(value, 4) for key, value in self.components.items()},
        }


@dataclass(frozen=True)
class PrunedTurnRecord:
    index: int
    message: Dict[str, Any]
    score: float
    token_count: int
    primary_reason: str
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "role": str(self.message.get("role", "")),
            "name": str(self.message.get("name") or self.message.get("tool_name") or "").strip(),
            "content": self._extract_text(self.message),
            "message": self.message,
            "score": round(self.score, 4),
            "tokenCount": self.token_count,
            "primaryReason": self.primary_reason,
            "reasonCodes": list(self.reason_codes),
            "components": {key: round(value, 4) for key, value in self.components.items()},
        }

    @staticmethod
    def _extract_text(message: Dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
            content = "\n".join(part for part in parts if part)
        if not content and isinstance(message.get("parts"), list):
            parts = []
            for item in message["parts"]:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
            content = "\n".join(part for part in parts if part)
        return str(content or "").strip()


@dataclass(frozen=True)
class PruningResult:
    history: List[Dict[str, Any]]
    scored_turns: List[ScoredTurn]
    pruned_turns: List[PrunedTurnRecord]
    tokens_before: int
    tokens_after: int
    target_tokens: int
    notification: str
    reason_counts: Dict[str, int]


class HistoryPruner:
    """score conversation turns and selectively prune low-value turns."""

    def __init__(self, tool_success_tracker=None, adaptive_tool_scoring_override=None):
        """Optional tool_success_tracker enables CB3 adaptive scoring.

        When provided AND ``policy.adaptive_tool_scoring`` is True, each tool
        turn's score is multiplied by ``tracker.tool_weight_multiplier(name)``,
        which maps a rolling per-tool success rate into [0.5, 1.5].

        ``adaptive_tool_scoring_override``: force the policy flag regardless of
        tracker presence. ``None`` = auto (flag follows tracker presence);
        ``True`` = always on (requires tracker to have effect); ``False`` = off.
        """
        self._tool_tracker = tool_success_tracker
        self._adaptive_override = adaptive_tool_scoring_override

    def policy_for(self, *, mode: str = "balanced", economy_preset: str = "balanced") -> PruningPolicy:
        normalized_mode = str(mode or "balanced").strip().lower() or "balanced"
        if normalized_mode not in {"gentle", "balanced", "aggressive"}:
            normalized_mode = "balanced"
        score_threshold = {"gentle": 0.25, "balanced": 0.45, "aggressive": 0.65}[normalized_mode]
        preset = str(economy_preset or "balanced").strip().lower() or "balanced"
        if preset == "frugal":
            score_threshold += 0.1
        elif preset == "quality":
            score_threshold -= 0.1
        if self._adaptive_override is None:
            adaptive = self._tool_tracker is not None
        else:
            adaptive = bool(self._adaptive_override)
        return PruningPolicy(
            mode=normalized_mode,
            economy_preset=preset,
            score_threshold=max(-1.0, min(1.5, score_threshold)),
            adaptive_tool_scoring=adaptive,
        )

    def prune(
        self,
        history: List[Dict[str, Any]],
        *,
        target_tokens: int = 0,
        mode: str = "balanced",
        economy_preset: str = "balanced",
        trigger: str = "manual",
        active_files: Optional[Sequence[str]] = None,
        turn_pin_overlay: Optional[Dict[str, str]] = None,
    ) -> PruningResult:
        if turn_pin_overlay:
            history = _apply_turn_pin_overlay(history, turn_pin_overlay)
        hook_manager = getattr(self, "_hook_manager", None)
        rows_before = len(history)
        emit_policy_hook_nowait(
            hook_manager,
            "pre_prune",
            {"rowsBefore": rows_before},
        )
        policy = self.policy_for(mode=mode, economy_preset=economy_preset)
        scored_turns = self.score_history(history, policy=policy, active_files=active_files)
        current_tokens = self._history_tokens(history)
        keep = [True] * len(history)
        pruned_turns: List[PrunedTurnRecord] = []
        # soft-pinned turns enter the candidate pool only when we exceed budget
        # by the configured factor (default 5%). Hard-pinned turns stay fully out.
        severe_pressure = (
            target_tokens > 0
            and current_tokens > target_tokens * policy.soft_pin_evict_factor
        )
        ordered = sorted(
            (
                turn for turn in scored_turns
                if not turn.protected and (severe_pressure or not turn.soft_protected)
            ),
            key=lambda turn: (turn.score, turn.index),
        )
        for turn in ordered:
            must_prune = turn.superseded or turn.score <= 0
            budget_pressure = target_tokens > 0 and current_tokens > target_tokens
            budget_prune = budget_pressure and turn.score <= policy.score_threshold
            if not must_prune and not budget_prune:
                if not budget_pressure:
                    continue
                break
            if not keep[turn.index]:
                continue
            keep[turn.index] = False
            current_tokens = max(0, current_tokens - turn.token_count)
            pruned_turns.append(
                PrunedTurnRecord(
                    index=turn.index,
                    message=turn.message,
                    score=turn.score,
                    token_count=turn.token_count,
                    primary_reason=turn.primary_reason,
                    reason_codes=turn.reason_codes,
                    components=turn.components,
                )
            )
        retained_history = [self._annotate_message(history[index], turn) for index, turn in enumerate(scored_turns) if keep[index]]
        reason_counts = self._count_reasons(pruned_turns)
        result = PruningResult(
            history=retained_history,
            scored_turns=scored_turns,
            pruned_turns=pruned_turns,
            tokens_before=self._history_tokens(history),
            tokens_after=self._history_tokens(retained_history),
            target_tokens=max(0, int(target_tokens or 0)),
            notification=self._build_notification(pruned_turns, reason_counts, trigger),
            reason_counts=reason_counts,
        )
        emit_policy_hook_nowait(
            hook_manager,
            "post_prune",
            {
                "rowsBefore": rows_before,
                "rowsAfter": len(retained_history),
                "removed": len(pruned_turns),
            },
        )
        return result

    def score_history(
        self,
        history: List[Dict[str, Any]],
        *,
        policy: Optional[PruningPolicy] = None,
        active_files: Optional[Sequence[str]] = None,
    ) -> List[ScoredTurn]:
        policy = policy or self.policy_for()
        protected_indexes, soft_protected_indexes = self._protected_indexes(history)
        resolved_active_files = self._active_files(history, active_files)
        file_refs_by_index = {
            index: tuple(self._extract_files(message, self._extract_text(message)))
            for index, message in enumerate(history)
        }
        superseded = self._detect_superseded(history, file_refs_by_index)
        scored: List[ScoredTurn] = []
        for index, message in enumerate(history):
            text = self._extract_text(message)
            role = self._normalized_role(message)
            file_refs = file_refs_by_index[index]
            recency = 0.42 / (1.0 + max(0, len(history) - index - 1) / 3.0)
            tool_weight = self._tool_score(message, text, policy=policy)
            file_weight = 0.35 if resolved_active_files.intersection(file_refs) else 0.0
            role_weight = {
                "user": 0.32,
                "assistant": 0.1,
                "model": 0.1,
                "tool": -0.08,
                "function": -0.08,
                "system": -0.25,
            }.get(role, 0.0)
            decision_weight = 0.35 if _DECISION_RE.search(text) else 0.0
            plan_weight = 0.18 if _PLAN_RE.search(text) else 0.0
            superseded_penalty = -0.7 if index in superseded else 0.0
            score = recency + tool_weight + file_weight + role_weight + decision_weight + plan_weight + superseded_penalty
            protected = index in protected_indexes
            soft_protected = index in soft_protected_indexes and not protected
            primary_reason = self._primary_reason(
                message=message,
                score=score,
                protected=protected,
                file_weight=file_weight,
                tool_weight=tool_weight,
                decision_weight=decision_weight,
                plan_weight=plan_weight,
                superseded_reasons=superseded.get(index, ()),
            )
            scored.append(
                ScoredTurn(
                    index=index,
                    message=self._annotate_message(
                        message,
                        metadata={
                            "score": round(score, 4),
                            "protected": protected,
                            "softProtected": soft_protected,
                            "superseded": bool(index in superseded),
                            "primaryReason": primary_reason,
                            "reasonCodes": list(superseded.get(index, ())),
                            "fileRefs": list(file_refs),
                            "components": {
                                "recency": recency,
                                "tool": tool_weight,
                                "fileRelevance": file_weight,
                                "role": role_weight,
                                "decision": decision_weight,
                                "plan": plan_weight,
                                "supersededPenalty": superseded_penalty,
                            },
                        },
                    ),
                    score=score,
                    token_count=(get_token_counter().count(text).count if text else 0),
                    protected=protected,
                    superseded=index in superseded,
                    primary_reason=primary_reason,
                    reason_codes=tuple(superseded.get(index, ())),
                    file_refs=file_refs,
                    components={
                        "recency": recency,
                        "tool": tool_weight,
                        "fileRelevance": file_weight,
                        "role": role_weight,
                        "decision": decision_weight,
                        "plan": plan_weight,
                        "supersededPenalty": superseded_penalty,
                    },
                    soft_protected=soft_protected,
                )
            )
        return scored

    def _protected_indexes(self, history: List[Dict[str, Any]]) -> Tuple[set[int], set[int]]:
        """Return (hard_protected, soft_protected) index sets.

        Hard-pinned turns (``pinned: true`` or ``"hard"``) are never pruned.
        Soft-pinned turns (``pinned: "soft"``) are pruned only when
        ``current_tokens > target_tokens * soft_pin_evict_factor``. The current
        turn tail, last user message, and active/pinned-context sources are
        always hard-protected regardless of ``pinned`` metadata.
        """
        hard: set[int] = set()
        soft: set[int] = set()
        if history:
            hard.add(len(history) - 1)  # current turn tail
        for index in range(len(history) - 1, -1, -1):
            if self._normalized_role(history[index]) == "user":
                hard.add(index)  # last user
                break
        for index, message in enumerate(history):
            metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
            pin_raw = message.get("pinned", metadata.get("pinned"))
            if isinstance(pin_raw, str) and pin_raw.strip().lower() == PIN_SOFT:
                soft.add(index)
                continue
            if pin_raw:  # truthy, non-"soft" value = hard pin (legacy pinned=true)
                hard.add(index)
                continue
            if metadata.get("contextSource") in {"active_file", "pinned_context"}:
                hard.add(index)
        return hard, soft

    def _active_files(self, history: List[Dict[str, Any]], active_files: Optional[Sequence[str]]) -> set[str]:
        files = {str(path).strip() for path in (active_files or []) if str(path).strip()}
        for index in range(len(history) - 1, -1, -1):
            message = history[index]
            role = self._normalized_role(message)
            metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
            if role == "user":
                files.update(self._extract_files(message, self._extract_text(message)))
                break
            if metadata.get("contextSource") in {"active_file", "pinned_context"}:
                files.update(self._extract_files(message, self._extract_text(message)))
        return files

    def _detect_superseded(
        self,
        history: List[Dict[str, Any]],
        file_refs_by_index: Dict[int, Tuple[str, ...]],
    ) -> Dict[int, Tuple[str, ...]]:
        superseded: Dict[int, set[str]] = {}

        def mark(index: int, reason: str) -> None:
            superseded.setdefault(index, set()).add(reason)

        success_tool_keys: set[Tuple[str, Tuple[str, ...]]] = set()
        success_tool_names: set[str] = set()
        for index in range(len(history) - 1, -1, -1):
            message = history[index]
            role = self._normalized_role(message)
            if role not in {"tool", "function"}:
                continue
            name = self._tool_name(message)
            files = file_refs_by_index.get(index, ())
            key = (name, files)
            if self._tool_succeeded(message, self._extract_text(message)):
                success_tool_keys.add(key)
                success_tool_names.add(name)
                continue
            if key in success_tool_keys or name in success_tool_names:
                mark(index, "failed_retry_succeeded")

        latest_read_by_file: Dict[str, int] = {}
        for index in range(len(history) - 1, -1, -1):
            message = history[index]
            role = self._normalized_role(message)
            if role not in {"tool", "function"}:
                continue
            if not self._looks_like_read(message):
                continue
            for file_ref in file_refs_by_index.get(index, ()):
                if file_ref in latest_read_by_file:
                    mark(index, "stale_file_read")
                else:
                    latest_read_by_file[file_ref] = index

        previous_user = -1
        for index, message in enumerate(history):
            if self._normalized_role(message) != "user":
                continue
            text = self._extract_text(message)
            if _CORRECTION_RE.search(text) and previous_user >= 0:
                mark(previous_user, "corrected_by_user")
            previous_user = index

        return {index: tuple(sorted(reasons)) for index, reasons in superseded.items()}

    def _tool_score(self, message: Dict[str, Any], text: str, *, policy: Optional["PruningPolicy"] = None) -> float:
        role = self._normalized_role(message)
        if role not in {"tool", "function"}:
            return 0.0
        succeeded = self._tool_succeeded(message, text)
        base = 0.18 if succeeded else -0.3
        # CB3: adjust by per-tool success rate when enabled and tracker provided
        if policy and policy.adaptive_tool_scoring and self._tool_tracker is not None:
            name = self._tool_name(message)
            if name:
                multiplier = self._tool_tracker.tool_weight_multiplier(name)
                # only amplify the positive base — failures already penalize
                if base > 0:
                    base = base * multiplier
        return base

    def _tool_succeeded(self, message: Dict[str, Any], text: str) -> bool:
        metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
        if "success" in metadata:
            return bool(metadata.get("success"))
        return not bool(_FAILURE_RE.search(text))

    def _looks_like_read(self, message: Dict[str, Any]) -> bool:
        name = self._tool_name(message)
        return any(token in name for token in ("read", "open", "view", "cat"))

    def _tool_name(self, message: Dict[str, Any]) -> str:
        return str(message.get("name") or message.get("tool_name") or message.get("tool_call_id") or "").strip().lower()

    def _extract_files(self, message: Dict[str, Any], text: str) -> List[str]:
        files: List[str] = []
        metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
        for key in ("file_path", "path"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                files.append(value.strip())
        for key in ("paths", "changed_paths", "contextFiles", "activeFiles"):
            values = metadata.get(key)
            if isinstance(values, list):
                files.extend(str(value).strip() for value in values if str(value).strip())
        for match in _FILE_RE.finditer(text):
            files.append(match.group(1))
        seen = set()
        ordered: List[str] = []
        for file_ref in files:
            if file_ref in seen:
                continue
            seen.add(file_ref)
            ordered.append(file_ref)
        return ordered

    def _primary_reason(
        self,
        *,
        message: Dict[str, Any],
        score: float,
        protected: bool,
        file_weight: float,
        tool_weight: float,
        decision_weight: float,
        plan_weight: float,
        superseded_reasons: Sequence[str],
    ) -> str:
        if protected:
            return "protected_turn"
        if superseded_reasons:
            return superseded_reasons[0]
        role = self._normalized_role(message)
        if role in {"tool", "function"} and tool_weight < 0:
            return "failed_tool_call"
        if role in {"tool", "function"} and tool_weight > 0:
            return "successful_tool_call"
        if file_weight > 0:
            return "active_file_context"
        if decision_weight > 0 or plan_weight > 0:
            return "decision_content"
        if role == "user":
            return "user_turn"
        if score <= 0:
            return "low_value_turn"
        return "exploration_turn"

    def _annotate_message(
        self,
        message: Dict[str, Any],
        turn: Optional[ScoredTurn] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        annotated = dict(message)
        base_metadata = annotated.get("metadata", {}) if isinstance(annotated.get("metadata"), dict) else {}
        pruning_metadata = dict(base_metadata.get("pruning", {})) if isinstance(base_metadata.get("pruning"), dict) else {}
        if turn is not None:
            pruning_metadata.update(turn.to_metadata())
        if metadata:
            pruning_metadata.update(metadata)
        if pruning_metadata:
            base_metadata = dict(base_metadata)
            base_metadata["pruning"] = pruning_metadata
            annotated["metadata"] = base_metadata
        return annotated

    def _history_tokens(self, history: List[Dict[str, Any]]) -> int:
        counter = get_token_counter()
        return sum(counter.count(text).count for text in (self._extract_text(m) for m in history) if text)

    def _build_notification(
        self,
        pruned_turns: List[PrunedTurnRecord],
        reason_counts: Dict[str, int],
        trigger: str,
    ) -> str:
        if not pruned_turns:
            return ""
        prefix = "[auto-pruned]" if str(trigger or "").strip().lower() == "auto" else "[pruned]"
        details = ", ".join(
            f"{count} {self._reason_label(reason, count)}"
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        )
        return f"{prefix} {len(pruned_turns)} turns removed ({details})"

    def _count_reasons(self, pruned_turns: List[PrunedTurnRecord]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for turn in pruned_turns:
            key = turn.primary_reason
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _reason_label(self, reason: str, count: int) -> str:
        labels = {
            "failed_retry_succeeded": "superseded failed tool calls",
            "stale_file_read": "stale file reads",
            "corrected_by_user": "superseded user instructions",
            "failed_tool_call": "failed tool calls",
            "low_value_turn": "low-value turns",
            "exploration_turn": "exploration turns",
        }
        label = labels.get(reason, reason.replace("_", " "))
        if count == 1 and label.endswith("s"):
            return label[:-1]
        return label

    def _extract_text(self, message: Dict[str, Any]) -> str:
        return PrunedTurnRecord._extract_text(message)

    @staticmethod
    def _normalized_role(message: Dict[str, Any]) -> str:
        return str(message.get("role", "unknown") or "unknown").strip().lower()
