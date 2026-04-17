"""Per-tool circuit breaker state for tool dispatch."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Dict, Optional, Tuple

from poor_cli import tool_health


@dataclass
class _State:
    mode: str = "closed"  # closed|open|half_open
    opened_at_mono: float = 0.0
    probe_in_flight: bool = False


class ToolCircuit:
    def __init__(self) -> None:
        self._states: Dict[str, _State] = {}
        self._lock = threading.Lock()

    def pre_dispatch(self, tool: str, spec: Any) -> Tuple[bool, Dict[str, object]]:
        now = time.monotonic()
        with self._lock:
            state = self._states.setdefault(tool, _State())
            if state.mode == "open":
                elapsed = now - state.opened_at_mono
                if elapsed >= spec.circuit_cooldown_s:
                    state.mode = "half_open"
                    state.probe_in_flight = False
                else:
                    return False, {
                        "circuit_open": True,
                        "circuit_state": "open",
                        "retry_after_s": max(0.0, spec.circuit_cooldown_s - elapsed),
                    }

            if state.mode == "half_open":
                if state.probe_in_flight:
                    return False, {
                        "circuit_open": True,
                        "circuit_state": "half_open",
                        "retry_after_s": max(0.0, spec.circuit_cooldown_s - (now - state.opened_at_mono)),
                    }
                state.probe_in_flight = True
                return True, {"circuit_state": "half_open", "circuit_probe": True}

            failures = tool_health.recent_consecutive_failures(tool, window_s=spec.circuit_window_s)
            if failures >= spec.circuit_threshold:
                state.mode = "open"
                state.opened_at_mono = now
                state.probe_in_flight = False
                return False, {
                    "circuit_open": True,
                    "circuit_state": "open",
                    "retry_after_s": spec.circuit_cooldown_s,
                }
            return True, {"circuit_state": "closed"}

    def post_dispatch(self, tool: str, spec: Any, *, success: bool) -> None:
        now = time.monotonic()
        with self._lock:
            state = self._states.setdefault(tool, _State())
            if state.mode == "half_open":
                state.probe_in_flight = False
                if success:
                    state.mode = "closed"
                    state.opened_at_mono = 0.0
                    return
                state.mode = "open"
                state.opened_at_mono = now
                return
            if state.mode == "closed" and not success:
                failures = tool_health.recent_consecutive_failures(tool, window_s=spec.circuit_window_s)
                if failures >= spec.circuit_threshold:
                    state.mode = "open"
                    state.opened_at_mono = now
                    state.probe_in_flight = False
                    return
            if state.mode == "open" and success:
                state.mode = "closed"
                state.opened_at_mono = 0.0
                state.probe_in_flight = False

    def state(self, tool: str, spec: Any) -> Dict[str, object]:
        now = time.monotonic()
        with self._lock:
            state = self._states.setdefault(tool, _State())
            if state.mode == "open":
                elapsed = now - state.opened_at_mono
                retry_after = max(0.0, spec.circuit_cooldown_s - elapsed)
                if retry_after <= 0:
                    return {
                        "state": "half_open",
                        "open": False,
                        "retry_after_s": 0.0,
                    }
                return {
                    "state": "open",
                    "open": True,
                    "retry_after_s": retry_after,
                }
            return {"state": state.mode, "open": False, "retry_after_s": 0.0}


def get_circuit(ctx: object, *, create: bool = False) -> Optional[ToolCircuit]:
    circuit = getattr(ctx, "tool_circuit", None)
    if isinstance(circuit, ToolCircuit):
        return circuit
    if not create:
        return None
    circuit = ToolCircuit()
    setattr(ctx, "tool_circuit", circuit)
    return circuit
