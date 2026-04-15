"""Round-robin multiplayer prompt queue."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional
import time
import uuid

from .multiplayer_attribution import author_tag_for


class MultiPrompterQueueFull(Exception):
    """Raised when a user exceeds their queue quota."""

    def __init__(self, *, connection_id: str, max_per_user: int):
        super().__init__("per-user queue limit reached")
        self.connection_id = connection_id
        self.max_per_user = max_per_user


@dataclass
class QueuedRequest:
    """Queued request for room worker."""

    connection_id: str
    message: Any
    author: Dict[str, str]
    queue_id: str = ""
    submitted_at: float = field(default_factory=time.time)


class MultiPrompterQueue:
    def __init__(self, room: Any, *, max_concurrent: int, max_per_user: int):
        self.room = room
        self.max_concurrent = max(1, int(max_concurrent or 1))
        self.max_per_user = max(1, int(max_per_user or 1))
        self._queues: "OrderedDict[str, Deque[QueuedRequest]]" = OrderedDict()
        self._inflight: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._available = asyncio.Event()
        self._closed = False

    async def submit(self, connection_id: str, message: Any) -> str:
        async with self._lock:
            queued_count = len(self._queues.get(connection_id, ()))
            inflight_count = self._inflight.get(connection_id, 0)
            if queued_count + inflight_count >= self.max_per_user:
                raise MultiPrompterQueueFull(
                    connection_id=connection_id,
                    max_per_user=self.max_per_user,
                )
            queue_id = f"q-{uuid.uuid4().hex}"
            request = QueuedRequest(
                connection_id=connection_id,
                message=message,
                author=author_tag_for(connection_id, self.room.session),
                queue_id=queue_id,
            )
            queue = self._queues.get(connection_id)
            if queue is None:
                queue = deque()
                self._queues[connection_id] = queue
            queue.append(request)
            self._available.set()
            return queue_id

    async def next(self) -> Optional[QueuedRequest]:
        while True:
            await self._available.wait()
            async with self._lock:
                if self._closed:
                    return None
                for _ in range(len(self._queues)):
                    connection_id, queue = self._queues.popitem(last=False)
                    if not queue:
                        continue
                    request = queue.popleft()
                    if queue:
                        self._queues[connection_id] = queue
                    self._inflight[connection_id] = self._inflight.get(connection_id, 0) + 1
                    if not self._queues:
                        self._available.clear()
                    return request
                self._available.clear()

    async def cancel(self, queue_id: str) -> bool:
        normalized = str(queue_id or "").strip()
        if not normalized:
            return False
        async with self._lock:
            for connection_id, queue in list(self._queues.items()):
                remaining = deque(item for item in queue if item.queue_id != normalized)
                if len(remaining) == len(queue):
                    continue
                if remaining:
                    self._queues[connection_id] = remaining
                else:
                    self._queues.pop(connection_id, None)
                if not self._queues:
                    self._available.clear()
                return True
        return False

    async def remove_connection(self, connection_id: str) -> bool:
        async with self._lock:
            removed = bool(self._queues.pop(connection_id, None))
            if not self._queues:
                self._available.clear()
            return removed

    async def task_done(self, request: QueuedRequest) -> None:
        async with self._lock:
            count = self._inflight.get(request.connection_id, 0)
            if count <= 1:
                self._inflight.pop(request.connection_id, None)
            else:
                self._inflight[request.connection_id] = count - 1

    def snapshot(self) -> List[Dict[str, Any]]:
        pending = self._snapshot_pending_order()
        snapshot: List[Dict[str, Any]] = []
        for index, item in enumerate(pending, start=1):
            message = item.message
            params = getattr(message, "params", {}) or {}
            request_id = ""
            if isinstance(params, dict):
                request_id = str(params.get("requestId", "") or "")
            payload = {
                "queueId": item.queue_id,
                "connectionId": item.connection_id,
                "method": str(getattr(message, "method", "") or ""),
                "requestId": request_id,
                "position": index,
                "submittedAt": item.submitted_at,
            }
            payload.update(item.author)
            snapshot.append(payload)
        return snapshot

    def qsize(self) -> int:
        return sum(len(queue) for queue in self._queues.values())

    def close(self) -> None:
        self._closed = True
        self._available.set()

    def _snapshot_pending_order(self) -> List[QueuedRequest]:
        queues: "OrderedDict[str, Deque[QueuedRequest]]" = OrderedDict(
            (connection_id, deque(queue))
            for connection_id, queue in self._queues.items()
            if queue
        )
        ordered: List[QueuedRequest] = []
        while queues:
            connection_id, queue = queues.popitem(last=False)
            item = queue.popleft()
            ordered.append(item)
            if queue:
                queues[connection_id] = queue
        return ordered
