"""Telegram-multiplayer session bridge."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class BridgedSession:
    user_id: int
    chat_id: int
    room_name: str
    invite_code: str
    monitor_only: bool = False
    task: Optional[asyncio.Task] = field(default=None, repr=False)
    active: bool = True


class MultiplayerBridge:
    """bridges Telegram users into multiplayer poor-cli sessions."""

    def __init__(self, send_callback: Callable[..., Any]):
        self._sessions: Dict[int, BridgedSession] = {} # user_id -> session
        self._send_callback = send_callback # async fn(chat_id, text) -> None

    async def join_session(self, user_id: int, chat_id: int, invite_code: str,
                           room_name: str = "", monitor_only: bool = False) -> bool:
        """join a multiplayer session from Telegram."""
        if user_id in self._sessions:
            await self._send_callback(chat_id, "already in a session. /leave first")
            return False
        session = BridgedSession(
            user_id=user_id, chat_id=chat_id, room_name=room_name or "default",
            invite_code=invite_code, monitor_only=monitor_only,
        )
        self._sessions[user_id] = session
        mode = "monitor" if monitor_only else "participant"
        logger.info("user %d joined room %s as %s", user_id, room_name, mode)
        await self._send_callback(chat_id, f"🔗 joined room `{room_name}` as {mode}")
        return True

    async def leave_session(self, user_id: int) -> bool:
        session = self._sessions.pop(user_id, None)
        if not session:
            return False
        session.active = False
        if session.task:
            session.task.cancel()
        logger.info("user %d left room %s", user_id, session.room_name)
        await self._send_callback(session.chat_id, f"🔌 left room `{session.room_name}`")
        return True

    async def forward_room_event(self, user_id: int, event: Dict[str, Any]) -> None:
        """forward a multiplayer room event to the user's Telegram chat."""
        session = self._sessions.get(user_id)
        if not session or not session.active:
            return
        etype = event.get("type", "unknown")
        sender = event.get("sender", "unknown")
        content = event.get("content", "")
        text = f"[{session.room_name}] {sender}: {content}" if content else f"[{session.room_name}] {etype} from {sender}"
        try:
            await self._send_callback(session.chat_id, text)
        except Exception as e:
            logger.error("forward_room_event failed: %s", e)

    async def monitor_mode(self, user_id: int, chat_id: int, room_name: str,
                           invite_code: str) -> bool:
        """view-only monitoring of a multiplayer session."""
        return await self.join_session(user_id, chat_id, invite_code, room_name, monitor_only=True)

    def is_in_session(self, user_id: int) -> bool:
        return user_id in self._sessions

    def get_session(self, user_id: int) -> Optional[BridgedSession]:
        return self._sessions.get(user_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [
            {"user_id": s.user_id, "room_name": s.room_name,
             "monitor_only": s.monitor_only, "active": s.active}
            for s in self._sessions.values()
        ]

    async def broadcast(self, room_name: str, text: str) -> int:
        """broadcast message to all users in a room."""
        sent = 0
        for s in self._sessions.values():
            if s.room_name == room_name and s.active:
                try:
                    await self._send_callback(s.chat_id, text)
                    sent += 1
                except Exception:
                    pass
        return sent

    async def shutdown(self) -> None:
        for uid in list(self._sessions.keys()):
            await self.leave_session(uid)
