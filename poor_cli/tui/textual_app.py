"""Minimal Textual frontend for poor-cli."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from typing import Any, Dict, List, Optional

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Input, Static
except Exception as exc:  # pragma: no cover - exercised when optional extra is absent
    App = object  # type: ignore[assignment,misc]
    ComposeResult = object  # type: ignore[assignment,misc]
    Horizontal = Vertical = Footer = Input = Static = None  # type: ignore[assignment]
    _TEXTUAL_IMPORT_ERROR: Optional[BaseException] = exc
else:
    _TEXTUAL_IMPORT_ERROR = None

from .rpc_client import BackendConfiguration, JsonRpcClient
from .autocomplete import Suggestion, all_suggestions, fuzzy_match


def _truncate(value: str, limit: int = 240) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class PoorCLIApp(App):  # type: ignore[misc,valid-type]
    """Small harness-first Textual UI.

    This intentionally keeps the screen narrow: transcript, activity, status,
    composer.
    """

    CSS = """
    Screen {
        background: #10100f;
        color: #e7ddb5;
    }

    #status {
        height: 1;
        background: #d9c77f;
        color: #161616;
        text-style: bold;
        padding: 0 1;
    }

    #hud {
        height: 1;
        color: #a9a07a;
        padding: 0 1;
    }

    #main {
        height: 1fr;
    }

    #transcript_box {
        width: 2fr;
        border: solid #83784f;
        padding: 0 1;
    }

    #activity_box {
        width: 1fr;
        border: solid #83784f;
        padding: 0 1;
    }

    .title {
        height: 1;
        text-style: bold;
        color: #f0e5b7;
    }

    #transcript, #activity {
        height: 1fr;
        overflow-y: auto;
    }

    #composer {
        height: 3;
        border: solid #83784f;
    }

    #suggest {
        max-height: 8;
        background: #1c1b18;
        color: #e7ddb5;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("escape", "cancel", "Cancel"),
        ("tab", "suggest_accept", "Complete"),
        ("up", "suggest_up", "Previous"),
        ("down", "suggest_down", "Next"),
    ]

    def __init__(self, configuration: BackendConfiguration):
        super().__init__()
        self.title = "poor-cli"
        self.sub_title = ""
        self._configuration = configuration
        self._client = JsonRpcClient(configuration)
        self._events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._request_origins: Dict[str, str] = {}
        self._transcript: List[tuple[str, str]] = []
        self._activity: List[str] = []
        self._connection_state = "stopped"
        self._provider = "provider?"
        self._model = "model?"
        self._session_id = "-"
        self._active_request_id: Optional[str] = None
        self._active_assistant_index: Optional[int] = None
        self._hud_inflight = False
        self._hud_text = "tok -/-/- | comp - | mode - | trend - | cost $0.000000"
        self._all_suggestions: List[Suggestion] = []
        self._suggestions: List[Suggestion] = []
        self._suggestion_index = 0
        self._suggest_visible = False

    def compose(self) -> ComposeResult:
        yield Static("", id="status")
        yield Static("", id="hud")
        with Horizontal(id="main"):
            with Vertical(id="transcript_box"):
                yield Static("Transcript", classes="title")
                yield Static("", id="transcript")
            with Vertical(id="activity_box"):
                yield Static("Activity", classes="title")
                yield Static("", id="activity")
        yield Static("", id="suggest")
        yield Input(placeholder="Type a prompt and press Enter", id="composer")
        yield Footer()

    def on_mount(self) -> None:
        self._all_suggestions = all_suggestions()
        self.query_one("#suggest", Static).display = False
        self.query_one("#composer", Input).focus()
        self.set_interval(0.05, self._process_events)
        self.set_interval(2.0, self._poll_hud)
        self._set_status("starting")
        self._render_hud(None)
        threading.Thread(
            target=self._initialize_worker,
            name="poor-cli-textual-init",
            daemon=True,
        ).start()

    def on_unmount(self) -> None:
        self._client.shutdown_if_running()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._suggest_visible:
            self._accept_suggestion()
            return
        message = event.value.strip()
        event.input.value = ""
        if message:
            self._start_chat_request(message)

    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        if text.startswith("/"):
            self._suggestions = fuzzy_match(text, self._all_suggestions)
            self._suggestion_index = 0
            self._render_suggestions()
            return
        self._hide_suggestions()

    def action_cancel(self) -> None:
        if self._suggest_visible:
            self._hide_suggestions()
            return
        if self._active_request_id:
            self._client.notify("poor-cli/cancelRequest", {"requestId": self._active_request_id})
            self._add_activity("Cancel", self._active_request_id)

    def action_suggest_accept(self) -> None:
        if self._suggest_visible:
            self._accept_suggestion()

    def action_suggest_up(self) -> None:
        if not self._suggest_visible or not self._suggestions:
            return
        self._suggestion_index = (self._suggestion_index - 1) % len(self._suggestions)
        self._render_suggestions()

    def action_suggest_down(self) -> None:
        if not self._suggest_visible or not self._suggestions:
            return
        self._suggestion_index = (self._suggestion_index + 1) % len(self._suggestions)
        self._render_suggestions()

    def _initialize_worker(self) -> None:
        try:
            result = self._client.initialize()
            self._events.put({"type": "initialized", "result": result})
        except BaseException as exc:
            self._events.put({"type": "initialize_error", "error": str(exc)})

    def _start_chat_request(self, prompt: str, *, origin: str = "text") -> Optional[str]:
        if self._active_request_id is not None:
            self._add_activity("Busy", "Wait for the active request or cancel it.")
            return None
        request_id = f"textual-{uuid.uuid4().hex[:8]}"
        self._transcript.append(("user", prompt))
        assistant_index = len(self._transcript)
        self._transcript.append(("assistant", ""))
        self._active_request_id = request_id
        self._active_assistant_index = assistant_index
        self._request_origins[request_id] = origin
        self._add_activity("Chat", "Request started")
        self._render_transcript()
        threading.Thread(
            target=self._chat_worker,
            args=(request_id, prompt),
            name=f"poor-cli-textual-chat-{request_id}",
            daemon=True,
        ).start()
        return request_id

    def _chat_worker(self, request_id: str, message: str) -> None:
        try:
            result = self._client.call(
                "poor-cli/chatStreaming",
                {"message": message, "requestId": request_id},
                timeout=None,
            )
            self._events.put({"type": "chat_complete", "requestId": request_id, "result": result})
        except BaseException as exc:
            self._events.put({"type": "chat_error", "requestId": request_id, "error": str(exc)})

    def _start_rpc_request(
        self,
        title: str,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        event_type: str = "rpc_success",
        timeout: float = 15.0,
    ) -> None:
        threading.Thread(
            target=self._rpc_worker,
            args=(title, method, params or {}, event_type, timeout),
            name=f"poor-cli-textual-rpc-{method}",
            daemon=True,
        ).start()

    def _rpc_worker(
        self,
        title: str,
        method: str,
        params: Dict[str, Any],
        event_type: str,
        timeout: float,
    ) -> None:
        try:
            result = self._client.call(method, params, timeout=timeout)
            self._events.put({"type": event_type, "title": title, "method": method, "result": result})
        except BaseException as exc:
            self._events.put({"type": "rpc_error", "title": title, "method": method, "error": str(exc)})

    def _process_events(self) -> None:
        while True:
            try:
                event = self._client.notifications.get_nowait()
            except queue.Empty:
                break
            self._handle_notification(event)
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._handle_ui_event(event)

    def _handle_ui_event(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "initialized":
            self._connection_state = "connected"
            result = event.get("result") if isinstance(event.get("result"), dict) else {}
            capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
            provider = capabilities.get("providerInfo") if isinstance(capabilities.get("providerInfo"), dict) else {}
            self._provider = str(provider.get("name") or self._provider)
            self._model = str(provider.get("model") or self._model)
            if capabilities.get("needsApiKey") is True:
                self._add_activity("API key", str(capabilities.get("message") or "API key required"))
            else:
                self._add_activity("Backend", "Initialized")
            self._set_status("connected")
            return
        if event_type == "initialize_error":
            self._connection_state = "failed"
            self._add_activity("Backend", str(event.get("error") or "Initialization failed"))
            self._set_status("failed")
            return
        if event_type == "chat_complete":
            request_id = str(event.get("requestId") or "")
            if request_id == self._active_request_id:
                result = event.get("result") if isinstance(event.get("result"), dict) else {}
                content = str(result.get("content") or "")
                if content and self._active_assistant_index is not None:
                    self._replace_turn(self._active_assistant_index, content)
                self._active_request_id = None
                self._active_assistant_index = None
            self._add_activity("Chat", "Request completed")
            self._set_status(self._connection_state)
            return
        if event_type == "chat_error":
            request_id = str(event.get("requestId") or "")
            if request_id == self._active_request_id:
                self._replace_turn(self._active_assistant_index, str(event.get("error") or "Request failed"))
                self._active_request_id = None
                self._active_assistant_index = None
            self._add_activity("Chat", str(event.get("error") or "Request failed"))
            self._set_status(self._connection_state)
            return
        if event_type == "rpc_error":
            title = str(event.get("title") or "RPC")
            if title == "HUD":
                self._hud_inflight = False
                return
            self._add_activity(title, str(event.get("error") or "RPC failed"))
            return
        if event_type == "hud_snapshot":
            self._hud_inflight = False
            self._render_hud(event.get("result"))
            return

    def _handle_notification(self, event: Dict[str, Any]) -> None:
        method = str(event.get("method") or "")
        params = event.get("params") if isinstance(event.get("params"), dict) else {}
        if method == "poor-cli/streamChunk":
            chunk = str(params.get("chunk") or "")
            if self._active_assistant_index is not None:
                role, content = self._transcript[self._active_assistant_index]
                self._transcript[self._active_assistant_index] = (role, content + chunk)
                self._render_transcript()
            return
        if method == "poor-cli/thinkingChunk":
            self._add_activity("Thinking", _truncate(str(params.get("chunk") or ""), 120))
            return
        if method == "poor-cli/toolEvent":
            self._add_activity(str(params.get("toolName") or "tool"), str(params.get("eventType") or "event"))
            return
        if method == "poor-cli/permissionReq":
            self._add_activity("Permission", _truncate(_json_text(params), 180))
            return
        if method == "poor-cli/planReq":
            self._add_activity("Plan", _truncate(str(params.get("summary") or "Review requested"), 180))
            return
        self._add_activity(method, _truncate(_json_text(params), 180))

    def _replace_turn(self, index: Optional[int], content: str) -> None:
        if index is None:
            return
        if 0 <= index < len(self._transcript):
            role, _old = self._transcript[index]
            self._transcript[index] = (role, content)
            self._render_transcript()

    def _add_activity(self, title: str, detail: str = "") -> None:
        line = f"{title}: {detail}" if detail else title
        self._activity.insert(0, line)
        del self._activity[120:]
        self._render_activity()

    def _render_transcript(self) -> None:
        if not self.is_mounted:
            return
        lines: List[str] = []
        for role, content in self._transcript[-40:]:
            lines.append(f"{role}> {content}")
        self.query_one("#transcript", Static).update("\n\n".join(lines))

    def _render_activity(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#activity", Static).update("\n".join(self._activity[:80]))

    def _poll_hud(self) -> None:
        if self._connection_state != "connected" or self._hud_inflight:
            return
        self._hud_inflight = True
        self._start_rpc_request(
            "HUD",
            "poor-cli/budgetHudSnapshot",
            {},
            event_type="hud_snapshot",
            timeout=3.0,
        )

    def _render_hud(self, result: Any) -> None:
        if isinstance(result, dict):
            action = result.get("lastAction") if isinstance(result.get("lastAction"), dict) else {}
            outcome = result.get("lastOutcome") if isinstance(result.get("lastOutcome"), dict) else {}
            adaptation = result.get("adaptation") if isinstance(result.get("adaptation"), dict) else {}
            input_tokens = int(outcome.get("input_tokens") or outcome.get("inputTokens") or 0)
            output_tokens = int(outcome.get("output_tokens") or outcome.get("outputTokens") or 0)
            thinking_tokens = int(action.get("max_thinking_tokens") or action.get("maxThinkingTokens") or 0)
            compression = float(action.get("compression_ratio") or action.get("compressionRatio") or 0.0)
            mode = str(action.get("model_tier") or action.get("modelTier") or "-")
            trend = float(adaptation.get("trend") or 0.0)
            cost = float(result.get("projectedCostUsd") or 0.0)
            self._hud_text = (
                f"tok {input_tokens}/{output_tokens}/{thinking_tokens} | "
                f"comp {compression:.0%} | mode {mode} | trend {trend:+.2f} | cost ${cost:.6f}"
            )
        if self.is_mounted:
            self.query_one("#hud", Static).update(self._hud_text)

    def _render_suggestions(self) -> None:
        if not self.is_mounted:
            return
        suggest = self.query_one("#suggest", Static)
        if not self._suggestions:
            suggest.update("")
            suggest.display = False
            self._suggest_visible = False
            return
        lines: List[str] = []
        for index, item in enumerate(self._suggestions[:8]):
            marker = ">" if index == self._suggestion_index else " "
            detail = f"{item.category} - {item.description}" if item.description else item.category
            lines.append(f"{marker} {item.command:<18} {detail}")
        suggest.update("\n".join(lines))
        suggest.display = True
        self._suggest_visible = True

    def _hide_suggestions(self) -> None:
        self._suggestions = []
        self._suggestion_index = 0
        self._suggest_visible = False
        if self.is_mounted:
            suggest = self.query_one("#suggest", Static)
            suggest.update("")
            suggest.display = False

    def _accept_suggestion(self) -> None:
        if not self._suggestions:
            self._hide_suggestions()
            return
        selected = self._suggestions[self._suggestion_index]
        composer = self.query_one("#composer", Input)
        composer.value = f"{selected.command} "
        try:
            composer.cursor_position = len(composer.value)
        except Exception:
            pass
        self._hide_suggestions()

    def _set_status(self, state: str) -> None:
        request_state = self._active_request_id or "-"
        text = (
            f"poor-cli tui | {state} | session:{self._session_id[:8]} | "
            f"{self._provider}/{self._model} | req:{request_state}"
        )
        if self.is_mounted:
            self.query_one("#status", Static).update(text)


def _summarize_result(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("message", "error", "summary"):
            if key in result:
                return _truncate(str(result[key]), 180)
        return _truncate(json.dumps(result, ensure_ascii=False, sort_keys=True), 180)
    return _truncate(str(result), 180)


def run_textual_tui(configuration: BackendConfiguration) -> int:
    if _TEXTUAL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Textual is not installed. Install package dependencies with `python3 -m pip install -e .`."
        ) from _TEXTUAL_IMPORT_ERROR
    app = PoorCLIApp(configuration)
    app.run()
    return 0
