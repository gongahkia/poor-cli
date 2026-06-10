import math
import threading
import time

from poor_cli.voice.audio import RecordedAudio
from poor_cli.voice.controller import VoiceController, VoiceSettings
from poor_cli.voice.transcription import TranscriptionResult


class FakeRecorder:
    def __init__(self, audio: RecordedAudio):
        self.audio = audio
        self.started = False
        self.cancelled = False

    def start(self, device_name=None):
        del device_name
        self.started = True

    def stop(self) -> RecordedAudio:
        self.started = False
        return self.audio

    def cancel(self) -> None:
        self.started = False
        self.cancelled = True


class FakeTranscriber:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def transcribe(self, audio: RecordedAudio, *, language: str, translate: bool) -> TranscriptionResult:
        self.calls.append((audio, language, translate))
        return TranscriptionResult(text=self.text, segments=[], duration_ms=42)


class BlockingTts:
    def __init__(self):
        self._release = threading.Event()
        self.stop_called = False
        self.spoken = []

    def diagnostics(self):
        return type("Diag", (), {"ready": True, "engine": "fake-tts", "blockers": []})()

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        self._release.wait(timeout=1.0)

    def stop_speaking(self) -> bool:
        self.stop_called = True
        self._release.set()
        return True


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met before timeout")


def _speech_audio() -> RecordedAudio:
    speech = [
        math.sin(index / 16000.0 * 220.0 * math.tau) * 0.4
        for index in range(9600)
    ]
    return RecordedAudio(samples=speech + ([0.0] * 32000), sample_rate=16000)


def test_voice_controller_transcribes_recording():
    events = []
    recorder = FakeRecorder(_speech_audio())
    transcriber = FakeTranscriber("hello world")
    controller = VoiceController(
        settings=VoiceSettings(enabled=True, language="en", speak_responses=False),
        recorder=recorder,
        transcriber=transcriber,
        tts_manager=None,
        on_event=events.append,
    )

    controller.start_recording()
    time.sleep(0.05)
    controller.finish_recording()

    _wait_for(lambda: any(event["type"] == "voice_transcription" for event in events))
    assert recorder.started is False
    assert transcriber.calls
    assert any(event["type"] == "voice_state" and event["state"] == "recording" for event in events)
    assert any(event["type"] == "voice_state" and event["state"] == "processing" for event in events)
    assert any(
        event["type"] == "voice_transcription" and event["text"] == "hello world"
        for event in events
    )
    _wait_for(lambda: controller.state == "idle")


def test_voice_controller_cancel_recording():
    events = []
    recorder = FakeRecorder(_speech_audio())
    controller = VoiceController(
        settings=VoiceSettings(enabled=True, speak_responses=False),
        recorder=recorder,
        transcriber=FakeTranscriber("unused"),
        tts_manager=None,
        on_event=events.append,
    )

    controller.start_recording()
    assert controller.cancel() is True
    assert recorder.cancelled is True
    assert controller.state == "idle"
    assert any(event["type"] == "voice_state" and event["state"] == "idle" for event in events)


def test_start_recording_interrupts_speaking():
    events = []
    recorder = FakeRecorder(_speech_audio())
    tts = BlockingTts()
    controller = VoiceController(
        settings=VoiceSettings(enabled=True, speak_responses=True),
        recorder=recorder,
        transcriber=FakeTranscriber("unused"),
        tts_manager=tts,
        on_event=events.append,
    )

    assert controller.speak_text("assistant reply") is True
    _wait_for(lambda: controller.state == "speaking")
    controller.start_recording()

    assert tts.stop_called is True
    assert recorder.started is True
    assert controller.state == "recording"


def test_update_settings_changes_conversation_mode_and_speech_limits():
    controller = VoiceController(
        settings=VoiceSettings(enabled=True, speak_responses=True),
        recorder=FakeRecorder(_speech_audio()),
        transcriber=FakeTranscriber("unused"),
        tts_manager=BlockingTts(),
        on_event=None,
    )

    settings = controller.update_settings(
        conversation_mode=True,
        max_spoken_chars=180,
        tts_rate=1.4,
    )

    assert settings.conversation_mode is True
    assert settings.max_spoken_chars == 180
    assert settings.tts_rate == 1.4
    assert controller.get_settings().conversation_mode is True


def test_speak_text_strips_code_blocks_and_truncates():
    tts = BlockingTts()
    controller = VoiceController(
        settings=VoiceSettings(enabled=True, speak_responses=True, max_spoken_chars=120),
        recorder=FakeRecorder(_speech_audio()),
        transcriber=FakeTranscriber("unused"),
        tts_manager=tts,
        on_event=None,
    )

    assert controller.speak_text(
        "Short intro. ```python\nprint('debug')\n``` "
        + ("A" * 300)
    ) is True
    _wait_for(lambda: bool(tts.spoken))
    spoken = tts.spoken[0]
    assert "print('debug')" not in spoken
    assert len(spoken) <= 120
    tts.stop_speaking()
