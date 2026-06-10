"""
Context Window Optimization for poor-cli

Intelligent context management to stay within token limits:
- Smart context pruning
- Auto-summarization of old messages
- Context pinning for important messages
- Sliding window with importance weighting
- Token counting and estimation
"""

import re
from typing import Awaitable, Callable, Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from poor_cli.exceptions import setup_logger
from poor_cli.failure_amnesia import FailureAmnesia, ExtractionCallback
from poor_cli.history_pruning import HistoryPruner
from poor_cli.token_counter import get_token_counter

logger = setup_logger(__name__)

_COMPACTION_FILE_RE = re.compile(r"(?:^|[\s`'\"])((?:[\w.\-]+/)*[\w.\-]+\.[A-Za-z0-9_]+)")
_COMPACTION_DECISION_RE = re.compile(
    r"\b(decided|chosen|approved|rejected|confirmed|implemented|refactored|fixed|switched|kept|dropped)\b",
    re.IGNORECASE,
)
_COMPACTION_UNRESOLVED_RE = re.compile(
    r"\b(todo|fixme|unresolved|remaining|follow[- ]up|next step|pending|still need|open item|edge case)\b",
    re.IGNORECASE,
)
_COMPACTION_FAILURE_RE = re.compile(
    r"\b(error|exception|traceback|failed|failure|permission denied|not found|timed out|timeout)\b",
    re.IGNORECASE,
)


class MessageRole(Enum):
    """Message roles in conversation"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ImportanceLevel(Enum):
    """Importance levels for messages"""
    CRITICAL = 5  # Never prune
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    MINIMAL = 1


@dataclass
class Message:
    """Conversation message"""
    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    token_count: int = 0
    importance: ImportanceLevel = ImportanceLevel.MEDIUM
    pinned: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def estimate_tokens(self) -> int:
        """Estimate token count for message"""
        self.token_count = get_token_counter().count(self.content).count
        return self.token_count


@dataclass
class ContextWindow:
    """Managed context window"""
    messages: List[Message] = field(default_factory=list)
    max_tokens: int = 100000  # Default max context size
    system_message: Optional[Message] = None

    def add_message(self, message: Message):
        """Add message to context"""
        message.estimate_tokens()
        self.messages.append(message)

    def get_total_tokens(self) -> int:
        """Get total token count"""
        total = sum(m.token_count for m in self.messages)
        if self.system_message:
            total += self.system_message.token_count
        return total

    def is_over_limit(self) -> bool:
        """Check if context exceeds token limit"""
        return self.get_total_tokens() > self.max_tokens


class ContextOptimizer:
    """Optimizes conversation context to fit within token limits"""

    def __init__(self, max_tokens: int = 100000, economy_preset: str = "balanced"):
        """Initialize context optimizer

        Args:
            max_tokens: Maximum context window size in tokens
            economy_preset: Economy mode for compression aggressiveness
        """
        self.max_tokens = max_tokens
        self.summarization_threshold = int(max_tokens * 0.8)  # Summarize at 80%
        self._prompt_compressor = None # lazy
        self._economy_preset = economy_preset

    @property
    def prompt_compressor(self):
        """Lazy-load prompt compressor on first access."""
        if self._prompt_compressor is None:
            from .prompt_compressor import PromptCompressor
            self._prompt_compressor = PromptCompressor(economy_preset=self._economy_preset)
        return self._prompt_compressor

    def optimize(self, context: ContextWindow) -> ContextWindow:
        """Optimize context window to fit within limits

        Args:
            context: Context window to optimize

        Returns:
            Optimized context window
        """
        if not context.is_over_limit():
            return context

        logger.info(f"Context optimization triggered: {context.get_total_tokens()} tokens")

        # Strategy 0: Prompt compression on non-recent, non-pinned messages
        context = self._compress_messages(context)

        if not context.is_over_limit():
            return context

        # Strategy 1: Remove low-importance messages
        context = self._prune_low_importance(context)

        if not context.is_over_limit():
            return context

        # Strategy 2: Summarize old messages
        context = self._summarize_old_messages(context)

        if not context.is_over_limit():
            return context

        # Strategy 3: Aggressive pruning (keep only recent + pinned)
        context = self._aggressive_prune(context)

        logger.info(f"After optimization: {context.get_total_tokens()} tokens")

        return context

    def assign_importance(self, message: Message) -> ImportanceLevel:
        """Assign importance level to a message

        Args:
            message: Message to evaluate

        Returns:
            Importance level
        """
        # Pinned messages are critical
        if message.pinned:
            return ImportanceLevel.CRITICAL

        content = message.content.lower()

        # Critical patterns
        critical_patterns = [
            r'error', r'exception', r'failure', r'critical',
            r'checkpoint', r'rollback', r'plan approved',
            r'system:', r'important:'
        ]

        if any(re.search(pattern, content) for pattern in critical_patterns):
            return ImportanceLevel.HIGH

        # High importance patterns
        high_patterns = [
            r'warning', r'caution', r'note:',
            r'file created', r'file modified', r'file deleted',
            r'commit', r'push'
        ]

        if any(re.search(pattern, content) for pattern in high_patterns):
            return ImportanceLevel.HIGH

        # Code blocks are medium importance
        if '```' in content:
            return ImportanceLevel.MEDIUM

        # Short messages are likely low importance
        if len(content) < 100:
            return ImportanceLevel.LOW

        # Default
        return ImportanceLevel.MEDIUM

    def pin_message(self, context: ContextWindow, message_index: int):
        """Pin a message to prevent pruning

        Args:
            context: Context window
            message_index: Index of message to pin
        """
        if 0 <= message_index < len(context.messages):
            context.messages[message_index].pinned = True
            context.messages[message_index].importance = ImportanceLevel.CRITICAL
            logger.info(f"Pinned message {message_index}")

    def unpin_message(self, context: ContextWindow, message_index: int):
        """Unpin a message

        Args:
            context: Context window
            message_index: Index of message to unpin
        """
        if 0 <= message_index < len(context.messages):
            context.messages[message_index].pinned = False
            # Reassign importance
            context.messages[message_index].importance = self.assign_importance(
                context.messages[message_index]
            )
            logger.info(f"Unpinned message {message_index}")

    def summarize_messages(
        self,
        messages: List[Message],
        target_ratio: float = 0.3
    ) -> Message:
        """Summarize a list of messages into one

        Args:
            messages: Messages to summarize
            target_ratio: Target compression ratio (0-1)

        Returns:
            Summarized message
        """
        # Extract key information
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]

        # Build summary
        summary_parts = ["[SUMMARIZED CONTEXT]"]

        if user_messages:
            user_requests = [m.content[:100] for m in user_messages[:5]]
            summary_parts.append(f"User requests: {'; '.join(user_requests)}")

        if assistant_messages:
            # Extract key actions
            actions = []
            for msg in assistant_messages:
                # Look for tool calls or file operations
                if 'read_file' in msg.content.lower():
                    actions.append("Read files")
                if 'write_file' in msg.content.lower() or 'edit_file' in msg.content.lower():
                    actions.append("Modified files")
                if 'bash' in msg.content.lower():
                    actions.append("Executed commands")

            if actions:
                summary_parts.append(f"Actions: {', '.join(set(actions))}")

        summary_content = "\n".join(summary_parts)

        # Create summary message
        summary = Message(
            role=MessageRole.SYSTEM,
            content=summary_content,
            importance=ImportanceLevel.MEDIUM
        )
        summary.estimate_tokens()

        return summary

    def _compress_messages(self, context: ContextWindow) -> ContextWindow:
        """Apply prompt compression to non-recent, non-pinned messages."""
        if len(context.messages) < 4:
            return context
        recent_count = min(3, len(context.messages))
        compressor = self.prompt_compressor
        for i, msg in enumerate(context.messages[:-recent_count]):
            if msg.pinned or msg.importance == ImportanceLevel.CRITICAL:
                continue
            if len(msg.content) < 200: # not worth compressing
                continue
            result = compressor.compress(msg.content)
            if not result.skipped and result.compressed_tokens < result.original_tokens:
                msg.content = result.compressed_text
                msg.estimate_tokens()
        return context

    def _prune_low_importance(self, context: ContextWindow) -> ContextWindow:
        """Remove low-importance messages

        Args:
            context: Context window

        Returns:
            Pruned context
        """
        # Assign importance to all messages
        for message in context.messages:
            if not message.pinned:
                message.importance = self.assign_importance(message)

        # Keep messages with importance >= LOW, plus all pinned
        pruned_messages = [
            m for m in context.messages
            if m.importance.value >= ImportanceLevel.LOW.value or m.pinned
        ]

        removed = len(context.messages) - len(pruned_messages)
        if removed > 0:
            logger.info(f"Pruned {removed} low-importance messages")

        context.messages = pruned_messages
        return context

    def _summarize_old_messages(self, context: ContextWindow) -> ContextWindow:
        """Summarize older messages

        Args:
            context: Context window

        Returns:
            Context with summarized messages
        """
        if len(context.messages) < 10:
            return context

        # Keep recent messages (last 10) + pinned messages
        recent_count = 10
        recent_messages = context.messages[-recent_count:]

        # Messages to summarize (older ones, excluding pinned)
        old_messages = [
            m for m in context.messages[:-recent_count]
            if not m.pinned
        ]

        # Pinned messages to keep
        pinned_messages = [
            m for m in context.messages[:-recent_count]
            if m.pinned
        ]

        if not old_messages:
            return context

        # Summarize old messages
        summary = self.summarize_messages(old_messages)

        # Rebuild context: pinned + summary + recent
        new_messages = pinned_messages + [summary] + recent_messages
        context.messages = new_messages

        logger.info(f"Summarized {len(old_messages)} old messages")

        return context

    def _aggressive_prune(self, context: ContextWindow) -> ContextWindow:
        """Aggressively prune to fit within limits

        Args:
            context: Context window

        Returns:
            Aggressively pruned context
        """
        # Keep only:
        # - System message
        # - All pinned messages
        # - Last 5 messages

        pinned = [m for m in context.messages if m.pinned]
        recent = [m for m in context.messages[-5:] if not m.pinned]

        # Combine and remove duplicates
        message_ids = set()
        unique_messages = []

        for msg in pinned + recent:
            msg_id = id(msg)
            if msg_id not in message_ids:
                message_ids.add(msg_id)
                unique_messages.append(msg)

        # Sort by timestamp to maintain order
        unique_messages.sort(key=lambda m: m.timestamp)

        context.messages = unique_messages

        logger.warning(f"Aggressive pruning: kept {len(unique_messages)} messages")

        return context

    def get_context_stats(self, context: ContextWindow) -> Dict[str, Any]:
        """Get statistics about context window

        Args:
            context: Context window

        Returns:
            Statistics dictionary
        """
        total_tokens = context.get_total_tokens()
        message_count = len(context.messages)

        by_role = {
            MessageRole.USER: 0,
            MessageRole.ASSISTANT: 0,
            MessageRole.SYSTEM: 0
        }

        by_importance = {level: 0 for level in ImportanceLevel}

        for msg in context.messages:
            by_role[msg.role] += 1
            by_importance[msg.importance] += 1

        pinned_count = sum(1 for m in context.messages if m.pinned)

        return {
            "total_tokens": total_tokens,
            "max_tokens": context.max_tokens,
            "utilization": (total_tokens / context.max_tokens * 100) if context.max_tokens > 0 else 0,
            "message_count": message_count,
            "pinned_count": pinned_count,
            "by_role": {role.value: count for role, count in by_role.items()},
            "by_importance": {level.name: count for level, count in by_importance.items()},
            "avg_tokens_per_message": total_tokens / message_count if message_count > 0 else 0
        }


class SmartContextManager:
    """High-level context manager with auto-optimization"""

    def __init__(self, max_tokens: int = 100000, auto_optimize: bool = True):
        """Initialize smart context manager

        Args:
            max_tokens: Maximum context size
            auto_optimize: Auto-optimize when threshold exceeded
        """
        self.context = ContextWindow(max_tokens=max_tokens)
        self.optimizer = ContextOptimizer(max_tokens=max_tokens)
        self.auto_optimize = auto_optimize

    def add_message(
        self,
        role: MessageRole,
        content: str,
        pinned: bool = False
    ) -> Message:
        """Add message to context with auto-optimization

        Args:
            role: Message role
            content: Message content
            pinned: Whether to pin message

        Returns:
            Created message
        """
        message = Message(
            role=role,
            content=content,
            pinned=pinned
        )

        message.importance = self.optimizer.assign_importance(message)
        self.context.add_message(message)

        # Auto-optimize if needed
        if self.auto_optimize and self.context.is_over_limit():
            logger.info("Auto-optimizing context")
            self.context = self.optimizer.optimize(self.context)

        return message

    def pin_last_message(self):
        """Pin the last message"""
        if self.context.messages:
            self.context.messages[-1].pinned = True
            self.context.messages[-1].importance = ImportanceLevel.CRITICAL

    def get_messages_for_api(self, include_system: bool = True) -> List[Dict[str, str]]:
        """Get messages formatted for API

        Args:
            include_system: Include system message

        Returns:
            List of message dictionaries
        """
        messages = []

        if include_system and self.context.system_message:
            messages.append({
                "role": "system",
                "content": self.context.system_message.content
            })

        for msg in self.context.messages:
            messages.append({
                "role": msg.role.value,
                "content": msg.content
            })

        return messages

    def get_stats(self) -> Dict[str, Any]:
        """Get context statistics"""
        return self.optimizer.get_context_stats(self.context)

    def clear_context(self, keep_pinned: bool = True):
        """Clear context window

        Args:
            keep_pinned: Keep pinned messages
        """
        if keep_pinned:
            self.context.messages = [m for m in self.context.messages if m.pinned]
        else:
            self.context.messages = []

        logger.info("Context cleared")


class CompactionTier(Enum):
    PRESERVE = "preserve"
    SUMMARIZE = "summarize"
    DROP = "drop"


@dataclass(frozen=True)
class CompactionPolicy:
    mode: str = "balanced"
    economy_preset: str = "balanced"
    preserve_recent_messages: int = 6
    max_summary_items: int = 6
    drop_tool_chars: int = 600
    prune_score_threshold: float = 0.45
    auto_compact_threshold: float = 0.7
    auto_compact_target: float = 0.4
    allow_model_summary: bool = True


@dataclass(frozen=True)
class HistoryTierAssessment:
    index: int
    tier: CompactionTier
    reason: str
    essential: bool = False
    lesson: str = ""


@dataclass(frozen=True)
class TieredCompactionResult:
    history: List[Dict[str, Any]]
    summary: str
    messages_before: int
    messages_after: int
    tokens_before: int
    tokens_after: int
    removed_tokens: int
    tier_counts: Dict[str, int]
    mode: str
    trigger: str
    utilization_before: float
    utilization_after: float
    pruned_turns: List[Dict[str, Any]] = field(default_factory=list)
    pruned_count: int = 0
    pruning_summary: str = ""
    pruning_reasons: Dict[str, int] = field(default_factory=dict)


SummaryCallback = Callable[[List[Dict[str, Any]], str, CompactionPolicy], Awaitable[str]]


class TieredContextCompactor:
    """Tiered history compactor for provider chat transcripts."""

    def __init__(self):
        # CB3: pull the process-wide tracker so adaptive scoring activates
        # automatically as recordings accumulate during the session.
        try:
            from .tool_success_tracker import get_default_tracker
            tracker = get_default_tracker()
        except Exception:
            tracker = None
        # Respect the user-facing adaptive_tool_scoring strategy override.
        adaptive_override = None
        try:
            from .ux_strategies import load as _load_strategies, adaptive_override_from_str
            adaptive_override = adaptive_override_from_str(
                _load_strategies().get("adaptive_tool_scoring", "auto")
            )
        except Exception:
            adaptive_override = None
        self._history_pruner = HistoryPruner(
            tool_success_tracker=tracker,
            adaptive_tool_scoring_override=adaptive_override,
        )
        self._failure_amnesia = FailureAmnesia()

    @property
    def failure_amnesia_tokens_saved(self) -> int:
        return self._failure_amnesia.tokens_saved

    def policy_for(
        self,
        *,
        mode: str = "balanced",
        economy_preset: str = "balanced",
        auto_compact_threshold: float = 0.7,
        auto_compact_target: float = 0.4,
    ) -> CompactionPolicy:
        normalized_mode = str(mode or "balanced").strip().lower()
        if normalized_mode not in {"gentle", "balanced", "aggressive"}:
            normalized_mode = "balanced"
        preserve_recent = {"gentle": 10, "balanced": 6, "aggressive": 4}[normalized_mode]
        max_summary_items = {"gentle": 8, "balanced": 6, "aggressive": 4}[normalized_mode]
        drop_tool_chars = {"gentle": 1600, "balanced": 600, "aggressive": 250}[normalized_mode]
        preset = str(economy_preset or "balanced").strip().lower() or "balanced"
        prune_score_threshold = {"gentle": 0.25, "balanced": 0.45, "aggressive": 0.65}[normalized_mode]
        if preset == "frugal":
            preserve_recent = max(2, preserve_recent - 2)
            max_summary_items = max(3, max_summary_items - 2)
            drop_tool_chars = min(drop_tool_chars, 250)
            prune_score_threshold += 0.1
        elif preset == "quality":
            preserve_recent += 2
            max_summary_items += 2
            drop_tool_chars = max(drop_tool_chars, 2000)
            prune_score_threshold -= 0.1
        return CompactionPolicy(
            mode=normalized_mode,
            economy_preset=preset,
            preserve_recent_messages=preserve_recent,
            max_summary_items=max_summary_items,
            drop_tool_chars=drop_tool_chars,
            prune_score_threshold=max(-1.0, min(1.5, prune_score_threshold)),
            auto_compact_threshold=max(0.0, float(auto_compact_threshold or 0.0)),
            auto_compact_target=max(0.0, float(auto_compact_target or 0.0)),
            allow_model_summary=True,
        )

    async def compact(
        self,
        history: List[Dict[str, Any]],
        *,
        max_tokens: int = 0,
        mode: str = "balanced",
        economy_preset: str = "balanced",
        trigger: str = "manual",
        summary_callback: Optional[SummaryCallback] = None,
        failure_amnesia_callback: Optional[ExtractionCallback] = None,
        auto_compact_threshold: float = 0.7,
        auto_compact_target: float = 0.4,
    ) -> TieredCompactionResult:
        normalized_history = [self._normalize_message(message) for message in history if isinstance(message, dict)]
        # failure amnesia: prune resolved failure traces first
        try:
            amnesia_result = await self._failure_amnesia.process_history(
                normalized_history,
                extraction_callback=failure_amnesia_callback,
                trigger=trigger,
            )
            normalized_history = amnesia_result.history
            if amnesia_result.failures_pruned > 0:
                logger.info(
                    "failure amnesia pruned %d traces, saved ~%d tokens",
                    amnesia_result.failures_pruned,
                    amnesia_result.tokens_saved,
                )
        except Exception as exc:
            logger.warning("failure amnesia pass failed, continuing: %s", exc)
        messages_before = len(normalized_history)
        tokens_before = self._history_tokens(normalized_history)
        policy = self.policy_for(
            mode=mode,
            economy_preset=economy_preset,
            auto_compact_threshold=auto_compact_threshold,
            auto_compact_target=auto_compact_target,
        )
        if not normalized_history:
            return TieredCompactionResult(
                history=[],
                summary="",
                messages_before=0,
                messages_after=0,
                tokens_before=0,
                tokens_after=0,
                removed_tokens=0,
                tier_counts={tier.value: 0 for tier in CompactionTier},
                mode=policy.mode,
                trigger=str(trigger or "manual"),
                utilization_before=0.0,
                utilization_after=0.0,
                pruned_turns=[],
                pruned_count=0,
                pruning_summary="",
                pruning_reasons={},
            )
        target_tokens = int(max_tokens * policy.auto_compact_target) if max_tokens > 0 and policy.auto_compact_target > 0 else 0
        try:
            from .turn_pin_overlay import TurnPinOverlay
            turn_pin_overlay = TurnPinOverlay().load().all() or None
        except Exception:
            turn_pin_overlay = None
        pruning = self._history_pruner.prune(
            normalized_history,
            target_tokens=target_tokens,
            mode=policy.mode,
            economy_preset=policy.economy_preset,
            trigger=trigger,
            turn_pin_overlay=turn_pin_overlay,
        )
        working_history = pruning.history
        assessments = self._assess_history(working_history, policy)
        summary_messages = [
            working_history[item.index]
            for item in assessments
            if item.tier == CompactionTier.SUMMARIZE
        ]
        dropped_lessons = [self._pruning_lesson(turn) for turn in pruning.pruned_turns]
        dropped_lessons.extend(item.lesson for item in assessments if item.lesson)
        summary_text = self._build_structured_summary(summary_messages, dropped_lessons, policy)
        if summary_text and summary_callback and summary_messages and policy.allow_model_summary:
            try:
                rendered = await summary_callback(summary_messages, summary_text, policy)
            except Exception as exc:
                logger.warning("tiered compaction summary callback failed: %s", exc)
            else:
                if rendered and rendered.strip():
                    summary_text = rendered.strip()
        essential_preserve: List[Tuple[int, Dict[str, Any]]] = []
        optional_preserve: List[Tuple[int, Dict[str, Any]]] = []
        for item in assessments:
            if item.tier != CompactionTier.PRESERVE:
                continue
            target = essential_preserve if item.essential else optional_preserve
            target.append((item.index, working_history[item.index]))
        compacted = self._assemble_history(summary_text, essential_preserve, optional_preserve)
        while target_tokens > 0 and self._history_tokens(compacted) > target_tokens and optional_preserve:
            optional_preserve.pop(0)
            compacted = self._assemble_history(summary_text, essential_preserve, optional_preserve)
        if target_tokens > 0 and self._history_tokens(compacted) > target_tokens and summary_text:
            summary_text = self._condense_summary(summary_text, policy)
            compacted = self._assemble_history(summary_text, essential_preserve, optional_preserve)
        tokens_after = self._history_tokens(compacted)
        tier_counts = {tier.value: 0 for tier in CompactionTier}
        for item in assessments:
            tier_counts[item.tier.value] += 1
        utilization_before = (tokens_before / max_tokens) if max_tokens > 0 else 0.0
        utilization_after = (tokens_after / max_tokens) if max_tokens > 0 else 0.0
        return TieredCompactionResult(
            history=compacted,
            summary=summary_text,
            messages_before=messages_before,
            messages_after=len(compacted),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            removed_tokens=max(0, tokens_before - tokens_after),
            tier_counts=tier_counts,
            mode=policy.mode,
            trigger=str(trigger or "manual"),
            utilization_before=utilization_before,
            utilization_after=utilization_after,
            pruned_turns=[turn.to_dict() for turn in pruning.pruned_turns],
            pruned_count=len(pruning.pruned_turns),
            pruning_summary=pruning.notification,
            pruning_reasons=pruning.reason_counts,
        )

    def _assess_history(
        self,
        history: List[Dict[str, Any]],
        policy: CompactionPolicy,
    ) -> List[HistoryTierAssessment]:
        last_user = self._last_index(history, {"user"})
        last_assistant = self._last_index(history, {"assistant", "model"})
        preserve_recent = self._recent_non_tool_indexes(history, policy.preserve_recent_messages)
        assessments: List[HistoryTierAssessment] = []
        for index, message in enumerate(history):
            role = self._normalized_role(message)
            text = self._extract_text(message)
            essential = False
            if index == last_user:
                essential = True
                assessments.append(HistoryTierAssessment(index, CompactionTier.PRESERVE, "latest_user", True))
                continue
            if index == last_assistant:
                essential = True
                assessments.append(HistoryTierAssessment(index, CompactionTier.PRESERVE, "latest_assistant", True))
                continue
            if self._looks_like_active_context(message):
                essential = True
                assessments.append(HistoryTierAssessment(index, CompactionTier.PRESERVE, "active_or_pinned_context", True))
                continue
            if index in preserve_recent and role in {"user", "assistant", "model"}:
                assessments.append(HistoryTierAssessment(index, CompactionTier.PRESERVE, "recent_turn", essential))
                continue
            if role in {"tool", "function"}:
                if self._is_failed_tool_message(message):
                    assessments.append(
                        HistoryTierAssessment(
                            index,
                            CompactionTier.DROP,
                            "failed_tool_attempt",
                            False,
                            self._tool_lesson(message),
                        )
                    )
                    continue
                if len(text) > policy.drop_tool_chars or text.count("\n") > 24:
                    assessments.append(
                        HistoryTierAssessment(
                            index,
                            CompactionTier.DROP,
                            "raw_tool_output",
                            False,
                            self._tool_lesson(message),
                        )
                    )
                    continue
            if role == "system":
                assessments.append(HistoryTierAssessment(index, CompactionTier.DROP, "rebuildable_system_context"))
                continue
            assessments.append(HistoryTierAssessment(index, CompactionTier.SUMMARIZE, "older_turn"))
        return assessments

    def _assemble_history(
        self,
        summary_text: str,
        essential_preserve: List[Tuple[int, Dict[str, Any]]],
        optional_preserve: List[Tuple[int, Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        ordered = sorted(essential_preserve + optional_preserve, key=lambda item: item[0])
        compacted: List[Dict[str, Any]] = []
        if summary_text.strip():
            compacted.append(
                {
                    "role": "user",
                    "content": f"[COMPACTED CONTEXT]\n{summary_text.strip()}",
                    "parts": [{"text": f"[COMPACTED CONTEXT]\n{summary_text.strip()}"}],
                }
            )
        for _, message in ordered:
            sanitized = self._sanitize_preserved_message(message)
            if sanitized is not None:
                compacted.append(sanitized)
        return compacted

    def _build_structured_summary(
        self,
        messages: List[Dict[str, Any]],
        dropped_lessons: List[str],
        policy: CompactionPolicy,
    ) -> str:
        if not messages and not dropped_lessons:
            return ""
        user_requests: List[str] = []
        files: List[str] = []
        decisions: List[str] = []
        unresolved: List[str] = []
        tool_outcomes: List[str] = []
        for message in messages:
            role = self._normalized_role(message)
            text = self._extract_text(message)
            if not text:
                continue
            if role == "user":
                user_requests.append(self._shorten(text, 160))
            for match in _COMPACTION_FILE_RE.finditer(text):
                files.append(match.group(1))
            if _COMPACTION_DECISION_RE.search(text):
                decisions.append(self._shorten(text, 160))
            if _COMPACTION_UNRESOLVED_RE.search(text):
                unresolved.append(self._shorten(text, 160))
            if role in {"tool", "function"}:
                tool_outcomes.append(self._tool_lesson(message))
        max_items = max(2, policy.max_summary_items)
        turn_count = max(1, sum(1 for message in messages if self._normalized_role(message) == "user"))
        lines = [f"## Session Summary (turns 1-{turn_count})"]
        if user_requests:
            lines.append(f"- User asked: {self._join_unique(user_requests, max_items)}")
        if files:
            lines.append(f"- Files modified/referenced: {self._join_unique(files, max_items)}")
        if decisions:
            lines.append(f"- Key decisions: {self._join_unique(decisions, max_items)}")
        if tool_outcomes:
            lines.append(f"- Tool outcomes: {self._join_unique(tool_outcomes, max_items)}")
        if unresolved:
            lines.append(f"- Unresolved: {self._join_unique(unresolved, max_items)}")
        if dropped_lessons:
            lines.append(f"- Dropped noise lessons: {self._join_unique(dropped_lessons, max_items)}")
        if len(lines) == 1:
            lines.append("- Older turns summarized with no open issues.")
        return "\n".join(lines)

    def _condense_summary(self, summary_text: str, policy: CompactionPolicy) -> str:
        lines = [line for line in summary_text.splitlines() if line.strip()]
        if len(lines) <= 3:
            return summary_text
        header = lines[0]
        bullets = lines[1:1 + max(2, policy.max_summary_items // 2)]
        return "\n".join([header] + bullets)

    def _normalize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(message)
        normalized["role"] = self._normalized_role(message)
        normalized["content"] = self._extract_text(message)
        return normalized

    def _sanitize_preserved_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        role = self._normalized_role(message)
        if role == "system":
            return None
        if role in {"tool", "function"}:
            # Tool result messages are dropped — their content is captured in
            # the compaction summary.  The matching assistant ``tool_calls``
            # field is also stripped below so the provider never receives an
            # orphaned tool-result or tool-call reference.
            return None
        text = self._extract_text(message)
        sanitized = {
            "role": "assistant" if role == "model" else role,
            "content": text,
            "parts": [{"text": text}],
        }
        # Intentionally omit "tool_calls" / "function_call" — the
        # corresponding tool/function result messages are dropped above, so
        # keeping tool_calls would create an orphan that the OpenAI API
        # rejects with "messages with role 'tool' must be a response to a
        # preceding message with 'tool_calls'".
        metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
        if metadata:
            sanitized["metadata"] = dict(metadata)
        if message.get("pinned"):
            sanitized["pinned"] = True
        return sanitized

    def _extract_text(self, message: Dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    if "text" in part:
                        text_parts.append(str(part.get("text", "")))
                    elif part.get("type") == "text":
                        text_parts.append(str(part.get("text", "")))
            content = "\n".join(part for part in text_parts if part)
        parts = message.get("parts")
        if parts and not content:
            text_parts = [str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in parts]
            content = "\n".join(part for part in text_parts if part)
        return str(content or "").strip()

    def _normalized_role(self, message: Dict[str, Any]) -> str:
        return str(message.get("role", "unknown") or "unknown").strip().lower()

    def _history_tokens(self, history: List[Dict[str, Any]]) -> int:
        counter = get_token_counter()
        return sum(counter.count(self._extract_text(message)).count for message in history)

    def _last_index(self, history: List[Dict[str, Any]], roles: set) -> int:
        for index in range(len(history) - 1, -1, -1):
            if self._normalized_role(history[index]) in roles:
                return index
        return -1

    def _recent_non_tool_indexes(self, history: List[Dict[str, Any]], count: int) -> set:
        indexes: List[int] = []
        for index in range(len(history) - 1, -1, -1):
            role = self._normalized_role(history[index])
            if role in {"user", "assistant", "model"}:
                indexes.append(index)
            if len(indexes) >= max(0, count):
                break
        return set(indexes)

    def _looks_like_active_context(self, message: Dict[str, Any]) -> bool:
        text = self._extract_text(message).lower()
        metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
        if message.get("pinned") or metadata.get("pinned"):
            return True
        if metadata.get("contextSource") in {"active_file", "pinned_context"}:
            return True
        return ("--- file:" in text or "file:" in text) and ("pinned" in text or "user request:" in text)

    def _is_failed_tool_message(self, message: Dict[str, Any]) -> bool:
        role = self._normalized_role(message)
        if role not in {"tool", "function"}:
            return False
        return bool(_COMPACTION_FAILURE_RE.search(self._extract_text(message)))

    def _tool_lesson(self, message: Dict[str, Any]) -> str:
        name = str(message.get("name") or message.get("tool_name") or message.get("tool_call_id") or "tool").strip()
        text = self._extract_text(message)
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line:
            return f"{name} output dropped"
        if len(first_line) > 120:
            first_line = first_line[:117] + "..."
        if _COMPACTION_FAILURE_RE.search(text):
            return f"{name} failed: {first_line}"
        return f"{name}: {first_line}"

    @staticmethod
    def _pruning_lesson(turn: Any) -> str:
        if isinstance(turn, dict):
            primary_reason = str(turn.get("primaryReason", "") or "").strip()
        else:
            primary_reason = str(getattr(turn, "primary_reason", "") or "").strip()
        labels = {
            "failed_retry_succeeded": "superseded failed tool call removed",
            "stale_file_read": "stale file read removed",
            "corrected_by_user": "superseded user instruction removed",
            "failed_tool_call": "failed tool call removed",
            "low_value_turn": "low-value turn removed",
            "exploration_turn": "exploration turn removed",
        }
        return labels.get(primary_reason, primary_reason.replace("_", " ").strip())

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) <= limit:
            return compact
        return compact[: max(0, limit - 3)].rstrip() + "..."

    def _join_unique(self, values: List[str], limit: int) -> str:
        seen = set()
        ordered: List[str] = []
        for value in values:
            cleaned = str(value or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            ordered.append(cleaned)
            if len(ordered) >= limit:
                break
        return "; ".join(ordered)
