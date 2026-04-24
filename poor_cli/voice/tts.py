"""System speech output for poor-cli voice mode."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import sys
import threading

from .common import VoiceError


@dataclass
class SpeechOutputDiagnostics:
    engine: str
    ready: bool
    blockers: list[str]


class SystemTtsManager:
    def __init__(self, *, engine: str = "auto", voice: str = "", rate: float = 1.0):
        self._engine = (engine or "auto").strip().lower()
        self._voice = voice.strip()
        self._rate = max(0.5, min(2.0, float(rate)))
        self._active_child: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def diagnostics(self) -> SpeechOutputDiagnostics:
        if sys.platform == "darwin":
            ready = shutil.which("say") is not None
            return SpeechOutputDiagnostics(
                engine="say" if self._engine in {"auto", "say"} else self._engine,
                ready=ready and self._engine in {"auto", "say"},
                blockers=[] if ready else ["`say` is required for speech output on macOS."],
            )
        if sys.platform.startswith("linux"):
            spd_ready = shutil.which("spd-say") is not None
            espeak_ready = shutil.which("espeak-ng") is not None
            if self._engine == "spd-say":
                return SpeechOutputDiagnostics(
                    engine="spd-say",
                    ready=spd_ready,
                    blockers=[] if spd_ready else ["`spd-say` is required for this speech engine."],
                )
            if self._engine == "espeak-ng":
                return SpeechOutputDiagnostics(
                    engine="espeak-ng",
                    ready=espeak_ready,
                    blockers=[] if espeak_ready else ["`espeak-ng` is required for this speech engine."],
                )
            ready = spd_ready or espeak_ready
            chosen = "spd-say" if spd_ready else "espeak-ng" if espeak_ready else "unavailable"
            blockers = []
            if not ready:
                blockers.append(
                    "Install `speech-dispatcher` (spd-say) or `espeak-ng` for speech output."
                )
            return SpeechOutputDiagnostics(engine=chosen, ready=ready, blockers=blockers)
        return SpeechOutputDiagnostics(
            engine="unsupported",
            ready=False,
            blockers=["Speech output is not supported on this platform."],
        )

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        command = self._build_command(text)
        with self._lock:
            if self._active_child is not None and self._active_child.poll() is None:
                self._terminate_child(self._active_child)
            try:
                child = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                raise VoiceError(f"Unable to start speech output: {exc}") from exc
            self._active_child = child
        try:
            child.wait()
        finally:
            with self._lock:
                if self._active_child is child:
                    self._active_child = None

    def stop_speaking(self) -> bool:
        with self._lock:
            child = self._active_child
            self._active_child = None
        if child is None:
            return False
        self._terminate_child(child)
        return True

    def _build_command(self, text: str) -> list[str]:
        diagnostics = self.diagnostics()
        if not diagnostics.ready:
            blocker = diagnostics.blockers[0] if diagnostics.blockers else "Speech output is unavailable."
            raise VoiceError(blocker)

        if sys.platform == "darwin":
            command = ["say"]
            if self._voice:
                command.extend(["-v", self._voice])
            command.extend(["-r", str(int(175 * self._rate)), text])
            return command

        if sys.platform.startswith("linux"):
            if diagnostics.engine == "spd-say":
                rate = str(int((self._rate - 1.0) * 100))
                command = ["spd-say", "-r", rate]
                if self._voice:
                    command.extend(["-t", self._voice])
                command.append(text)
                return command
            command = ["espeak-ng", "-s", str(int(175 * self._rate))]
            if self._voice:
                command.extend(["-v", self._voice])
            command.append(text)
            return command

        raise VoiceError("Speech output is not supported on this platform.")

    def _terminate_child(self, child: subprocess.Popen[bytes]) -> None:
        if child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1.0)
