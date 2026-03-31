"""
Voice input support for poor-cli.

Provides speech-to-text via multiple backends:
1. macOS system dictation (subprocess to say/dictation API)
2. Whisper via Ollama (local, cross-platform)

The TUI triggers recording, this module handles transcription.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


class VoiceInputManager:
    """Manages voice recording and transcription."""

    def __init__(self):
        self._backend = _detect_backend()
        self._recording = False

    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def backend_name(self) -> str:
        return self._backend or "none"

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "backend": self.backend_name,
            "recording": self._recording,
        }

    async def record_and_transcribe(self, duration: float = 10.0) -> str:
        """Record audio and return transcribed text."""
        if not self.available:
            return "error: no voice backend available"

        self._recording = True
        try:
            if self._backend == "sox":
                return await _transcribe_with_sox(duration)
            elif self._backend == "arecord":
                return await _transcribe_with_arecord(duration)
            return "error: unsupported backend"
        finally:
            self._recording = False

    async def transcribe_file(self, audio_path: str) -> str:
        """Transcribe an existing audio file."""
        if not Path(audio_path).exists():
            return f"error: file not found: {audio_path}"
        if shutil.which("whisper"):
            return await _run_whisper_cli(audio_path)
        return "error: whisper CLI not available for file transcription"


def _detect_backend() -> Optional[str]:
    """Detect available audio recording + transcription backend."""
    has_whisper = shutil.which("whisper") is not None
    if shutil.which("sox") and shutil.which("rec") and has_whisper:
        return "sox"
    if sys.platform == "linux" and shutil.which("arecord") and has_whisper:
        return "arecord"
    # macOS: try sox even without whisper (will fail at transcription step)
    if shutil.which("sox") and shutil.which("rec"):
        return "sox"
    return None


async def _record_audio(cmd: list[str], duration: float, output_path: str) -> bool:
    """Record audio using given command."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=duration + 5)
        return Path(output_path).exists() and Path(output_path).stat().st_size > 0
    except asyncio.TimeoutError:
        if proc.returncode is None:
            proc.terminate()
        return Path(output_path).exists()
    except Exception as exc:
        logger.error("recording failed: %s", exc)
        return False


async def _transcribe_with_sox(duration: float) -> str:
    """Record with SoX and transcribe with Whisper CLI if available."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        cmd = ["rec", "-q", wav_path, "trim", "0", str(duration)]
        ok = await _record_audio(cmd, duration, wav_path)
        if not ok:
            return "error: recording failed"
        if shutil.which("whisper"):
            return await _run_whisper_cli(wav_path)
        return "error: whisper CLI not found for transcription"
    finally:
        Path(wav_path).unlink(missing_ok=True)


async def _transcribe_with_arecord(duration: float) -> str:
    """Record with ALSA arecord and transcribe."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        cmd = ["arecord", "-q", "-f", "cd", "-d", str(int(duration)), wav_path]
        ok = await _record_audio(cmd, duration, wav_path)
        if not ok:
            return "error: recording failed"
        if shutil.which("whisper"):
            return await _run_whisper_cli(wav_path)
        return "error: whisper CLI not found for transcription"
    finally:
        Path(wav_path).unlink(missing_ok=True)


async def _run_whisper_cli(audio_path: str) -> str:
    """Run OpenAI Whisper CLI for transcription."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "whisper", audio_path, "--model", "base", "--output_format", "txt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        # whisper outputs to .txt file next to audio
        txt_path = Path(audio_path).with_suffix(".txt")
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8").strip()
            txt_path.unlink(missing_ok=True)
            return text
        return stdout.decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        return "error: whisper transcription timed out"
    except Exception as exc:
        return f"error: whisper failed: {exc}"
