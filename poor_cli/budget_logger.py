"""Budget decision logger (Phase 7A).

Logs (state, action, outcome) tuples to .poor-cli/budget_logs.jsonl
for offline analysis and future bandit/RL training.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .token_budget_controller import (
    TokenBudgetState,
    TokenBudgetAction,
    TurnOutcome,
    compute_reward,
)
from .exceptions import setup_logger

logger = setup_logger(__name__)

_DEFAULT_LOG_FILE = "budget_logs.jsonl"


class BudgetLogger:
    """Append-only JSONL logger for budget decisions."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = base_dir or Path(".poor-cli")
        self._path = self._base / _DEFAULT_LOG_FILE
        self._buffer: list[dict] = []
        self._flush_every = 5

    @property
    def log_path(self) -> Path:
        return self._path

    def log(
        self,
        state: TokenBudgetState,
        action: TokenBudgetAction,
        outcome: TurnOutcome,
    ) -> None:
        """Log a single (state, action, outcome) tuple."""
        reward = compute_reward(state, action, outcome)
        record = {
            "ts": time.time(),
            "state": asdict(state),
            "action": asdict(action),
            "outcome": asdict(outcome),
            "reward": reward,
        }
        self._buffer.append(record)
        if len(self._buffer) >= self._flush_every:
            self.flush()

    def flush(self) -> None:
        """Write buffered records to disk."""
        if not self._buffer:
            return
        try:
            self._base.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                for rec in self._buffer:
                    f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            self._buffer.clear()
        except OSError as e:
            logger.warning("budget_logger flush failed: %s", e)

    def read_all(self) -> list[dict]:
        """Read all logged records (for offline analysis)."""
        if not self._path.exists():
            return []
        records = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def summary(self) -> dict:
        """Return aggregate stats from log file."""
        records = self.read_all()
        if not records:
            return {"total_records": 0}
        rewards = [r.get("reward", 0) for r in records]
        total_tokens = sum(r.get("outcome", {}).get("total_tokens_used", 0) for r in records)
        successes = sum(1 for r in records if r.get("outcome", {}).get("task_succeeded", False))
        tiers: dict[str, int] = {}
        for r in records:
            t = r.get("action", {}).get("model_tier", "unknown")
            tiers[t] = tiers.get(t, 0) + 1
        return {
            "total_records": len(records),
            "avg_reward": round(sum(rewards) / len(rewards), 4),
            "total_tokens": total_tokens,
            "success_rate": round(successes / len(records), 3),
            "tokens_per_success": round(total_tokens / max(successes, 1)),
            "tier_distribution": tiers,
        }

    def close(self) -> None:
        """Flush remaining buffer on shutdown."""
        self.flush()
