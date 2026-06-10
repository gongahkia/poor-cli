"""Latent-step auto-tuning.

The original LatentAgent uses a fixed ``latent_steps`` value (default 20).
That's wrong on both ends: trivial tasks waste steps, complex tasks under-think.
This module learns a per-task-type recommendation from a rolling reward log,
mirroring the thinking-budget retuning approach from CB5.

Storage: ``.poor-cli/latent_step_logs.jsonl`` — append-only, one record per
architect→editor latent hand-off:

```json
{"task_type": "moderate", "latent_steps": 20, "reward": 0.7, "ts": "2026-04-14T03:00Z"}
```

The optimizer aggregates by task_type and recommends the latent-step count
that maximizes the rolling-window mean reward, clamped to safety bounds.

This is a research-grade module — the production loop calls
``recommend_steps`` to pick a value at the start of each architect turn, and
calls ``record(task_type, steps, reward)`` at the end so the next turn learns.
"""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..exceptions import setup_logger

logger = setup_logger(__name__)

LOG_FILENAME = "latent_step_logs.jsonl"

DEFAULT_STEPS = {
    "trivial": 4,
    "simple": 10,
    "moderate": 20,
    "complex": 40,
}

STEP_BOUNDS = {
    "trivial": (1, 8),
    "simple": (4, 16),
    "moderate": (8, 32),
    "complex": (16, 80),
}

CANDIDATE_STEP_GRID = {
    "trivial": (1, 2, 4, 6, 8),
    "simple": (4, 6, 8, 10, 12, 14, 16),
    "moderate": (8, 12, 16, 20, 24, 28, 32),
    "complex": (16, 24, 32, 40, 48, 56, 64, 80),
}

ROLLING_WINDOW = 100  # max records considered per task type
MIN_SAMPLES_FOR_TUNING = 5  # below this, fall back to default


@dataclass
class LatentStepRecord:
    task_type: str
    latent_steps: int
    reward: float
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "latent_steps": int(self.latent_steps),
            "reward": float(self.reward),
            "ts": self.timestamp,
        }


@dataclass
class TuningReport:
    task_type: str
    samples: int
    recommended_steps: int
    mean_reward: float
    fell_back_to_default: bool


class LatentStepAutotuner:
    """Append-only log + recommendation engine for latent step counts."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = Path(base_dir) if base_dir else Path.cwd() / ".poor-cli"
        self._path = self._base / LOG_FILENAME
        self._lock = threading.Lock()

    def record(self, task_type: str, latent_steps: int, reward: float) -> None:
        """Append a single observation to the log. Crash-safe append."""
        record = LatentStepRecord(
            task_type=str(task_type or "moderate").lower(),
            latent_steps=max(1, int(latent_steps)),
            reward=float(reward),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        try:
            self._base.mkdir(parents=True, exist_ok=True)
            with self._lock:
                # atomic append using O_APPEND
                fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                try:
                    os.write(fd, (json.dumps(record.to_dict()) + "\n").encode("utf-8"))
                finally:
                    os.close(fd)
        except Exception as exc:
            logger.debug("latent autotune record failed: %s", exc)

    def recommend_steps(self, task_type: str) -> TuningReport:
        """Return tuned step count for a task type with a usability report."""
        normalized = (task_type or "moderate").strip().lower()
        if normalized not in DEFAULT_STEPS:
            normalized = "moderate"
        records = self._read_logs(task_type=normalized)
        if len(records) < MIN_SAMPLES_FOR_TUNING:
            return TuningReport(
                task_type=normalized,
                samples=len(records),
                recommended_steps=DEFAULT_STEPS[normalized],
                mean_reward=0.0,
                fell_back_to_default=True,
            )
        # group by step count, pick the one with highest mean reward
        by_steps: Dict[int, List[float]] = defaultdict(list)
        for r in records[-ROLLING_WINDOW:]:
            by_steps[r.latent_steps].append(r.reward)
        candidates = []
        for steps, rewards in by_steps.items():
            if len(rewards) < 2:
                continue
            mean = sum(rewards) / len(rewards)
            candidates.append((mean, steps))
        if not candidates:
            return TuningReport(
                task_type=normalized,
                samples=len(records),
                recommended_steps=DEFAULT_STEPS[normalized],
                mean_reward=0.0,
                fell_back_to_default=True,
            )
        candidates.sort(reverse=True)
        best_mean, best_steps = candidates[0]
        lo, hi = STEP_BOUNDS[normalized]
        clamped = max(lo, min(hi, best_steps))
        return TuningReport(
            task_type=normalized,
            samples=len(records),
            recommended_steps=clamped,
            mean_reward=round(best_mean, 4),
            fell_back_to_default=False,
        )

    def explore_grid(self, task_type: str) -> List[int]:
        """Return candidate step counts to round-robin through during exploration.

        Caller is responsible for the bandit policy (epsilon-greedy etc.); this
        just exposes the search space for a given task type.
        """
        normalized = (task_type or "moderate").strip().lower()
        if normalized not in CANDIDATE_STEP_GRID:
            normalized = "moderate"
        return list(CANDIDATE_STEP_GRID[normalized])

    def _read_logs(self, *, task_type: Optional[str] = None) -> List[LatentStepRecord]:
        if not self._path.is_file():
            return []
        records: List[LatentStepRecord] = []
        try:
            with self._path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if task_type and str(data.get("task_type", "")).lower() != task_type:
                        continue
                    records.append(LatentStepRecord(
                        task_type=str(data.get("task_type", "")),
                        latent_steps=int(data.get("latent_steps", 0) or 0),
                        reward=float(data.get("reward", 0.0) or 0.0),
                        timestamp=str(data.get("ts", "")),
                    ))
        except Exception as exc:
            logger.warning("failed to read latent step logs: %s", exc)
            return []
        return records


_default_autotuner: Optional[LatentStepAutotuner] = None
_default_autotuner_lock = threading.Lock()


def get_default_autotuner(base_dir: Optional[Path] = None) -> LatentStepAutotuner:
    """Process-wide singleton; tests use their own instances."""
    global _default_autotuner
    if _default_autotuner is not None:
        return _default_autotuner
    with _default_autotuner_lock:
        if _default_autotuner is None:
            _default_autotuner = LatentStepAutotuner(base_dir)
    return _default_autotuner


def reset_default_autotuner() -> None:
    """Tests only."""
    global _default_autotuner
    with _default_autotuner_lock:
        _default_autotuner = None
