from __future__ import annotations

import copy
import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

SECRET_MARKERS = ("key", "token", "secret", "password", "auth", "credential")
DISMISSED_MARKER = "[tool result dismissed from future context]"
TERMINAL_STATUSES = {"done", "failed", "cancelled"}


def _now() -> float:
    return time.monotonic()


def _public_time(ts: Optional[float]) -> Optional[float]:
    if ts is None:
        return None
    return ts


def _strip_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in SECRET_MARKERS):
                clean[key_text] = "[redacted]"
            else:
                clean[key_text] = _strip_secrets(item)
        return clean
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


def _one_line(value: Any, limit: int) -> str:
    try:
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, sort_keys=True, default=str)
    except Exception:
        text = str(value)
    text = text.splitlines()[0] if text else ""
    if len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


@dataclass
class ToolEvent:
    event_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    status: str = "pending"
    args_preview: str = ""
    args_full: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    duration_ms: Optional[int] = None
    result_preview: str = ""
    result_full: str = ""
    result_full_size: int = 0
    error: Optional[str] = None
    cost_tokens: Optional[int] = None
    stream_chunks: List[str] = field(default_factory=list)
    dismissed: bool = False
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def mark_running(self) -> None:
        if self.status not in TERMINAL_STATUSES:
            self.status = "running"
            self.started_at = self.started_at or _now()
            self.updated_at = _now()

    def finish(self, status: str, result: str = "", error: Optional[str] = None) -> None:
        self.status = status
        self.ended_at = _now()
        if self.started_at is not None:
            self.duration_ms = int((self.ended_at - self.started_at) * 1000)
        self.result_full = result
        self.result_preview = _one_line(result, 200)
        self.result_full_size = len(result.encode("utf-8", errors="replace"))
        self.error = error
        self.updated_at = _now()

    def append_chunk(self, chunk: str) -> None:
        if chunk:
            self.stream_chunks.append(chunk)
            self.updated_at = _now()

    def to_dict(self, include_full: bool = True) -> Dict[str, Any]:
        payload = {
            "eventId": self.event_id,
            "turnId": self.turn_id,
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "status": self.status,
            "argsPreview": self.args_preview,
            "argsFull": copy.deepcopy(self.args_full),
            "startedAt": _public_time(self.started_at),
            "endedAt": _public_time(self.ended_at),
            "durationMs": self.duration_ms,
            "resultPreview": self.result_preview,
            "resultFullSize": self.result_full_size,
            "error": self.error,
            "costTokens": self.cost_tokens,
            "streamChunks": list(self.stream_chunks),
            "dismissed": self.dismissed,
            "updatedAt": self.updated_at,
        }
        if include_full:
            payload["resultFull"] = self.result_full
        return payload


class TimelineStore:
    def __init__(self, *, max_events: int = 500):
        self.max_events = max_events
        self._events: "OrderedDict[str, ToolEvent]" = OrderedDict()

    def list(self, *, turn_id: Optional[str] = None, limit: int = 200) -> List[ToolEvent]:
        events = list(self._events.values())
        if turn_id:
            events = [event for event in events if event.turn_id == turn_id]
        return events[-max(1, limit):]

    def get(self, event_id: str) -> Optional[ToolEvent]:
        return self._events.get(str(event_id))

    def pending(
        self,
        *,
        turn_id: str,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        tool_call_id: str = "",
        event_id: str = "",
    ) -> ToolEvent:
        event_id = str(event_id or tool_call_id or uuid.uuid4())
        event = self._events.get(event_id)
        if event is None:
            clean_args = _strip_secrets(args or {})
            event = ToolEvent(
                event_id=event_id,
                turn_id=str(turn_id or "unknown"),
                tool_call_id=str(tool_call_id or event_id),
                tool_name=str(tool_name or "tool"),
                status="pending",
                args_preview=_one_line(clean_args, 120),
                args_full=clean_args if isinstance(clean_args, dict) else {},
            )
            self._events[event_id] = event
            self._trim()
        return event

    def running(
        self,
        *,
        turn_id: str,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        tool_call_id: str = "",
        event_id: str = "",
    ) -> ToolEvent:
        event = self.pending(
            turn_id=turn_id,
            tool_name=tool_name,
            args=args,
            tool_call_id=tool_call_id,
            event_id=event_id,
        )
        event.mark_running()
        return event

    def result(
        self,
        *,
        event_id: str,
        status: str,
        result: str = "",
        error: Optional[str] = None,
        turn_id: str = "",
        tool_name: str = "",
        tool_call_id: str = "",
    ) -> ToolEvent:
        event = self._events.get(str(event_id))
        if event is None:
            event = self.pending(
                turn_id=turn_id,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                event_id=event_id,
            )
            event.mark_running()
        event.finish(status, result, error)
        return event

    def cancel(self, event_id: str) -> bool:
        event = self._events.get(str(event_id))
        if event is None:
            return False
        event.finish("cancelled", event.result_full, "cancelled")
        return True

    def dismiss(self, event_id: str) -> bool:
        event = self._events.get(str(event_id))
        if event is None:
            return False
        event.dismissed = True
        event.updated_at = _now()
        return True

    def append_chunk(
        self,
        *,
        event_id: str,
        turn_id: str = "",
        tool_call_id: str = "",
        tool_name: str = "",
        chunk: str = "",
    ) -> ToolEvent:
        event = self._events.get(str(event_id))
        if event is None:
            event = self.running(
                turn_id=turn_id,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                event_id=event_id,
            )
        event.append_chunk(chunk)
        return event

    def record_core_event(self, *, request_id: str, event_type: str, data: Dict[str, Any]) -> Optional[ToolEvent]:
        if event_type == "tool_call_start":
            return self.running(
                turn_id=request_id,
                tool_name=str(data.get("toolName", "")),
                args=data.get("toolArgs") if isinstance(data.get("toolArgs"), dict) else {},
                tool_call_id=str(data.get("callId", "")),
                event_id=str(data.get("callId", "")),
            )
        if event_type == "tool_result":
            result_text = str(data.get("toolResult", ""))
            lowered = result_text.lower()
            if "cancelled" in lowered:
                status = "cancelled"
                error = "cancelled"
            elif lowered.startswith("error:") or "failed" in lowered:
                status = "failed"
                error = result_text
            else:
                status = "done"
                error = None
            return self.result(
                event_id=str(data.get("callId", "")),
                status=status,
                result=result_text,
                error=error,
                turn_id=request_id,
                tool_name=str(data.get("toolName", "")),
                tool_call_id=str(data.get("callId", "")),
            )
        return None

    def running_count(self, *, turn_id: Optional[str] = None) -> int:
        return sum(1 for event in self.list(turn_id=turn_id, limit=self.max_events) if event.status == "running")

    def total_count(self, *, turn_id: Optional[str] = None) -> int:
        return len(self.list(turn_id=turn_id, limit=self.max_events))

    def dismissed_events(self) -> List[ToolEvent]:
        return [event for event in self._events.values() if event.dismissed]

    def _trim(self) -> None:
        while len(self._events) > self.max_events:
            self._events.popitem(last=False)


def _replace_text(value: Any, replacements: Dict[str, str]) -> Any:
    if isinstance(value, str):
        text = value
        for old, new in replacements.items():
            if old:
                text = text.replace(old, new)
        return text
    if isinstance(value, list):
        return [_replace_text(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_text(item, replacements) for key, item in value.items()}
    return value


def strip_dismissed_results_from_history(history: Iterable[Dict[str, Any]], events: Iterable[ToolEvent]) -> List[Dict[str, Any]]:
    dismissed = [event for event in events if event.dismissed]
    if not dismissed:
        return [dict(message) for message in history]
    ids = {event.tool_call_id or event.event_id for event in dismissed}
    replacements = {
        event.result_full: DISMISSED_MARKER
        for event in dismissed
        if event.result_full
    }
    cleaned: List[Dict[str, Any]] = []
    for message in history:
        msg = copy.deepcopy(message)
        if msg.get("role") == "tool" and str(msg.get("tool_call_id", "")) in ids:
            msg["content"] = DISMISSED_MARKER
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_result" and str(item.get("tool_use_id", "")) in ids:
                    item["content"] = DISMISSED_MARKER
        if "parts" in msg:
            msg["parts"] = _replace_text(msg["parts"], replacements)
        if replacements:
            msg = _replace_text(msg, replacements)
        cleaned.append(msg)
    return cleaned
