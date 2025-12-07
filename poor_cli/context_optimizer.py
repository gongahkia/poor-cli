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
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


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
        # Rough estimation: ~4 characters per token
        self.token_count = len(self.content) // 4
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

    def __init__(self, max_tokens: int = 100000):
        """Initialize context optimizer

        Args:
            max_tokens: Maximum context window size in tokens
        """
        self.max_tokens = max_tokens
        self.summarization_threshold = int(max_tokens * 0.8)  # Summarize at 80%

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
