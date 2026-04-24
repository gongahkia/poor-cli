"""Local transcription adapters for poor-cli voice mode."""

from __future__ import annotations

from dataclasses import dataclass
import os
import tempfile
import threading
import time

from .audio import RecordedAudio, resample_audio, write_wav
from .common import VoiceError


HALLUCINATION_PATTERNS = {
    "[blank_audio]",
    "(silence)",
    "thank you for watching",
    "thanks for watching",
    "thank you for listening",
    "subtitles by",
    "subscribe",
    "[music]",
    "(music)",
}
MIN_AUDIO_SAMPLES_16K = 8000


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]
    duration_ms: int


def faster_whisper_runtime_status() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return (
            False,
            "Install poor-cli[voice] to enable local transcription (missing faster-whisper).",
        )
    return True, ""


def _normalize_language(language: str) -> str | None:
    normalized = (language or "auto").strip()
    if not normalized or normalized == "auto":
        return None
    if normalized in {"zh-Hans", "zh-Hant"}:
        return "zh"
    return normalized


def _filter_hallucinations(text: str) -> str:
    trimmed = text.strip()
    if trimmed.lower() in HALLUCINATION_PATTERNS:
        return ""
    return trimmed


class FasterWhisperTranscriber:
    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        compute_type: str,
        download_root: str = "",
    ):
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._download_root = download_root.strip()
        self._model = None
        self._lock = threading.Lock()

    def transcribe(
        self,
        audio: RecordedAudio,
        *,
        language: str,
        translate: bool,
    ) -> TranscriptionResult:
        samples_16k = resample_audio(audio.samples, audio.sample_rate, 16000)
        if len(samples_16k) < MIN_AUDIO_SAMPLES_16K:
            return TranscriptionResult(text="", segments=[], duration_ms=0)

        fd, tmp_path = tempfile.mkstemp(prefix="poor-cli-voice-", suffix=".wav")
        os.close(fd)
        try:
            write_wav(tmp_path, samples_16k, 16000)
            start = time.monotonic()
            model = self._ensure_model()
            segments_iter, _info = model.transcribe(
                tmp_path,
                language=_normalize_language(language),
                task="translate" if translate else "transcribe",
                beam_size=1,
                best_of=1,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            text_parts: list[str] = []
            segments: list[Segment] = []
            for segment in segments_iter:
                text = str(getattr(segment, "text", "") or "").strip()
                if not text:
                    continue
                text_parts.append(text)
                start_sec = float(getattr(segment, "start", 0.0) or 0.0)
                end_sec = float(getattr(segment, "end", 0.0) or 0.0)
                segments.append(
                    Segment(
                        start_ms=int(start_sec * 1000.0),
                        end_ms=int(end_sec * 1000.0),
                        text=text,
                    )
                )
            text = _filter_hallucinations(" ".join(text_parts))
            return TranscriptionResult(
                text=text,
                segments=segments,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"Transcription failed: {exc}") from exc
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _ensure_model(self):
        with self._lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise VoiceError(
                        "Install poor-cli[voice] to enable local transcription (missing faster-whisper)."
                    ) from exc
                kwargs = {}
                if self._download_root:
                    kwargs["download_root"] = self._download_root
                try:
                    self._model = WhisperModel(
                        self._model_name,
                        device=self._device,
                        compute_type=self._compute_type,
                        **kwargs,
                    )
                except Exception as exc:
                    raise VoiceError(f"Unable to load Whisper model `{self._model_name}`: {exc}") from exc
            return self._model
