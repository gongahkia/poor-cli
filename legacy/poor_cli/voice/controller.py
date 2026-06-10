"""Voice-mode controller translated from Wimpr for poor-cli."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import os
import re
import threading
import time
from typing import Callable, Optional

from .audio import (
    SoundDeviceRecorder,
    apply_vad_stop_heuristics,
    sounddevice_runtime_status,
)
from .common import VoiceError
from .transcription import (
    FasterWhisperTranscriber,
    TranscriptionResult,
    faster_whisper_runtime_status,
)
from .tts import SystemTtsManager


@dataclass
class VoiceSettings:
    enabled: bool = True
    conversation_mode: bool = False
    language: str = "auto"
    translate: bool = False
    speak_responses: bool = True
    max_spoken_chars: int = 600
    auto_rearm_delay_ms: int = 400
    input_device: str = ""
    input_sample_rate: int = 0
    model_name: str = "base"
    model_device: str = "auto"
    compute_type: str = "auto"
    download_root: str = ""
    tts_engine: str = "auto"
    tts_voice: str = ""
    tts_rate: float = 1.0

    @classmethod
    def from_mapping(
        cls,
        mapping: dict,
        *,
        base: Optional["VoiceSettings"] = None,
    ) -> "VoiceSettings":
        settings = replace(base) if base is not None else cls()
        for key in asdict(settings).keys():
            if key in mapping:
                setattr(settings, key, mapping[key])
        settings.language = str(settings.language or "auto")
        settings.input_device = str(settings.input_device or "")
        settings.model_name = str(settings.model_name or "base")
        settings.model_device = str(settings.model_device or "auto")
        settings.compute_type = str(settings.compute_type or "auto")
        settings.download_root = str(settings.download_root or "")
        settings.tts_engine = str(settings.tts_engine or "auto")
        settings.tts_voice = str(settings.tts_voice or "")
        settings.max_spoken_chars = max(120, int(settings.max_spoken_chars))
        settings.auto_rearm_delay_ms = max(0, int(settings.auto_rearm_delay_ms))
        settings.tts_rate = max(0.5, min(2.0, float(settings.tts_rate)))
        settings.input_sample_rate = max(0, int(settings.input_sample_rate))
        return settings

    @classmethod
    def from_env(cls, base: Optional["VoiceSettings"] = None) -> "VoiceSettings":
        settings = replace(base) if base is not None else cls()
        env_bool = _env_optional_bool
        env_int = _env_optional_int
        env_float = _env_optional_float
        env_str = _env_optional_str

        if (value := env_bool("POOR_CLI_VOICE_ENABLED")) is not None:
            settings.enabled = value
        if (value := env_bool("POOR_CLI_VOICE_MODE")) is not None:
            settings.conversation_mode = value
        if (value := env_str("POOR_CLI_VOICE_LANGUAGE")) is not None:
            settings.language = value
        if (value := env_bool("POOR_CLI_VOICE_TRANSLATE")) is not None:
            settings.translate = value
        if (value := env_bool("POOR_CLI_VOICE_SPEAK_RESPONSES")) is not None:
            settings.speak_responses = value
        if (value := env_int("POOR_CLI_VOICE_MAX_SPOKEN_CHARS")) is not None:
            settings.max_spoken_chars = value
        if (value := env_int("POOR_CLI_VOICE_AUTO_REARM_DELAY_MS")) is not None:
            settings.auto_rearm_delay_ms = value
        if (value := env_str("POOR_CLI_VOICE_INPUT_DEVICE")) is not None:
            settings.input_device = value
        if (value := env_int("POOR_CLI_VOICE_INPUT_SAMPLE_RATE")) is not None:
            settings.input_sample_rate = value
        if (value := env_str("POOR_CLI_VOICE_MODEL")) is not None:
            settings.model_name = value
        if (value := env_str("POOR_CLI_VOICE_MODEL_DEVICE")) is not None:
            settings.model_device = value
        if (value := env_str("POOR_CLI_VOICE_COMPUTE_TYPE")) is not None:
            settings.compute_type = value
        if (value := env_str("POOR_CLI_VOICE_DOWNLOAD_ROOT")) is not None:
            settings.download_root = value
        if (value := env_str("POOR_CLI_VOICE_TTS_ENGINE")) is not None:
            settings.tts_engine = value
        if (value := env_str("POOR_CLI_VOICE_TTS_VOICE")) is not None:
            settings.tts_voice = value
        if (value := env_float("POOR_CLI_VOICE_TTS_RATE")) is not None:
            settings.tts_rate = value
        return cls.from_mapping({}, base=settings)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VoiceDiagnostics:
    ready: bool
    state: str
    blockers: list[str] = field(default_factory=list)
    model_name: str = ""
    language: str = "auto"
    speak_responses: bool = False
    tts_ready: bool = False
    tts_engine: str = "auto"

    def summary(self) -> str:
        if self.ready:
            if self.speak_responses and self.tts_ready:
                return f"voice ready ({self.model_name}, speech output on)"
            if self.speak_responses and not self.tts_ready:
                return f"voice ready ({self.model_name}, speech output unavailable)"
            return f"voice ready ({self.model_name})"
        if self.blockers:
            return self.blockers[0]
        return "voice unavailable"

    def as_lines(self) -> list[str]:
        lines = [
            f"Ready: {'yes' if self.ready else 'no'}",
            f"State: {self.state}",
            f"Model: {self.model_name or '-'}",
            f"Language: {self.language}",
            f"Speak responses: {'yes' if self.speak_responses else 'no'}",
            f"TTS ready: {'yes' if self.tts_ready else 'no'}",
            f"TTS engine: {self.tts_engine}",
        ]
        if self.blockers:
            lines.append("Blockers:")
            lines.extend(f"- {item}" for item in self.blockers)
        return lines


class VoiceController:
    def __init__(
        self,
        *,
        settings: VoiceSettings,
        recorder,
        transcriber,
        tts_manager: Optional[SystemTtsManager],
        blockers: Optional[list[str]] = None,
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        self._settings = settings
        self._recorder = recorder
        self._transcriber = transcriber
        self._tts_manager = tts_manager
        self._blockers = list(blockers or [])
        self._on_event = on_event
        self._state = "idle" if not self._blockers else "unavailable"
        self._lock = threading.Lock()
        self._last_action = 0.0
        self._processing_generation = 0
        self._speech_generation = 0

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def diagnostics(self) -> VoiceDiagnostics:
        tts_ready = False
        tts_engine = "disabled"
        if self._tts_manager is not None:
            tts = self._tts_manager.diagnostics()
            tts_ready = tts.ready
            tts_engine = tts.engine
        return VoiceDiagnostics(
            ready=self._is_ready(),
            state=self.state,
            blockers=list(self._blockers),
            model_name=self._settings.model_name,
            language=self._settings.language,
            speak_responses=self._settings.speak_responses,
            tts_ready=tts_ready,
            tts_engine=tts_engine,
        )

    def get_settings(self) -> VoiceSettings:
        with self._lock:
            return replace(self._settings)

    def update_settings(self, **changes) -> VoiceSettings:
        next_settings = VoiceSettings.from_mapping(changes, base=self.get_settings())
        if self.state in {"recording", "processing", "speaking"}:
            self.cancel()
        recorder, transcriber, tts_manager, blockers = _build_runtime(next_settings)
        with self._lock:
            self._settings = next_settings
            self._recorder = recorder
            self._transcriber = transcriber
            self._tts_manager = tts_manager
            self._blockers = blockers
            self._state = "unavailable" if blockers else "idle"
        diagnostics = self.diagnostics()
        self._emit(
            "voice_settings",
            settings=next_settings.to_dict(),
            summary=diagnostics.summary(),
        )
        self._emit("voice_state", state=diagnostics.state, detail=diagnostics.summary())
        return next_settings

    def toggle_recording(self) -> None:
        current = self.state
        if current == "recording":
            self.finish_recording()
            return
        if current == "processing":
            raise VoiceError("Voice is still transcribing. Cancel first.")
        self.start_recording()

    def start_recording(self) -> None:
        if self._debounced():
            return
        current = self.state
        if current == "speaking":
            self.stop_speaking()
        elif current not in {"idle", "unavailable"}:
            return

        self._ensure_ready()
        self._recorder.start(self._settings.input_device or None)
        self._set_state("recording", detail="listening")

    def finish_recording(self) -> None:
        if self._debounced():
            return
        if self.state != "recording":
            return
        audio = apply_vad_stop_heuristics(self._recorder.stop())
        generation = self._next_processing_generation()
        self._set_state("processing", detail="transcribing")
        threading.Thread(
            target=self._transcription_worker,
            args=(generation, audio),
            name="poor-cli-voice-transcribe",
            daemon=True,
        ).start()

    def cancel(self) -> bool:
        current = self.state
        if current == "recording":
            self._recorder.cancel()
            self._set_state("idle", detail="cancelled")
            return True
        if current == "processing":
            self._next_processing_generation()
            self._set_state("idle", detail="cancelled")
            return True
        if current == "speaking":
            return self.stop_speaking()
        return False

    def speak_text(self, text: str) -> bool:
        if not self._settings.speak_responses or self._tts_manager is None:
            return False
        speech_text = self._speech_text_for_response(text)
        if not speech_text:
            return False
        diagnostics = self._tts_manager.diagnostics()
        if not diagnostics.ready:
            self._emit(
                "voice_error",
                message=diagnostics.blockers[0] if diagnostics.blockers else "Speech output unavailable.",
            )
            return False

        generation = self._next_speech_generation()
        self._set_state("speaking", detail="speaking")
        threading.Thread(
            target=self._speech_worker,
            args=(generation, speech_text),
            name="poor-cli-voice-speak",
            daemon=True,
        ).start()
        return True

    def stop_speaking(self) -> bool:
        if self._tts_manager is None:
            return False
        stopped = self._tts_manager.stop_speaking()
        self._next_speech_generation()
        self._set_state("idle", detail="speech stopped")
        return stopped

    def _transcription_worker(self, generation: int, audio) -> None:
        if not audio.samples:
            if generation == self._processing_generation:
                self._emit("voice_empty")
                self._set_state("idle")
            return
        try:
            result: TranscriptionResult = self._transcriber.transcribe(
                audio,
                language=self._settings.language,
                translate=self._settings.translate,
            )
        except Exception as exc:
            if generation == self._processing_generation:
                self._emit("voice_error", message=str(exc))
                self._set_state("idle")
            return

        if generation != self._processing_generation:
            return
        if not result.text.strip():
            self._emit("voice_empty")
            self._set_state("idle")
            return
        self._emit(
            "voice_transcription",
            text=result.text,
            duration_ms=result.duration_ms,
        )
        self._set_state("idle")

    def _speech_worker(self, generation: int, text: str) -> None:
        assert self._tts_manager is not None
        try:
            self._tts_manager.speak(text)
        except Exception as exc:
            if generation == self._speech_generation:
                self._emit("voice_error", message=str(exc))
                self._set_state("idle")
            return
        if generation == self._speech_generation:
            self._set_state("idle")

    def _ensure_ready(self) -> None:
        if not self._is_ready():
            raise VoiceError(self.diagnostics().summary())

    def _is_ready(self) -> bool:
        return self._settings.enabled and self._recorder is not None and self._transcriber is not None

    def _emit(self, event_type: str, **payload) -> None:
        if self._on_event is None:
            return
        self._on_event({"type": event_type, **payload})

    def _set_state(self, state: str, *, detail: str = "") -> None:
        with self._lock:
            self._state = state
        self._emit("voice_state", state=state, detail=detail)

    def _debounced(self) -> bool:
        with self._lock:
            now = time.monotonic()
            if now - self._last_action < 0.03:
                return True
            self._last_action = now
            return False

    def _next_processing_generation(self) -> int:
        with self._lock:
            self._processing_generation += 1
            return self._processing_generation

    def _next_speech_generation(self) -> int:
        with self._lock:
            self._speech_generation += 1
            return self._speech_generation

    def _speech_text_for_response(self, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        normalized = _strip_code_blocks(normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return ""
        limit = max(120, int(self._settings.max_spoken_chars))
        if len(normalized) <= limit:
            return normalized
        truncated = normalized[:limit]
        for marker in (". ", "! ", "? ", "; ", ": "):
            idx = truncated.rfind(marker)
            if idx >= limit // 2:
                return truncated[: idx + 1].strip()
        return truncated.rstrip()


def _env_optional_str(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip()


def _env_optional_bool(name: str) -> Optional[bool]:
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _env_optional_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _env_optional_float(name: str) -> Optional[float]:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _strip_code_blocks(text: str) -> str:
    parts = text.split("```")
    if len(parts) == 1:
        return text
    kept = [part for index, part in enumerate(parts) if index % 2 == 0]
    return " ".join(kept)


def _build_runtime(settings: VoiceSettings):
    blockers: list[str] = []
    recorder = None
    transcriber = None

    if not settings.enabled:
        blockers.append("Voice is disabled.")
    else:
        recorder_ready, recorder_message = sounddevice_runtime_status()
        if recorder_ready:
            recorder = SoundDeviceRecorder(
                requested_sample_rate=settings.input_sample_rate,
                device_name=settings.input_device,
            )
        else:
            blockers.append(recorder_message)

        transcriber_ready, transcriber_message = faster_whisper_runtime_status()
        if transcriber_ready:
            transcriber = FasterWhisperTranscriber(
                model_name=settings.model_name,
                device=settings.model_device,
                compute_type=settings.compute_type,
                download_root=settings.download_root,
            )
        else:
            blockers.append(transcriber_message)

    tts_manager = SystemTtsManager(
        engine=settings.tts_engine,
        voice=settings.tts_voice,
        rate=settings.tts_rate,
    )
    return recorder, transcriber, tts_manager, blockers


def build_voice_controller(
    settings: VoiceSettings,
    *,
    on_event: Optional[Callable[[dict], None]] = None,
) -> VoiceController:
    recorder, transcriber, tts_manager, blockers = _build_runtime(settings)
    return VoiceController(
        settings=settings,
        recorder=recorder,
        transcriber=transcriber,
        tts_manager=tts_manager,
        blockers=blockers,
        on_event=on_event,
    )


def build_default_voice_controller(
    repo_root: str = "",
    on_event: Optional[Callable[[dict], None]] = None,
) -> VoiceController:
    from .preferences import VoicePreferencesStore

    stored = VoicePreferencesStore(repo_root).load()
    settings = VoiceSettings.from_env(base=stored)
    return build_voice_controller(settings, on_event=on_event)
