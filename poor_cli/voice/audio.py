"""Audio capture and VAD stop heuristics translated from Wimpr."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import threading
import wave
from typing import Optional

from .common import VoiceError


DEFAULT_VAD_SPEECH_THRESHOLD = 0.01
DEFAULT_VAD_SILENCE_DURATION_MS = 1500
DEFAULT_VAD_SPEECH_PADDING_MS = 150
VAD_FRAME_MS = 30


@dataclass
class RecordedAudio:
    samples: list[float]
    sample_rate: int


class VadResult(str, Enum):
    SPEECH = "speech"
    SILENCE = "silence"
    SILENCE_TIMEOUT = "silence_timeout"


class VoiceActivityDetector:
    def __init__(self, speech_threshold: float, silence_duration_ms: int):
        self.speech_threshold = float(speech_threshold)
        self.silence_duration_ms = max(0, int(silence_duration_ms))
        self.consecutive_silence_ms = 0

    def process_frame(self, frame: list[float], sample_rate: int) -> VadResult:
        if not frame or sample_rate <= 0:
            rms = 0.0
            frame_duration_ms = 0
        else:
            rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
            frame_duration_ms = int(len(frame) / sample_rate * 1000.0)

        if rms > self.speech_threshold:
            self.consecutive_silence_ms = 0
            return VadResult.SPEECH

        self.consecutive_silence_ms += frame_duration_ms
        if self.consecutive_silence_ms >= self.silence_duration_ms:
            return VadResult.SILENCE_TIMEOUT
        return VadResult.SILENCE

    def reset(self) -> None:
        self.consecutive_silence_ms = 0


def apply_vad_stop_heuristics(audio: RecordedAudio) -> RecordedAudio:
    return apply_vad_stop_heuristics_with_config(
        audio,
        speech_threshold=DEFAULT_VAD_SPEECH_THRESHOLD,
        silence_duration_ms=DEFAULT_VAD_SILENCE_DURATION_MS,
        speech_padding_ms=DEFAULT_VAD_SPEECH_PADDING_MS,
    )


def apply_vad_stop_heuristics_with_config(
    audio: RecordedAudio,
    speech_threshold: float,
    silence_duration_ms: int,
    speech_padding_ms: int,
) -> RecordedAudio:
    if not audio.samples or audio.sample_rate <= 0:
        return audio

    detector = VoiceActivityDetector(speech_threshold, silence_duration_ms)
    frame_size = max(1, (audio.sample_rate * VAD_FRAME_MS) // 1000)
    speech_padding_samples = max(0, (audio.sample_rate * speech_padding_ms) // 1000)

    last_speech_end = 0
    frame_start = 0
    while frame_start < len(audio.samples):
        frame_end = min(len(audio.samples), frame_start + frame_size)
        frame = audio.samples[frame_start:frame_end]
        result = detector.process_frame(frame, audio.sample_rate)
        if result == VadResult.SPEECH:
            last_speech_end = frame_end
        elif result == VadResult.SILENCE_TIMEOUT and last_speech_end > 0:
            break
        frame_start = frame_end

    if last_speech_end == 0:
        return RecordedAudio(samples=[], sample_rate=audio.sample_rate)

    cutoff = min(len(audio.samples), last_speech_end + speech_padding_samples)
    return RecordedAudio(samples=audio.samples[:cutoff], sample_rate=audio.sample_rate)


def resample_audio(
    samples: list[float],
    sample_rate: int,
    target_sample_rate: int = 16000,
) -> list[float]:
    if sample_rate <= 0 or target_sample_rate <= 0 or not samples:
        return list(samples)
    if sample_rate == target_sample_rate or len(samples) == 1:
        return list(samples)

    ratio = target_sample_rate / sample_rate
    output_length = max(1, int(round(len(samples) * ratio)))
    output: list[float] = []
    for index in range(output_length):
        source_position = index / ratio
        left = int(math.floor(source_position))
        right = min(left + 1, len(samples) - 1)
        fraction = source_position - left
        left_value = samples[left]
        right_value = samples[right]
        output.append(left_value + (right_value - left_value) * fraction)
    return output


def write_wav(path: str, samples: list[float], sample_rate: int) -> None:
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for sample in samples:
            clamped = max(-1.0, min(1.0, float(sample)))
            pcm = int(clamped * 32767.0)
            frames.extend(int(pcm).to_bytes(2, byteorder="little", signed=True))
        handle.writeframes(bytes(frames))


def sounddevice_runtime_status() -> tuple[bool, str]:
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return (
            False,
            "Install poor-cli[voice] to enable microphone capture (missing sounddevice).",
        )
    return True, ""


def _require_sounddevice():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceError(
            "Install poor-cli[voice] to enable microphone capture (missing sounddevice)."
        ) from exc
    return sd


class SoundDeviceRecorder:
    def __init__(self, requested_sample_rate: int = 0, device_name: str = ""):
        self._requested_sample_rate = max(0, int(requested_sample_rate))
        self._preferred_device_name = device_name.strip()
        self._stream = None
        self._samples: list[float] = []
        self._sample_rate = 16000
        self._recording = False
        self._lock = threading.Lock()

    def is_recording(self) -> bool:
        return self._recording

    def start(self, device_name: Optional[str] = None) -> None:
        if self._recording:
            return

        sd = _require_sounddevice()
        chosen_device = (device_name or self._preferred_device_name or "").strip() or None
        try:
            info = sd.query_devices(device=chosen_device, kind="input")
        except Exception as exc:
            raise VoiceError(f"Unable to open input device: {exc}") from exc

        actual_rate = self._requested_sample_rate or int(
            float(info.get("default_samplerate") or 16000)
        )
        channels = max(1, min(int(info.get("max_input_channels") or 1), 2))

        with self._lock:
            self._samples.clear()

        def callback(indata, frames, time_info, status) -> None:
            del frames, time_info
            if status:
                return
            if not self._recording:
                return
            try:
                if getattr(indata, "ndim", 1) > 1:
                    mono = indata.mean(axis=1).tolist()
                else:
                    mono = indata.tolist()
            except Exception:
                mono = [float(sample) for sample in indata]
            with self._lock:
                self._samples.extend(float(sample) for sample in mono)

        try:
            self._stream = sd.InputStream(
                samplerate=actual_rate,
                device=chosen_device,
                channels=channels,
                dtype="float32",
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise VoiceError(f"Unable to start recording: {exc}") from exc

        self._sample_rate = actual_rate
        self._recording = True

    def stop(self) -> RecordedAudio:
        samples = self._snapshot_and_close(discard=False)
        return RecordedAudio(samples=samples, sample_rate=self._sample_rate)

    def cancel(self) -> None:
        self._snapshot_and_close(discard=True)

    def _snapshot_and_close(self, *, discard: bool) -> list[float]:
        stream = self._stream
        self._stream = None
        self._recording = False
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

        with self._lock:
            snapshot = list(self._samples)
            self._samples.clear()
        if discard:
            return []
        return snapshot
