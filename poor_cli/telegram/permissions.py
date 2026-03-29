"""Permission/approval flow for tool execution."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from poor_cli.exceptions import setup_logger
from poor_cli.telegram import formatter as fmt
from poor_cli.telegram.keyboards import permission_keyboard

logger = setup_logger(__name__)

PERMISSION_TIMEOUT = 300 # 5 min default

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None # type: ignore[assignment,misc]
    ContextTypes = None # type: ignore[assignment,misc]


@dataclass
class PendingPermission:
    """represents a pending permission request with asyncio.Event for waiting."""
    prompt_id: str
    tool_name: str
    tool_args: Dict[str, Any]
    user_id: int
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: Optional[bool] = None
    approve_all: bool = False


class PermissionManager:
    """manages permission requests for tool execution in Telegram."""

    def __init__(self, timeout: int = PERMISSION_TIMEOUT):
        self._pending: Dict[str, PendingPermission] = {} # prompt_id -> pending
        self._timeout = timeout
        self._auto_approve: Dict[int, bool] = {} # user_id -> auto-approve flag

    async def handle_permission_request(self, update: Any, context: Any,
                                         tool_name: str, tool_args: Dict[str, Any],
                                         prompt_id: str, user_id: int) -> bool:
        """send inline keyboard and wait for user response. returns True if approved."""
        if self._auto_approve.get(user_id, False):
            logger.info("auto-approved %s for user %d", tool_name, user_id)
            return True
        pending = PendingPermission(
            prompt_id=prompt_id, tool_name=tool_name,
            tool_args=tool_args, user_id=user_id,
        )
        self._pending[prompt_id] = pending
        msg = fmt.format_permission_request(tool_name, tool_args)
        keyboard = permission_keyboard(prompt_id)
        await update.effective_message.reply_text(msg, reply_markup=keyboard)
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning("permission timeout for %s (prompt_id=%s)", tool_name, prompt_id)
            self._pending.pop(prompt_id, None)
            await update.effective_message.reply_text(f"⏱ permission timed out for `{tool_name}`")
            return False
        self._pending.pop(prompt_id, None)
        if pending.approve_all:
            self._auto_approve[user_id] = True
        return pending.approved is True

    async def handle_permission_response(self, prompt_id: str, approved: bool,
                                          approve_all: bool = False) -> bool:
        """resolve a pending permission from callback query."""
        pending = self._pending.get(prompt_id)
        if not pending:
            return False
        pending.approved = approved
        pending.approve_all = approve_all
        pending.event.set()
        return True

    def has_pending(self, prompt_id: str) -> bool:
        return prompt_id in self._pending

    def cancel_all(self, user_id: int) -> int:
        """cancel all pending permissions for a user."""
        cancelled = 0
        for pid, pending in list(self._pending.items()):
            if pending.user_id == user_id:
                pending.approved = False
                pending.event.set()
                cancelled += 1
        return cancelled

    def reset_auto_approve(self, user_id: int) -> None:
        self._auto_approve.pop(user_id, None)
