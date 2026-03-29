"""Proactive scheduled check-ins (OpenClaw-style heartbeats)."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_INTERVAL = 30 # minutes
DEFAULT_PROMPT = "summarize recent git activity and check for issues"


@dataclass
class Heartbeat:
    user_id: int
    chat_id: int
    interval_minutes: int
    prompt: str
    task: Optional[asyncio.Task] = field(default=None, repr=False)
    active: bool = True
    last_run: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class HeartbeatScheduler:
    """manages periodic heartbeat check-ins per user."""

    def __init__(self, send_callback: Callable[..., Any]):
        self._heartbeats: Dict[int, Heartbeat] = {} # user_id -> heartbeat
        self._send_callback = send_callback # async fn(user_id, chat_id, prompt) -> None

    def schedule_heartbeat(self, user_id: int, chat_id: int,
                           interval_minutes: int = DEFAULT_INTERVAL,
                           prompt: str = DEFAULT_PROMPT) -> Heartbeat:
        self.cancel_heartbeat(user_id)
        hb = Heartbeat(
            user_id=user_id, chat_id=chat_id,
            interval_minutes=interval_minutes, prompt=prompt,
        )
        hb.task = asyncio.create_task(self._heartbeat_loop(hb))
        self._heartbeats[user_id] = hb
        logger.info("scheduled heartbeat for user %d every %dm", user_id, interval_minutes)
        return hb

    def cancel_heartbeat(self, user_id: int) -> bool:
        hb = self._heartbeats.pop(user_id, None)
        if hb and hb.task:
            hb.active = False
            hb.task.cancel()
            return True
        return False

    def pause_heartbeat(self, user_id: int) -> bool:
        hb = self._heartbeats.get(user_id)
        if hb:
            hb.active = False
            return True
        return False

    def resume_heartbeat(self, user_id: int) -> bool:
        hb = self._heartbeats.get(user_id)
        if hb:
            hb.active = True
            return True
        return False

    def list_heartbeats(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        hbs = self._heartbeats.values()
        if user_id is not None:
            hbs = [h for h in hbs if h.user_id == user_id]
        return [
            {
                "user_id": h.user_id, "interval_minutes": h.interval_minutes,
                "prompt": h.prompt, "active": h.active, "last_run": h.last_run,
            }
            for h in hbs
        ]

    def get_heartbeat(self, user_id: int) -> Optional[Heartbeat]:
        return self._heartbeats.get(user_id)

    async def _heartbeat_loop(self, hb: Heartbeat) -> None:
        try:
            while True:
                await asyncio.sleep(hb.interval_minutes * 60)
                if not hb.active:
                    continue
                try:
                    hb.last_run = datetime.now().isoformat()
                    await self._send_callback(hb.user_id, hb.chat_id, hb.prompt)
                    logger.info("heartbeat fired for user %d", hb.user_id)
                except Exception as e:
                    logger.error("heartbeat callback failed for user %d: %s", hb.user_id, e)
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        for uid in list(self._heartbeats.keys()):
            self.cancel_heartbeat(uid)
