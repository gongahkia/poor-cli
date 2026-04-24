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
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, configuration: BackendConfiguration):
        super().__init__()
        self.title = "poor-cli"
        self.sub_title = ""
        self._configuration = configuration
        self._client = JsonRpcClient(configuration)
        self._events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._request_origins: Dict[str, str] = {}
        self._request_queue_items: Dict[str, str] = {}
        self._transcript: List[tuple[str, str]] = []
        self._activity: List[str] = []
        self._connection_state = "stopped"
        self._provider = "provider?"
        self._model = "model?"
        self._session_id = "-"
        self._active_request_id: Optional[str] = None
        self._active_assistant_index: Optional[int] = None
        self._multiplayer_poll_inflight = False
        self._multiplayer_poll_error_reported = False

    def compose(self) -> ComposeResult:
        yield Static("", id="status")
        with Horizontal(id="main"):
            with Vertical(id="transcript_box"):
                yield Static("Transcript", classes="title")
                yield Static("", id="transcript")
            with Vertical(id="activity_box"):
                yield Static("Activity", classes="title")
                yield Static("", id="activity")
        yield Input(placeholder="Type a prompt and press Enter", id="composer")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#composer", Input).focus()
        self.set_interval(0.05, self._process_events)
        if self._configuration.enable_multiplayer_queue:
            self.set_interval(1.5, self._poll_multiplayer_queue)
        self._set_status("starting")
        threading.Thread(
            target=self._initialize_worker,
            name="poor-cli-textual-init",
            daemon=True,
        ).start()

    def on_unmount(self) -> None:
        self._client.shutdown_if_running()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        event.input.value = ""
        if message:
            self._start_chat_request(message)

    def action_cancel(self) -> None:
        if self._active_request_id:
            self._client.notify("poor-cli/cancelRequest", {"requestId": self._active_request_id})
            self._add_activity("Cancel", self._active_request_id)

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

    def _poll_multiplayer_queue(self) -> None:
        if self._connection_state != "connected":
            return
        if self._active_request_id is not None or self._multiplayer_poll_inflight:
            return
        self._multiplayer_poll_inflight = True
        self._start_rpc_request(
            "Multiplayer Queue",
            "multiplayer.queue.next",
            {},
            event_type="multiplayer_queue_next",
            timeout=5.0,
        )

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
            queue_item_id = self._request_queue_items.pop(request_id, "")
            if request_id == self._active_request_id:
                result = event.get("result") if isinstance(event.get("result"), dict) else {}
                content = str(result.get("content") or "")
                if content and self._active_assistant_index is not None:
                    self._replace_turn(self._active_assistant_index, content)
                self._active_request_id = None
                self._active_assistant_index = None
            if queue_item_id:
                self._finish_multiplayer_queue_item(queue_item_id, "completed")
            self._add_activity("Chat", "Request completed")
            self._set_status(self._connection_state)
            return
        if event_type == "chat_error":
            request_id = str(event.get("requestId") or "")
            queue_item_id = self._request_queue_items.pop(request_id, "")
            if request_id == self._active_request_id:
                self._replace_turn(self._active_assistant_index, str(event.get("error") or "Request failed"))
                self._active_request_id = None
                self._active_assistant_index = None
            if queue_item_id:
                self._finish_multiplayer_queue_item(queue_item_id, "failed")
            self._add_activity("Chat", str(event.get("error") or "Request failed"))
            self._set_status(self._connection_state)
            return
        if event_type == "multiplayer_queue_next":
            self._multiplayer_poll_inflight = False
            self._handle_multiplayer_queue_next(event.get("result"))
            return
        if event_type == "multiplayer_queue_finished":
            self._add_activity("Multiplayer", _summarize_result(event.get("result")))
            return
        if event_type == "rpc_error":
            title = str(event.get("title") or "RPC")
            if title == "Multiplayer Queue":
                self._multiplayer_poll_inflight = False
                if not self._multiplayer_poll_error_reported:
                    self._add_activity(title, str(event.get("error") or "RPC failed"))
                    self._multiplayer_poll_error_reported = True
                return
            self._add_activity(title, str(event.get("error") or "RPC failed"))

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

    def _handle_multiplayer_queue_next(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        item = result.get("item")
        if not isinstance(item, dict):
            return
        prompt = str(item.get("prompt") or "").strip()
        item_id = str(item.get("itemId") or "").strip()
        if not prompt or not item_id:
            return
        request_id = self._start_chat_request(prompt, origin="multiplayer")
        if request_id is None:
            self._finish_multiplayer_queue_item(item_id, "failed")
            return
        self._request_queue_items[request_id] = item_id
        self._add_activity("Multiplayer", f"Started queued prompt {item_id}")

    def _finish_multiplayer_queue_item(self, item_id: str, status: str) -> None:
        self._start_rpc_request(
            "Multiplayer Queue Finish",
            "multiplayer.queue.finish",
            {"itemId": item_id, "status": status},
            event_type="multiplayer_queue_finished",
            timeout=5.0,
        )

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

    def _set_status(self, state: str) -> None:
        request_state = self._active_request_id or "-"
        multiplayer = " | mp:on" if self._configuration.enable_multiplayer_queue else ""
        text = (
            f"poor-cli tui | {state} | session:{self._session_id[:8]} | "
            f"{self._provider}/{self._model} | req:{request_state}{multiplayer}"
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
