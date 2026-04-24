"""curses-based poor-cli frontend."""

from __future__ import annotations

import argparse
import curses
import json
import queue
import textwrap
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from ..voice.controller import build_default_voice_controller
from ..voice.common import VoiceError
from ..voice.preferences import VoicePreferencesStore
from .rpc_client import BackendConfiguration, JsonRpcClient
from .state import AppState, DetailView, MenuItem, MenuView, PendingReview


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class CursesTUIApplication:
    def __init__(self, configuration: BackendConfiguration):
        self._client = JsonRpcClient(configuration)
        self._configuration = configuration
        self._state = AppState(status_detail=configuration.repo_root)
        self._ui_events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._request_origins: Dict[str, str] = {}
        self._request_queue_items: Dict[str, str] = {}
        self._multiplayer_poll_inflight = False
        self._multiplayer_poll_error_reported = False
        self._last_multiplayer_poll = 0.0
        self._voice_store = VoicePreferencesStore(configuration.repo_root)
        self._voice = build_default_voice_controller(
            configuration.repo_root,
            self._enqueue_voice_event,
        )
        self._voice_rearm_pending = False
        self._running = True
        self._needs_redraw = True
        self._sync_voice_from_controller()

    def run(self) -> int:
        try:
            return curses.wrapper(self._curses_main)
        except KeyboardInterrupt:
            return 0
        finally:
            self._client.shutdown_if_running()

    def _curses_main(self, stdscr: "curses._CursesWindow") -> int:
        curses.use_default_colors()
        stdscr.timeout(25)
        stdscr.keypad(True)
        with context_suppress_curses_error():
            curses.curs_set(1)
        self._start_initialize()
        while self._running:
            self._process_events()
            self._render(stdscr)
            key = stdscr.getch()
            if key != -1:
                self._handle_key(key)
        return 0

    def _start_initialize(self) -> None:
        self._state.connection_state = "starting"
        self._state.status_detail = "Starting backend"
        threading.Thread(
            target=self._initialize_worker,
            name="poor-cli-tui-init",
            daemon=True,
        ).start()

    def _initialize_worker(self) -> None:
        try:
            result = self._client.initialize()
            self._ui_events.put({"type": "initialized", "result": result})
        except BaseException as exc:
            self._ui_events.put({"type": "initialize_error", "error": str(exc)})

    def _enqueue_voice_event(self, event: Dict[str, Any]) -> None:
        self._ui_events.put(event)

    def _start_chat_request(self, prompt: str, *, origin: str = "text") -> Optional[str]:
        message = prompt.strip()
        if not message:
            return None
        if self._handle_local_command(message):
            self._state.composer = ""
            self._state.cursor = 0
            return None
        if self._state.active_request_id is not None:
            self._state.add_activity("Busy", "Wait for the active request or cancel it.")
            return None
        request_id = f"tui-{uuid.uuid4().hex[:8]}"
        self._state.composer = ""
        self._state.cursor = 0
        self._state.add_turn("user", message)
        assistant_index = self._state.add_turn("assistant", "")
        self._state.active_request_id = request_id
        self._state.active_assistant_index = assistant_index
        self._request_origins[request_id] = origin
        self._state.add_activity("Chat", "Request started")
        threading.Thread(
            target=self._chat_worker,
            args=(request_id, assistant_index, message),
            name=f"poor-cli-tui-chat-{request_id}",
            daemon=True,
        ).start()
        return request_id

    def _chat_worker(self, request_id: str, assistant_index: int, message: str) -> None:
        try:
            result = self._client.call(
                "poor-cli/chatStreaming",
                {
                    "message": message,
                    "requestId": request_id,
                },
                timeout=None,
            )
            self._ui_events.put(
                {
                    "type": "chat_complete",
                    "request_id": request_id,
                    "assistant_index": assistant_index,
                    "result": result,
                }
            )
        except BaseException as exc:
            self._ui_events.put(
                {
                    "type": "chat_error",
                    "request_id": request_id,
                    "assistant_index": assistant_index,
                    "error": str(exc),
                }
            )

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
            name=f"poor-cli-tui-rpc-{method}",
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
            self._ui_events.put(
                {
                    "type": event_type,
                    "title": title,
                    "method": method,
                    "result": result,
                }
            )
        except BaseException as exc:
            self._ui_events.put(
                {
                    "type": "rpc_error",
                    "title": title,
                    "method": method,
                    "error": str(exc),
                }
            )

    def _process_events(self) -> None:
        processed = False
        while True:
            try:
                event = self._client.notifications.get_nowait()
            except queue.Empty:
                break
            self._handle_notification(event)
            processed = True
        while True:
            try:
                event = self._ui_events.get_nowait()
            except queue.Empty:
                break
            self._handle_ui_event(event)
            processed = True
        if processed:
            self._needs_redraw = True
        self._maybe_poll_multiplayer_queue()

    def _maybe_poll_multiplayer_queue(self) -> None:
        if not self._configuration.enable_multiplayer_queue:
            return
        if self._state.connection_state != "connected":
            return
        if self._state.active_request_id is not None or self._state.pending_review is not None:
            return
        if self._multiplayer_poll_inflight:
            return
        now = time.monotonic()
        if now - self._last_multiplayer_poll < 1.5:
            return
        self._last_multiplayer_poll = now
        self._multiplayer_poll_inflight = True
        self._start_rpc_request(
            "Multiplayer Queue",
            "multiplayer.queue.next",
            {},
            event_type="multiplayer_queue_next",
            timeout=5.0,
        )

    def _handle_ui_event(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "initialized":
            result = event.get("result") or {}
            capabilities = result.get("capabilities") if isinstance(result, dict) else {}
            if not isinstance(capabilities, dict):
                capabilities = {}
            self._state.connection_state = "connected"
            self._state.permission_mode = str(
                capabilities.get("permissionMode", self._state.permission_mode)
            )
            self._state.sandbox_preset = str(
                capabilities.get("sandboxPreset", self._state.sandbox_preset)
            )
            provider = (
                capabilities.get("providerInfo")
                if isinstance(capabilities.get("providerInfo"), dict)
                else {}
            )
            self._apply_provider_info(provider)
            self._state.status_detail = self._configuration.repo_root
            if capabilities.get("needsApiKey") is True:
                self._state.api_key_message = str(
                    capabilities.get("message", "API key required.")
                )
                self._state.add_activity("API key", self._state.api_key_message)
            else:
                self._state.add_activity("Backend", "Initialized")
            self._start_rpc_request(
                "Sessions",
                "poor-cli/listSessions",
                {"limit": 20},
                event_type="sessions_snapshot",
            )
            return

        if event_type == "initialize_error":
            self._state.connection_state = "failed"
            self._state.error_message = str(event.get("error", "Initialization failed"))
            self._state.status_detail = self._state.error_message
            self._state.add_activity("Backend", self._state.error_message)
            return

        if event_type == "chat_complete":
            request_id = str(event.get("request_id", ""))
            origin = self._request_origins.pop(request_id, "text")
            queue_item_id = self._request_queue_items.pop(request_id, "")
            final_text = ""
            spoken = False
            if request_id == self._state.active_request_id:
                result = event.get("result") or {}
                content = ""
                if isinstance(result, dict):
                    content = str(result.get("content", ""))
                if content and self._state.active_assistant_index is not None:
                    self._state.replace_turn(self._state.active_assistant_index, content)
                    final_text = content
                elif (
                    self._state.active_assistant_index is not None
                    and 0 <= self._state.active_assistant_index < len(self._state.chat_turns)
                ):
                    final_text = self._state.chat_turns[self._state.active_assistant_index].content
                self._state.active_request_id = None
                self._state.active_assistant_index = None
            if origin == "voice" and final_text:
                spoken = self._voice.speak_text(final_text)
            if origin == "voice" and self._state.voice_mode_enabled:
                if spoken:
                    self._voice_rearm_pending = True
                else:
                    self._schedule_voice_rearm()
            if queue_item_id:
                self._finish_multiplayer_queue_item(queue_item_id, "completed")
            self._state.add_activity("Chat", "Request completed")
            return

        if event_type == "chat_error":
            request_id = str(event.get("request_id", ""))
            self._request_origins.pop(request_id, None)
            queue_item_id = self._request_queue_items.pop(request_id, "")
            if request_id == self._state.active_request_id:
                self._state.replace_turn(
                    self._state.active_assistant_index,
                    str(event.get("error", "Request failed")),
                )
                self._state.active_request_id = None
                self._state.active_assistant_index = None
            if queue_item_id:
                self._finish_multiplayer_queue_item(queue_item_id, "failed")
            self._state.add_activity("Chat", str(event.get("error", "Request failed")))
            return

        if event_type == "rpc_success":
            title = str(event.get("title", "RPC"))
            result = event.get("result")
            self._open_detail(title, _detail_lines_for_result(result), footer="Close [Esc]")
            self._state.add_activity(title, _summarize_result(result))
            return

        if event_type == "sessions_snapshot":
            result = event.get("result") or {}
            self._apply_session_snapshot(result)
            return

        if event_type == "sessions_menu":
            result = event.get("result") or {}
            self._apply_session_snapshot(result)
            self._open_session_menu(result)
            return

        if event_type == "session_switched":
            result = event.get("result") or {}
            session = result.get("session") if isinstance(result, dict) else {}
            if isinstance(session, dict):
                session_id = str(session.get("sessionId", "") or "")
                if session_id:
                    self._state.session_id = session_id
                    self._state.add_activity("Session", f"Switched to {session_id}")
            self._state.menu_view = None
            self._start_rpc_request(
                "Sessions",
                "poor-cli/listSessions",
                {"limit": 20},
                event_type="sessions_snapshot",
            )
            return

        if event_type == "session_created":
            result = event.get("result") or {}
            session = result.get("session") if isinstance(result, dict) else {}
            if isinstance(session, dict):
                session_id = str(session.get("sessionId", "") or "")
                if session_id:
                    self._state.session_id = session_id
                    self._state.add_activity("Session", f"Created {session_id}")
            self._open_detail("New Session", _detail_lines_for_result(result), footer="Close [Esc]")
            self._start_rpc_request(
                "Sessions",
                "poor-cli/listSessions",
                {"limit": 20},
                event_type="sessions_snapshot",
            )
            return

        if event_type in {"session_saved", "session_restored"}:
            result = event.get("result") or {}
            title = str(event.get("title", "Session"))
            self._open_detail(title, _detail_lines_for_result(result), footer="Close [Esc]")
            self._state.add_activity(title, _summarize_result(result))
            return

        if event_type == "multiplayer_snapshot" or event_type.startswith("multiplayer_snapshot_"):
            title = str(event.get("title", "Multiplayer"))
            result = event.get("result")
            self._state.add_activity(title, _summarize_result(result))
            self._open_detail(title, _detail_lines_for_result(result), footer="Close [Esc]")
            return

        if event_type == "multiplayer_queue_next":
            self._multiplayer_poll_inflight = False
            self._handle_multiplayer_queue_next(event.get("result"))
            return

        if event_type == "multiplayer_queue_finished":
            result = event.get("result")
            self._state.add_activity("Multiplayer", _summarize_result(result))
            return

        if event_type == "rpc_error":
            title = str(event.get("title", "RPC"))
            if title == "Multiplayer Queue":
                self._multiplayer_poll_inflight = False
                if not self._multiplayer_poll_error_reported:
                    self._state.add_activity(title, str(event.get("error", "RPC failed")))
                    self._multiplayer_poll_error_reported = True
                return
            self._state.add_activity(title, str(event.get("error", "RPC failed")))
            return

        if event_type.startswith("voice_"):
            self._handle_voice_event(event)
            return
        if event_type == "voice_rearm":
            self._start_voice_capture_if_possible()
            return

    def _handle_notification(self, event: Dict[str, Any]) -> None:
        method = str(event.get("method", "") or "")
        params = event.get("params") if isinstance(event.get("params"), dict) else {}
        if method == "poor-cli/streamChunk":
            chunk = str(params.get("chunk", ""))
            done = bool(params.get("done", False))
            self._state.append_to_turn(self._state.active_assistant_index, chunk)
            if done:
                reason = str(params.get("reason", "complete") or "complete")
                self._state.add_activity("Response", reason)
            return
        if method == "poor-cli/thinkingChunk":
            self._state.add_activity("Thinking", _truncate(str(params.get("chunk", "")), 140))
            return
        if method == "poor-cli/toolEvent":
            tool_name = str(params.get("toolName", "tool"))
            event_type = str(params.get("eventType", "event"))
            self._state.add_activity(tool_name, event_type)
            return
        if method == "tool.chunk":
            tool_name = str(params.get("toolName", "tool"))
            chunk = _truncate(_json_text(params.get("chunk", "")), 180)
            self._state.add_activity(tool_name, chunk)
            event_id = str(params.get("eventId", "") or "")
            chunk_index = params.get("chunkIndex")
            if event_id and isinstance(chunk_index, int):
                try:
                    self._client.notify(
                        "poor-cli/toolStreamAck",
                        {
                            "eventId": event_id,
                            "chunksProcessed": chunk_index + 1,
                        },
                    )
                except BaseException as exc:
                    self._state.add_activity("toolStreamAck", str(exc))
            return
        if method == "poor-cli/progress":
            phase = str(params.get("phase", "progress"))
            message = str(params.get("message", ""))
            self._state.add_activity(phase, message)
            return
        if method == "poor-cli/permissionReq":
            self._state.pending_review = PendingReview(
                kind="permission",
                prompt_id=str(params.get("promptId", "") or ""),
                title=str(params.get("toolName", "Permission review")),
                detail_lines=_permission_lines(params),
                payload=params,
            )
            return
        if method == "poor-cli/planReq":
            self._state.pending_review = PendingReview(
                kind="plan",
                prompt_id=str(params.get("promptId", "") or ""),
                title="Plan review",
                detail_lines=_plan_lines(params),
                payload=params,
            )
            return
        if method == "poor-cli/initialized":
            provider = (
                params.get("providerInfo")
                if isinstance(params.get("providerInfo"), dict)
                else {}
            )
            self._apply_provider_info(provider)
            return
        if method == "poor-cli/providerChanged":
            provider = (
                params.get("providerInfo")
                if isinstance(params.get("providerInfo"), dict)
                else {}
            )
            self._apply_provider_info(provider)
            self._state.add_activity("Provider", _summarize_result(provider))
            return
        if method == "poor-cli/costUpdate":
            self._state.add_activity("Cost", _summarize_result(params))
            return
        if method == "poor-cli/contextPressure":
            self._state.add_activity("Context", _summarize_result(params))
            return
        if method == "poor-cli/economyTurnReport":
            self._state.add_activity("Economy", _summarize_result(params))
            return
        if method == "poor-cli/stageEvent":
            self._state.add_activity("Stage", _summarize_result(params))
            return
        self._state.add_activity(method, _truncate(_summarize_result(params), 180))

    def _apply_provider_info(self, provider_info: Dict[str, Any]) -> None:
        self._state.provider_name = str(
            provider_info.get("name", self._state.provider_name)
            or self._state.provider_name
        )
        self._state.model_name = str(
            provider_info.get("model", self._state.model_name) or self._state.model_name
        )

    def _apply_session_snapshot(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        active_session_id = str(result.get("activeSessionId", "") or "")
        if active_session_id:
            self._state.session_id = active_session_id

    def _handle_multiplayer_queue_next(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        item = result.get("item")
        if not isinstance(item, dict):
            return
        prompt = str(item.get("prompt") or "").strip()
        item_id = str(item.get("itemId") or "").strip()
        author_id = str(item.get("authorId") or "").strip()
        if not prompt or not item_id:
            return
        request_id = self._start_chat_request(prompt, origin="multiplayer")
        if request_id is None:
            self._finish_multiplayer_queue_item(item_id, "failed")
            return
        self._request_queue_items[request_id] = item_id
        detail = f"{item_id}"
        if author_id:
            detail = f"{detail} from {author_id}"
        self._state.add_activity("Multiplayer", f"Started queued prompt {detail}")

    def _finish_multiplayer_queue_item(self, item_id: str, status: str) -> None:
        self._start_rpc_request(
            "Multiplayer Queue Finish",
            "multiplayer.queue.finish",
            {"itemId": item_id, "status": status},
            event_type="multiplayer_queue_finished",
            timeout=5.0,
        )

    def _open_action_menu(self) -> None:
        voice_detail = self._state.voice_detail or "Voice controls and settings"
        self._state.menu_view = MenuView(
            title="Actions",
            items=[
                MenuItem("voice-menu", "Voice", voice_detail),
                MenuItem("status-view", "Status view", "Canonical harness status payload"),
                MenuItem("provider-info", "Provider info", "Current provider and model"),
                MenuItem("sandbox-status", "Sandbox status", "Trust and sandbox posture"),
                MenuItem("policy-status", "Policy status", "Permission and policy summary"),
                MenuItem("doctor-report", "Doctor report", "Diagnostics snapshot"),
                MenuItem("multiplayer-status", "Multiplayer", "Participants, queue, threads, and templates"),
                MenuItem("sessions", "Sessions", "Browse and switch active sessions"),
                MenuItem("new-session", "New session", "Create and switch to a fresh session"),
                MenuItem("save-session", "Save session", "Persist the current transcript snapshot"),
                MenuItem("restore-session", "Restore latest session", "Load the most recent saved transcript"),
                MenuItem("clear-activity", "Clear activity", "Trim the activity pane"),
            ],
        )

    def _open_session_menu(self, result: Dict[str, Any]) -> None:
        sessions = result.get("sessions") if isinstance(result.get("sessions"), list) else []
        items: List[MenuItem] = []
        active_session_id = str(result.get("activeSessionId", "") or "")
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_id = str(session.get("sessionId", "") or "")
            model = str(session.get("model", "") or "")
            count = str(session.get("messageCount", "") or "")
            active = "active" if session_id == active_session_id else ""
            detail = " | ".join(part for part in (model, f"{count} msgs" if count else "", active) if part)
            items.append(
                MenuItem(
                    action="switch-session",
                    label=session_id or "unknown-session",
                    detail=detail,
                    payload={"sessionId": session_id},
                )
            )
        if not items:
            items = [MenuItem(action="noop", label="No sessions available", detail="Close with Esc")]
        self._state.menu_view = MenuView(
            title="Sessions",
            items=items,
            footer="Navigate [Up/Down], switch [Enter], close [Esc]",
        )

    def _open_voice_menu(self) -> None:
        voice_settings = self._voice.get_settings()
        talk_label = "Stop talking" if self._state.voice_state == "recording" else "Talk now"
        mode_label = "Conversation mode: on" if voice_settings.conversation_mode else "Conversation mode: off"
        speak_label = "Speak replies: on" if voice_settings.speak_responses else "Speak replies: off"
        self._state.menu_view = MenuView(
            title="Voice",
            items=[
                MenuItem("voice-talk", talk_label, "Start or stop local voice capture"),
                MenuItem(
                    "voice-mode-toggle",
                    mode_label,
                    "Keep listening between voice turns",
                ),
                MenuItem(
                    "voice-speak-toggle",
                    speak_label,
                    "Speak assistant replies for voice turns",
                ),
                MenuItem(
                    "voice-status",
                    "Voice status",
                    "Runtime readiness, blockers, and diagnostics",
                ),
                MenuItem(
                    "voice-settings-help",
                    "Voice settings",
                    "Slash commands for language, model, TTS, and rate",
                ),
            ],
            footer="Navigate [Up/Down], select [Enter], close [Esc]",
        )

    def _open_detail(self, title: str, lines: List[str], *, footer: str) -> None:
        self._state.detail_view = DetailView(title=title, detail_lines=lines, footer=footer)

    def _handle_local_command(self, message: str) -> bool:
        normalized = message.strip()
        if not normalized:
            return False
        if normalized == "/talk":
            self._toggle_voice_recording()
            return True
        if not normalized.startswith("/voice"):
            return False

        parts = normalized.split()
        subcommand = parts[1].lower() if len(parts) > 1 else "status"

        if subcommand in {"status", "show"}:
            self._open_voice_status()
            return True
        if subcommand in {"help", "settings"}:
            self._open_voice_settings_help()
            return True
        if subcommand in {"on", "off", "toggle"}:
            enabled = not self._state.voice_mode_enabled if subcommand == "toggle" else subcommand == "on"
            self._set_voice_mode(enabled)
            return True
        if subcommand == "talk":
            self._toggle_voice_recording()
            return True
        if subcommand == "speak":
            if len(parts) < 3:
                self._state.add_activity("Voice", "Usage: /voice speak on|off|toggle")
                return True
            option = parts[2].lower()
            if option == "toggle":
                target = not self._state.voice_speak_responses
            else:
                target = option == "on"
            self._update_voice_settings(speak_responses=target)
            self._state.add_activity("Voice", f"Speak replies {'on' if target else 'off'}")
            return True
        if subcommand == "language":
            if len(parts) < 3:
                self._state.add_activity("Voice", "Usage: /voice language <auto|en|zh|ja|...>")
                return True
            value = parts[2]
            self._update_voice_settings(language=value)
            self._state.add_activity("Voice", f"Language set to {value}")
            return True
        if subcommand == "model":
            if len(parts) < 3:
                self._state.add_activity("Voice", "Usage: /voice model <tiny|base|small|medium|large-v3>")
                return True
            value = parts[2]
            self._update_voice_settings(model_name=value)
            self._state.add_activity("Voice", f"Voice model set to {value}")
            return True
        if subcommand == "tts":
            if len(parts) < 3:
                self._state.add_activity("Voice", "Usage: /voice tts <auto|say|spd-say|espeak-ng>")
                return True
            value = parts[2]
            self._update_voice_settings(tts_engine=value)
            self._state.add_activity("Voice", f"TTS engine set to {value}")
            return True
        if subcommand == "rate":
            if len(parts) < 3:
                self._state.add_activity("Voice", "Usage: /voice rate <0.5-2.0>")
                return True
            try:
                value = float(parts[2])
            except ValueError:
                self._state.add_activity("Voice", "Voice rate must be a number between 0.5 and 2.0")
                return True
            self._update_voice_settings(tts_rate=value)
            self._state.add_activity("Voice", f"Voice rate set to {value:.2f}")
            return True
        if subcommand == "maxchars":
            if len(parts) < 3:
                self._state.add_activity("Voice", "Usage: /voice maxchars <120+>")
                return True
            try:
                value = int(parts[2])
            except ValueError:
                self._state.add_activity("Voice", "Voice maxchars must be an integer")
                return True
            self._update_voice_settings(max_spoken_chars=value)
            self._state.add_activity("Voice", f"Speech truncation set to {max(120, value)} chars")
            return True

        self._state.add_activity("Voice", f"Unknown command: {normalized}")
        return True

    def _handle_key(self, key: int) -> None:
        if self._state.pending_review is not None:
            self._handle_review_key(key)
            return
        if self._state.menu_view is not None:
            self._handle_menu_key(key)
            return
        if self._state.detail_view is not None:
            self._handle_detail_key(key)
            return
        if self._state.show_help:
            self._handle_help_key(key)
            return

        if key == 3:
            self._running = False
            return
        if key == 9:
            self._cycle_focus()
            return
        if key == 10:
            self._start_chat_request(self._state.composer)
            return
        if key == 27:
            if self._state.voice_state in {"recording", "processing", "speaking"}:
                self._cancel_voice()
            elif self._state.active_request_id is not None:
                self._cancel_active_request()
            return
        if key == 22:
            self._toggle_voice_recording()
            return
        if key == 12:
            self._needs_redraw = True
            return
        if key == 18:
            self._restart_backend()
            return
        if key == 19:
            self._start_rpc_request("Status View", "poor-cli/getStatusView")
            return
        if key == 16:
            self._start_rpc_request("Provider Info", "poor-cli/getProviderInfo")
            return
        if key == 15:
            self._open_action_menu()
            return
        if key == ord("?"):
            self._state.show_help = True
            return

        if self._state.focus in {"transcript", "activity"}:
            if self._handle_scroll_key(key):
                return

        if key in {curses.KEY_BACKSPACE, 127, 8}:
            self._delete_backward()
            return
        if key == curses.KEY_LEFT:
            self._state.cursor = max(0, self._state.cursor - 1)
            return
        if key == curses.KEY_RIGHT:
            self._state.cursor = min(len(self._state.composer), self._state.cursor + 1)
            return
        if key == curses.KEY_HOME:
            self._state.cursor = 0
            return
        if key == curses.KEY_END:
            self._state.cursor = len(self._state.composer)
            return
        if 32 <= key <= 126:
            self._insert_character(chr(key))

    def _handle_help_key(self, key: int) -> None:
        if key in {27, ord("?"), 10}:
            self._state.show_help = False
        elif key == 3:
            self._running = False

    def _handle_review_key(self, key: int) -> None:
        if key in {ord("y"), ord("Y")}:
            self._resolve_review(True)
            return
        if key in {ord("n"), ord("N"), 27}:
            self._resolve_review(False)
            return
        if key == 3:
            self._running = False

    def _handle_menu_key(self, key: int) -> None:
        menu = self._state.menu_view
        if menu is None:
            return
        if key == 3:
            self._running = False
            return
        if key in {27, ord("q"), ord("Q")}:
            self._state.menu_view = None
            return
        if key in {curses.KEY_UP, ord("k"), ord("K")}:
            menu.selected_index = max(0, menu.selected_index - 1)
            return
        if key in {curses.KEY_DOWN, ord("j"), ord("J")}:
            menu.selected_index = min(len(menu.items) - 1, menu.selected_index + 1)
            return
        if key in {10, curses.KEY_ENTER} and menu.items:
            self._execute_menu_action(menu.items[menu.selected_index])

    def _handle_detail_key(self, key: int) -> None:
        detail = self._state.detail_view
        if detail is None:
            return
        if key == 3:
            self._running = False
            return
        if key in {27, 10, ord("q"), ord("Q")}:
            self._state.detail_view = None
            return
        if key in {curses.KEY_UP, ord("k"), ord("K")}:
            detail.scroll_offset = max(0, detail.scroll_offset - 1)
            return
        if key in {curses.KEY_DOWN, ord("j"), ord("J")}:
            detail.scroll_offset += 1
            return
        if key == curses.KEY_PPAGE:
            detail.scroll_offset = max(0, detail.scroll_offset - 10)
            return
        if key == curses.KEY_NPAGE:
            detail.scroll_offset += 10

    def _execute_menu_action(self, item: MenuItem) -> None:
        action = item.action
        if action == "voice-menu":
            self._open_voice_menu()
            return
        if action == "voice-talk":
            self._state.menu_view = None
            self._toggle_voice_recording()
            return
        if action == "voice-mode-toggle":
            self._state.menu_view = None
            self._set_voice_mode(not self._state.voice_mode_enabled)
            return
        if action == "voice-speak-toggle":
            self._state.menu_view = None
            target = not self._state.voice_speak_responses
            self._update_voice_settings(speak_responses=target)
            self._state.add_activity("Voice", f"Speak replies {'on' if target else 'off'}")
            return
        if action == "voice-status":
            self._state.menu_view = None
            self._open_voice_status()
            return
        if action == "voice-settings-help":
            self._state.menu_view = None
            self._open_voice_settings_help()
            return
        if action == "status-view":
            self._state.menu_view = None
            self._start_rpc_request("Status View", "poor-cli/getStatusView")
            return
        if action == "provider-info":
            self._state.menu_view = None
            self._start_rpc_request("Provider Info", "poor-cli/getProviderInfo")
            return
        if action == "sandbox-status":
            self._state.menu_view = None
            self._start_rpc_request("Sandbox Status", "poor-cli/getSandboxStatus")
            return
        if action == "policy-status":
            self._state.menu_view = None
            self._start_rpc_request("Policy Status", "poor-cli/getPolicyStatus")
            return
        if action == "doctor-report":
            self._state.menu_view = None
            self._start_rpc_request("Doctor Report", "poor-cli/getDoctorReport")
            return
        if action == "multiplayer-status":
            self._state.menu_view = None
            self._start_rpc_request(
                "Multiplayer",
                "multiplayer.snapshot",
                {},
                event_type="multiplayer_snapshot",
            )
            return
        if action == "sessions":
            self._start_rpc_request(
                "Sessions",
                "poor-cli/listSessions",
                {"limit": 30},
                event_type="sessions_menu",
            )
            return
        if action == "new-session":
            self._state.menu_view = None
            self._start_rpc_request(
                "New Session",
                "poor-cli/createSession",
                {"makeDefault": True},
                event_type="session_created",
            )
            return
        if action == "save-session":
            self._state.menu_view = None
            self._start_rpc_request(
                "Save Session",
                "poor-cli/saveSession",
                {},
                event_type="session_saved",
            )
            return
        if action == "restore-session":
            self._state.menu_view = None
            self._start_rpc_request(
                "Restore Session",
                "poor-cli/restoreSession",
                {},
                event_type="session_restored",
            )
            return
        if action == "switch-session":
            self._state.menu_view = None
            self._start_rpc_request(
                "Switch Session",
                "poor-cli/switchSession",
                {"sessionId": item.payload.get("sessionId", "")},
                event_type="session_switched",
            )
            return
        if action == "clear-activity":
            self._state.activity.clear()
            self._state.activity_scroll = 0
            self._state.menu_view = None
            return

    def _cycle_focus(self) -> None:
        order = ["composer", "transcript", "activity"]
        try:
            index = order.index(self._state.focus)
        except ValueError:
            index = 0
        self._state.focus = order[(index + 1) % len(order)]

    def _handle_scroll_key(self, key: int) -> bool:
        if self._state.focus == "transcript":
            target = "transcript_scroll"
            line_count = len(_render_transcript_lines(self._state.chat_turns, 80))
        else:
            target = "activity_scroll"
            line_count = len(_render_activity_lines(self._state.activity, 80))
        current = getattr(self._state, target)
        if key in {curses.KEY_UP, ord("k"), ord("K")}:
            setattr(self._state, target, current + 1)
            return True
        if key in {curses.KEY_DOWN, ord("j"), ord("J")}:
            setattr(self._state, target, max(0, current - 1))
            return True
        if key == curses.KEY_PPAGE:
            setattr(self._state, target, current + 10)
            return True
        if key == curses.KEY_NPAGE:
            setattr(self._state, target, max(0, current - 10))
            return True
        if key == curses.KEY_HOME:
            setattr(self._state, target, max(0, line_count))
            return True
        if key == curses.KEY_END:
            setattr(self._state, target, 0)
            return True
        return False

    def _resolve_review(self, allowed: bool) -> None:
        review = self._state.pending_review
        if review is None:
            return
        method = "poor-cli/permissionRes" if review.kind == "permission" else "poor-cli/planRes"
        params: Dict[str, Any] = {
            "promptId": review.prompt_id,
            "allowed": allowed,
        }
        if review.kind == "permission":
            params["approvedPaths"] = []
            params["approvedChunks"] = []
        try:
            self._client.notify(method, params)
            detail = "approved" if allowed else "denied"
            self._state.add_activity(review.title, detail)
        except BaseException as exc:
            self._state.add_activity(review.title, str(exc))
        finally:
            self._state.pending_review = None

    def _insert_character(self, ch: str) -> None:
        composer = self._state.composer
        cursor = self._state.cursor
        self._state.composer = composer[:cursor] + ch + composer[cursor:]
        self._state.cursor = cursor + 1

    def _delete_backward(self) -> None:
        if self._state.cursor <= 0:
            return
        composer = self._state.composer
        cursor = self._state.cursor
        self._state.composer = composer[: cursor - 1] + composer[cursor:]
        self._state.cursor = cursor - 1

    def _cancel_active_request(self) -> None:
        request_id = self._state.active_request_id
        if not request_id:
            return
        try:
            self._client.notify("poor-cli/cancelRequest", {"requestId": request_id})
            self._state.add_activity("Cancel", request_id)
            self._request_origins.pop(request_id, None)
            self._state.active_request_id = None
            self._state.active_assistant_index = None
        except BaseException as exc:
            self._state.add_activity("Cancel failed", str(exc))

    def _cancel_voice(self) -> None:
        if self._state.voice_mode_enabled:
            self._set_voice_mode(False, announce=False)
        try:
            cancelled = self._voice.cancel()
        except VoiceError as exc:
            self._state.add_activity("Voice", str(exc))
            return
        if cancelled:
            self._state.add_activity("Voice", "Cancelled")

    def _toggle_voice_recording(self) -> None:
        try:
            if (
                self._state.active_request_id is not None
                and self._state.voice_state in {"idle", "speaking", "unavailable"}
            ):
                self._cancel_active_request()
            self._voice.toggle_recording()
        except VoiceError as exc:
            self._state.add_activity("Voice", str(exc))
            self._state.voice_detail = str(exc)
            self._needs_redraw = True

    def _open_voice_status(self) -> None:
        diagnostics = self._voice.diagnostics()
        self._sync_voice_from_controller()
        lines = diagnostics.as_lines()
        settings = self._voice.get_settings()
        lines.extend(
            [
                "",
                f"Conversation mode: {'on' if settings.conversation_mode else 'off'}",
                f"Max spoken chars: {settings.max_spoken_chars}",
                "",
                "Commands:",
                "/voice on | /voice off | /voice talk",
                "/voice speak on|off",
                "/voice language <code>",
                "/voice model <name>",
                "/voice tts <auto|say|spd-say|espeak-ng>",
                "/voice rate <0.5-2.0>",
            ]
        )
        self._open_detail("Voice Status", lines, footer="Close [Esc]")

    def _open_voice_settings_help(self) -> None:
        settings = self._voice.get_settings()
        lines = [
            "Current settings:",
            f"conversation_mode: {settings.conversation_mode}",
            f"speak_responses: {settings.speak_responses}",
            f"language: {settings.language}",
            f"model_name: {settings.model_name}",
            f"tts_engine: {settings.tts_engine}",
            f"tts_rate: {settings.tts_rate}",
            f"max_spoken_chars: {settings.max_spoken_chars}",
            "",
            "Slash commands:",
            "/voice on",
            "/voice off",
            "/voice talk",
            "/voice status",
            "/voice speak on|off|toggle",
            "/voice language auto|en|zh|ja|...",
            "/voice model tiny|base|small|medium|large-v3",
            "/voice tts auto|say|spd-say|espeak-ng",
            "/voice rate 1.0",
            "/voice maxchars 600",
        ]
        self._open_detail("Voice Settings", lines, footer="Close [Esc]")

    def _handle_voice_event(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "voice_state":
            state = str(event.get("state", "idle") or "idle")
            detail = str(event.get("detail", "") or "")
            self._state.voice_state = state
            self._sync_voice_from_controller()
            self._state.voice_detail = detail or self._state.voice_detail
            if state in {"recording", "processing", "speaking"}:
                self._state.add_activity("Voice", detail or state)
            if state == "idle" and self._voice_rearm_pending and self._state.voice_mode_enabled:
                self._voice_rearm_pending = False
                self._schedule_voice_rearm()
            return
        if event_type == "voice_transcription":
            text = str(event.get("text", "") or "").strip()
            if not text:
                return
            self._state.add_activity("Voice", _truncate(text, 140))
            self._start_chat_request(text, origin="voice")
            return
        if event_type == "voice_empty":
            self._state.add_activity("Voice", "No speech detected")
            return
        if event_type == "voice_error":
            message = str(event.get("message", "Voice failed") or "Voice failed")
            self._state.voice_detail = message
            self._state.add_activity("Voice", message)
            return
        if event_type == "voice_settings":
            self._sync_voice_from_controller()
            return

    def _restart_backend(self) -> None:
        self._voice_rearm_pending = False
        self._voice.cancel()
        self._client.shutdown_if_running()
        self._state.connection_state = "starting"
        self._state.status_detail = "Restarting backend"
        self._state.active_request_id = None
        self._state.active_assistant_index = None
        self._state.pending_review = None
        self._state.detail_view = None
        self._state.menu_view = None
        self._state.add_activity("Backend", "Restart requested")
        self._start_initialize()

    def _sync_voice_from_controller(self) -> None:
        diagnostics = self._voice.diagnostics()
        settings = self._voice.get_settings()
        self._state.voice_state = diagnostics.state
        self._state.voice_ready = diagnostics.ready
        self._state.voice_detail = diagnostics.summary()
        self._state.voice_mode_enabled = bool(settings.conversation_mode)
        self._state.voice_speak_responses = bool(settings.speak_responses)

    def _update_voice_settings(self, **changes):
        settings = self._voice.update_settings(**changes)
        self._voice_store.save(settings)
        self._sync_voice_from_controller()
        return settings

    def _set_voice_mode(self, enabled: bool, *, announce: bool = True) -> None:
        settings = self._update_voice_settings(conversation_mode=enabled)
        self._voice_rearm_pending = False
        if announce:
            self._state.add_activity(
                "Voice",
                f"Conversation mode {'on' if settings.conversation_mode else 'off'}",
            )
        if enabled:
            self._schedule_voice_rearm(immediate=True)

    def _schedule_voice_rearm(self, *, immediate: bool = False) -> None:
        if not self._state.voice_mode_enabled:
            return
        delay_ms = 0 if immediate else self._voice.get_settings().auto_rearm_delay_ms

        def worker() -> None:
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
            self._ui_events.put({"type": "voice_rearm"})

        threading.Thread(
            target=worker,
            name="poor-cli-voice-rearm",
            daemon=True,
        ).start()

    def _start_voice_capture_if_possible(self) -> None:
        if not self._state.voice_mode_enabled:
            return
        if self._state.active_request_id is not None:
            return
        if self._state.voice_state != "idle":
            return
        try:
            self._voice.start_recording()
        except VoiceError as exc:
            self._state.add_activity("Voice", str(exc))
            self._state.voice_detail = str(exc)

    def _render(self, stdscr: "curses._CursesWindow") -> None:
        if not self._needs_redraw:
            return
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        if height < 10 or width < 60:
            self._safe_addnstr(
                stdscr,
                0,
                0,
                "Terminal too small for poor-cli tui.",
                width - 1,
                curses.A_BOLD,
            )
            stdscr.refresh()
            return
        self._render_status_bar(stdscr, width)
        self._render_body(stdscr, height, width)
        self._render_composer(stdscr, height, width)
        self._render_footer(stdscr, height, width)
        if self._state.pending_review is not None:
            self._render_modal(
                stdscr,
                width,
                height,
                self._state.pending_review.title,
                self._state.pending_review.detail_lines,
                "Approve [y] / Deny [n]",
            )
        elif self._state.menu_view is not None:
            self._render_menu(stdscr, width, height, self._state.menu_view)
        elif self._state.detail_view is not None:
            self._render_modal(
                stdscr,
                width,
                height,
                self._state.detail_view.title,
                self._state.detail_view.detail_lines,
                self._state.detail_view.footer,
                scroll_offset=self._state.detail_view.scroll_offset,
            )
        elif self._state.show_help:
            self._render_modal(
                stdscr,
                width,
                height,
                "Key Help",
                _help_lines(),
                "Close [?] / [Esc]",
            )
        cursor_x = self._composer_cursor_x(width)
        if self._state.focus == "composer" and self._state.detail_view is None and self._state.menu_view is None and self._state.pending_review is None and not self._state.show_help:
            with context_suppress_curses_error():
                stdscr.move(height - 2, cursor_x)
        stdscr.refresh()
        self._needs_redraw = False

    def _render_status_bar(self, stdscr: "curses._CursesWindow", width: int) -> None:
        provider = self._state.provider_name or "provider?"
        model = self._state.model_name or "model?"
        request_state = self._state.active_request_id or "-"
        session_text = self._state.session_id[:8] if self._state.session_id else "-"
        voice_label = self._state.voice_state
        if self._state.voice_mode_enabled:
            voice_label = f"{voice_label}+mode"
        left = f" poor-cli tui | {self._state.connection_state} | focus:{self._state.focus} "
        right = (
            f" session:{session_text} | voice:{voice_label} | {provider}/{model} | "
            f"sandbox:{self._state.sandbox_preset} | mode:{self._state.permission_mode} | "
            f"req:{request_state} "
        )
        line = _fit_status_line(left, right, width)
        self._safe_addnstr(stdscr, 0, 0, line, width - 1, curses.A_REVERSE)

    def _render_body(self, stdscr: "curses._CursesWindow", height: int, width: int) -> None:
        top = 1
        bottom = height - 4
        split = max(30, min(width - 24, int(width * 0.68)))
        transcript_attr = curses.A_BOLD | (curses.A_UNDERLINE if self._state.focus == "transcript" else 0)
        activity_attr = curses.A_BOLD | (curses.A_UNDERLINE if self._state.focus == "activity" else 0)
        self._safe_addnstr(stdscr, top, 0, " Transcript ", split - 1, transcript_attr)
        self._safe_addnstr(stdscr, top, split + 1, " Activity ", width - split - 2, activity_attr)
        for row in range(top + 1, bottom):
            self._safe_addch(stdscr, row, split, ord("|"))
        transcript_lines = _render_transcript_lines(
            self._state.chat_turns,
            split - 1,
        )
        activity_lines = _render_activity_lines(
            self._state.activity,
            width - split - 2,
        )
        transcript_window = _window_from_bottom(
            transcript_lines,
            bottom - top - 1,
            self._state.transcript_scroll,
        )
        activity_window = _window_from_bottom(
            activity_lines,
            bottom - top - 1,
            self._state.activity_scroll,
        )
        for index, line in enumerate(transcript_window, start=top + 1):
            self._safe_addnstr(stdscr, index, 0, line, split - 1)
        for index, line in enumerate(activity_window, start=top + 1):
            self._safe_addnstr(stdscr, index, split + 1, line, width - split - 2)

    def _render_composer(self, stdscr: "curses._CursesWindow", height: int, width: int) -> None:
        row = height - 2
        self._safe_addnstr(stdscr, row - 1, 0, "-" * max(1, width - 1), width - 1)
        prompt = "> "
        available = max(10, width - len(prompt) - 1)
        composer, _start = _visible_tail(self._state.composer, self._state.cursor, available)
        prompt_attr = curses.A_BOLD | (curses.A_UNDERLINE if self._state.focus == "composer" else 0)
        self._safe_addnstr(stdscr, row, 0, prompt, len(prompt), prompt_attr)
        self._safe_addnstr(stdscr, row, len(prompt), composer, available)

    def _composer_cursor_x(self, width: int) -> int:
        available = max(10, width - 3)
        _, start = _visible_tail(self._state.composer, self._state.cursor, available)
        return min(width - 2, 2 + self._state.cursor - start)

    def _render_footer(self, stdscr: "curses._CursesWindow", height: int, width: int) -> None:
        status = self._state.api_key_message or self._state.error_message or self._state.info_message
        if not status:
            status = (
                "Enter send | Ctrl-V talk | /voice on | Tab focus | Ctrl-O actions | Esc cancel | Ctrl-R restart | "
                "Ctrl-S status | Ctrl-P provider | ? help | Ctrl-C quit"
            )
        self._safe_addnstr(
            stdscr,
            height - 1,
            0,
            _truncate(status, width - 1),
            width - 1,
            curses.A_DIM,
        )

    def _render_modal(
        self,
        stdscr: "curses._CursesWindow",
        width: int,
        height: int,
        title: str,
        lines: Iterable[str],
        footer: str,
        *,
        scroll_offset: int = 0,
    ) -> None:
        content = list(lines)
        box_width = min(width - 8, max(36, int(width * 0.72)))
        wrapped: List[str] = []
        for line in content:
            wrapped.extend(textwrap.wrap(line, width=box_width - 4) or [""])
        visible_height = max(4, height - 10)
        visible_lines = _window_from_top(wrapped, visible_height, scroll_offset)
        box_height = min(height - 4, len(visible_lines) + 5)
        start_y = max(1, (height - box_height) // 2)
        start_x = max(2, (width - box_width) // 2)
        _draw_box(stdscr, start_y, start_x, box_height, box_width)
        self._safe_addnstr(
            stdscr,
            start_y,
            start_x + 2,
            f"[ {title} ]",
            box_width - 4,
            curses.A_BOLD,
        )
        for index, line in enumerate(visible_lines, start=1):
            if index >= box_height - 2:
                break
            self._safe_addnstr(stdscr, start_y + index, start_x + 2, line, box_width - 4)
        self._safe_addnstr(
            stdscr,
            start_y + box_height - 2,
            start_x + 2,
            _truncate(footer, box_width - 4),
            box_width - 4,
            curses.A_REVERSE,
        )

    def _render_menu(
        self,
        stdscr: "curses._CursesWindow",
        width: int,
        height: int,
        menu: MenuView,
    ) -> None:
        lines = []
        for index, item in enumerate(menu.items, start=1):
            prefix = ">" if index - 1 == menu.selected_index else " "
            label = f"{prefix} {item.label}"
            if item.detail:
                label = f"{label} - {item.detail}"
            lines.append(label)
        self._render_modal(stdscr, width, height, menu.title, lines, menu.footer)

    def _safe_addnstr(
        self,
        window: "curses._CursesWindow",
        y: int,
        x: int,
        text: str,
        max_chars: int,
        attr: int = 0,
    ) -> None:
        with context_suppress_curses_error():
            window.addnstr(y, x, text, max_chars, attr)

    def _safe_addch(
        self,
        window: "curses._CursesWindow",
        y: int,
        x: int,
        ch: int,
        attr: int = 0,
    ) -> None:
        with context_suppress_curses_error():
            window.addch(y, x, ch, attr)


class context_suppress_curses_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, _tb) -> bool:
        return exc_type is curses.error


def _fit_status_line(left: str, right: str, width: int) -> str:
    usable = max(1, width - 1)
    if len(left) + len(right) <= usable:
        middle = " " * max(1, usable - len(left) - len(right))
        return (left + middle + right)[:usable]
    combined = f"{left.strip()}|{right.strip()}"
    return _truncate(combined, usable)


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _visible_tail(text: str, cursor: int, width: int) -> tuple[str, int]:
    cursor = max(0, min(len(text), cursor))
    if len(text) <= width:
        return text, 0
    start = max(0, cursor - width + 1)
    end = start + width
    return text[start:end], start


def _render_transcript_lines(turns: List[Any], width: int) -> List[str]:
    lines: List[str] = []
    for turn in turns:
        role = "U" if getattr(turn, "role", "") == "user" else "A"
        content = getattr(turn, "content", "") or ""
        wrapped = textwrap.wrap(content, width=max(8, width - 4)) or [""]
        lines.append(f"{role}> {wrapped[0]}")
        for extra in wrapped[1:]:
            lines.append(f"   {extra}")
        lines.append("")
    return lines


def _render_activity_lines(items: List[Any], width: int) -> List[str]:
    lines: List[str] = []
    for item in items:
        text = item.as_line()
        wrapped = textwrap.wrap(text, width=max(8, width - 1)) or [""]
        lines.extend(wrapped)
        lines.append("")
    return lines


def _window_from_bottom(lines: List[str], height: int, offset_from_bottom: int) -> List[str]:
    if height <= 0:
        return []
    if len(lines) <= height:
        return [""] * (height - len(lines)) + lines
    offset = max(0, min(offset_from_bottom, max(0, len(lines) - height)))
    end = len(lines) - offset
    start = max(0, end - height)
    window = lines[start:end]
    if len(window) < height:
        window = [""] * (height - len(window)) + window
    return window


def _window_from_top(lines: List[str], height: int, offset_from_top: int) -> List[str]:
    if height <= 0:
        return []
    if len(lines) <= height:
        return lines + [""] * (height - len(lines))
    offset = max(0, min(offset_from_top, max(0, len(lines) - height)))
    window = lines[offset : offset + height]
    if len(window) < height:
        window += [""] * (height - len(window))
    return window


def _draw_box(stdscr: "curses._CursesWindow", y: int, x: int, height: int, width: int) -> None:
    right = x + width - 1
    bottom = y + height - 1
    for col in range(x + 1, right):
        with context_suppress_curses_error():
            stdscr.addch(y, col, ord("-"))
            stdscr.addch(bottom, col, ord("-"))
    for row in range(y + 1, bottom):
        with context_suppress_curses_error():
            stdscr.addch(row, x, ord("|"))
            stdscr.addch(row, right, ord("|"))
    with context_suppress_curses_error():
        stdscr.addch(y, x, ord("+"))
        stdscr.addch(y, right, ord("+"))
        stdscr.addch(bottom, x, ord("+"))
        stdscr.addch(bottom, right, ord("+"))


def _summarize_result(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("summary", "message", "content", "status"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return _truncate(value.strip(), 180)
    return _truncate(_json_text(result), 180)


def _detail_lines_for_result(result: Any) -> List[str]:
    if isinstance(result, dict):
        if "sessions" in result and isinstance(result["sessions"], list):
            lines = []
            active = str(result.get("activeSessionId", "") or "")
            for session in result["sessions"][:30]:
                if not isinstance(session, dict):
                    continue
                session_id = str(session.get("sessionId", "") or "")
                model = str(session.get("model", "") or "")
                count = session.get("messageCount")
                active_marker = " (active)" if session_id == active else ""
                lines.append(f"{session_id}{active_marker}")
                if model or count is not None:
                    lines.append(f"  model={model or '-'} messages={count if count is not None else '-'}")
            return lines or ["No sessions returned."]
        if "session" in result and isinstance(result["session"], dict):
            result = result["session"]
        lines = []
        for key in sorted(result.keys()):
            value = result[key]
            if isinstance(value, (dict, list)):
                lines.append(f"{key}:")
                for line in json.dumps(value, ensure_ascii=False, indent=2).splitlines():
                    lines.append(f"  {line}")
            else:
                lines.append(f"{key}: {value}")
        return lines or ["No fields returned."]
    if isinstance(result, list):
        return [str(item) for item in result] or ["No items returned."]
    return [str(result)]


def _permission_lines(params: Dict[str, Any]) -> List[str]:
    lines = []
    operation = str(params.get("operation", "") or "")
    message = str(params.get("message", "") or "")
    if operation:
        lines.append(f"Operation: {operation}")
    if message:
        lines.append(message)
    paths = params.get("paths") if isinstance(params.get("paths"), list) else []
    if paths:
        lines.append("Paths:")
        lines.extend(f"- {path}" for path in paths[:8])
    diff = str(params.get("diff", "") or "")
    if diff:
        lines.append("Diff preview:")
        lines.extend(diff.splitlines()[:10])
    return lines or ["No additional detail."]


def _plan_lines(params: Dict[str, Any]) -> List[str]:
    lines = []
    summary = str(params.get("summary", "") or "")
    original = str(params.get("originalRequest", "") or "")
    if summary:
        lines.append(summary)
    if original:
        lines.append(f"Request: {original}")
    steps = params.get("steps") if isinstance(params.get("steps"), list) else []
    if steps:
        lines.append("Steps:")
        for step in steps[:12]:
            lines.append(f"- {_json_text(step)}")
    return lines or ["No plan details supplied."]


def _help_lines() -> List[str]:
    return [
        "Enter: send composer content",
        "Ctrl-V: start or stop voice capture",
        "/voice on: enable continuous in-session voice mode",
        "/voice off: disable continuous voice mode",
        "/voice talk: start or stop capture from the composer",
        "Tab: cycle focus between composer, transcript, and activity",
        "Ctrl-O: open the compact action palette",
        "Up / Down / PgUp / PgDn when transcript or activity is focused: scroll that pane",
        "Esc: cancel voice capture, speech output, or the active request",
        "Ctrl-R: restart backend",
        "Ctrl-S: fetch status view",
        "Ctrl-P: fetch provider info",
        "Backspace / Left / Right / Home / End: edit composer",
        "Ctrl-C: quit the TUI",
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli tui")
    parser.add_argument("--repo-root", help="Working repository root for the backend server")
    parser.add_argument(
        "--python",
        dest="python_executable",
        help="Python executable to launch poor-cli.server",
    )
    parser.add_argument("--provider", help="Initial provider override")
    parser.add_argument("--model", help="Initial model override")
    parser.add_argument("--api-key", help="Initial API key override")
    parser.add_argument(
        "--permission-mode",
        default="default",
        help="Permission mode for this TUI session",
    )
    parser.add_argument(
        "--sandbox-preset",
        default="workspace-write",
        help="Sandbox preset for this TUI session",
    )
    parser.add_argument(
        "--validate-api-key",
        action="store_true",
        help="Validate the configured API key during initialize",
    )
    parser.add_argument(
        "--multiplayer-host",
        action="store_true",
        help="Let this TUI consume and execute prompts from the multiplayer foreground queue",
    )
    return parser


def run_tui(configuration: BackendConfiguration) -> int:
    return CursesTUIApplication(configuration).run()


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configuration = BackendConfiguration.detected(
        repo_root=args.repo_root or "",
        python_executable=args.python_executable or "",
        provider=args.provider or "",
        model=args.model or "",
        api_key=args.api_key or "",
        permission_mode=args.permission_mode,
        sandbox_preset=args.sandbox_preset,
        validate_api_key=bool(args.validate_api_key),
        enable_multiplayer_queue=bool(args.multiplayer_host),
    )
    return run_tui(configuration)
