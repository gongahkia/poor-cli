"""Shared state objects for the curses TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class ActivityItem:
    title: str
    detail: str = ""
    created_at: float = field(default_factory=time.time)

    def as_line(self) -> str:
        if self.detail:
            return f"{self.title}: {self.detail}"
        return self.title


@dataclass
class PendingReview:
    kind: str
    prompt_id: str
    title: str
    detail_lines: List[str]
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetailView:
    title: str
    detail_lines: List[str]
    footer: str = "Close [Esc]"
    scroll_offset: int = 0


@dataclass
class MenuItem:
    action: str
    label: str
    detail: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MenuView:
    title: str
    items: List[MenuItem]
    selected_index: int = 0
    footer: str = "Navigate [Up/Down], select [Enter], close [Esc]"


@dataclass
class AppState:
    connection_state: str = "stopped"
    status_detail: str = ""
    provider_name: str = ""
    model_name: str = ""
    voice_state: str = "unavailable"
    voice_ready: bool = False
    voice_detail: str = ""
    voice_mode_enabled: bool = False
    voice_speak_responses: bool = True
    session_id: str = ""
    permission_mode: str = "default"
    sandbox_preset: str = "workspace-write"
    api_key_message: str = ""
    chat_turns: List[ChatTurn] = field(default_factory=list)
    activity: List[ActivityItem] = field(default_factory=list)
    composer: str = ""
    cursor: int = 0
    active_request_id: Optional[str] = None
    active_assistant_index: Optional[int] = None
    pending_review: Optional[PendingReview] = None
    detail_view: Optional[DetailView] = None
    menu_view: Optional[MenuView] = None
    show_help: bool = False
    focus: str = "composer"
    transcript_scroll: int = 0
    activity_scroll: int = 0
    info_message: str = ""
    error_message: str = ""

    def add_activity(self, title: str, detail: str = "") -> None:
        self.activity.insert(0, ActivityItem(title=title, detail=detail))
        if len(self.activity) > 200:
            del self.activity[200:]

    def add_turn(self, role: str, content: str) -> int:
        self.chat_turns.append(ChatTurn(role=role, content=content))
        self.transcript_scroll = 0
        return len(self.chat_turns) - 1

    def append_to_turn(self, index: Optional[int], chunk: str) -> None:
        if index is None or not chunk:
            return
        if 0 <= index < len(self.chat_turns):
            self.chat_turns[index].content += chunk
            self.transcript_scroll = 0

    def replace_turn(self, index: Optional[int], content: str) -> None:
        if index is None:
            return
        if 0 <= index < len(self.chat_turns):
            self.chat_turns[index].content = content
            self.transcript_scroll = 0
