"""Agent teams and shared scratchpad state."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScratchpadMessage:
    author_agent: str
    role: str
    body: str
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "authorAgent": self.author_agent,
            "role": self.role,
            "body": self.body,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScratchpadMessage":
        return cls(
            author_agent=str(data.get("authorAgent") or data.get("author_agent") or ""),
            role=str(data.get("role") or "info"),
            body=str(data.get("body") or ""),
            ts=str(data.get("ts") or _now()),
        )


@dataclass
class TeamScratchpad:
    team_id: str
    sections: Dict[str, str] = field(default_factory=dict)
    messages: List[ScratchpadMessage] = field(default_factory=list)
    path: Optional[Path] = None

    def __post_init__(self) -> None:
        self._lock = threading.RLock()

    def write_section(self, name: str, body: str) -> None:
        with self._lock:
            self.sections[str(name)] = str(body)
            self.save()

    def append_section(self, name: str, body: str) -> None:
        with self._lock:
            current = self.sections.get(str(name), "")
            self.sections[str(name)] = f"{current}\n{body}".strip() if current else str(body)
            self.save()

    def post_message(self, author: str, role: str, body: str) -> ScratchpadMessage:
        normalized_role = str(role or "info").strip().lower()
        if normalized_role not in {"info", "decision", "blocker", "request"}:
            normalized_role = "info"
        message = ScratchpadMessage(author_agent=str(author or "agent"), role=normalized_role, body=str(body))
        with self._lock:
            self.messages.append(message)
            self.save()
        return message

    def to_context(self, max_tokens: int = 4000) -> str:
        budget = max(200, int(max_tokens) * 4)
        parts = [f"# Team scratchpad {self.team_id}"]
        for name, body in sorted(self.sections.items()):
            parts.append(f"\n## {name}\n{body}")
        message_lines = [f"- [{m.role}] {m.author_agent}: {m.body}" for m in self.messages]
        rendered_messages = "\n".join(message_lines)
        while len("\n\n".join(parts + ["\n## Messages\n" + rendered_messages])) > budget and message_lines:
            message_lines.pop(0)
            rendered_messages = "\n".join(message_lines)
        parts.append("\n## Messages\n" + rendered_messages)
        text = "\n\n".join(parts)
        return text[:budget]

    def to_dict(self) -> dict:
        return {
            "teamId": self.team_id,
            "sections": dict(self.sections),
            "messages": [message.to_dict() for message in self.messages],
        }

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "TeamScratchpad":
        if not path.exists():
            return cls(team_id=path.parent.name or f"team-{uuid.uuid4().hex[:8]}", path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            team_id=str(data.get("teamId") or path.parent.name),
            sections={str(k): str(v) for k, v in (data.get("sections") or {}).items()},
            messages=[ScratchpadMessage.from_dict(item) for item in data.get("messages", []) if isinstance(item, dict)],
            path=path,
        )


class AgentTeam:
    def __init__(self, repo_root: Optional[Path] = None, team_id: Optional[str] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.team_id = team_id or f"team-{uuid.uuid4().hex[:8]}"
        self.team_dir = self.repo_root / ".poor-cli" / "teams" / self.team_id
        self.scratchpad = TeamScratchpad.load(self.team_dir / "scratchpad.json")
        self.scratchpad.team_id = self.team_id
        self.events_path = self.team_dir / "events.ndjson"

    def run_stub(self, goal: str) -> TeamScratchpad:
        self.scratchpad.write_section("plan", goal)
        self.scratchpad.post_message("planner", "decision", f"Plan accepted: {goal}")
        self.scratchpad.append_section("progress", "Executor completed first pass.")
        self.scratchpad.post_message("executor", "info", "Progress updated.")
        self.scratchpad.write_section("review", "PASS: no blockers in stub review.")
        self.scratchpad.post_message("reviewer", "decision", "PASS")
        self._event("team_completed", {"goal": goal})
        return self.scratchpad

    def _event(self, event: str, payload: dict) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": event, **payload}, ensure_ascii=False) + "\n")
