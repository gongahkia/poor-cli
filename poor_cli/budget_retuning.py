"""CB5 offline weekly budget retuning.

Wraps ``ThinkingBudgetOptimizer.analyze()`` with a persist step that writes
the resulting profile to ``.poor-cli/budget_tunings/<YYYY-MM-DD>.json``. The
running server can then hot-load the latest tuning without a restart via
``load_latest_tuning()``.

Intended to run as an AutomationRule on a cron (``0 3 * * 1`` = Monday 03:00).
The job is idempotent — running twice on the same day overwrites the day's
file rather than creating duplicates.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .exceptions import setup_logger
from .thinking_budget import ThinkingBudgetOptimizer, ThinkingBudgetProfile

logger = setup_logger(__name__)

TUNING_DIR_NAME = "budget_tunings"


def tuning_dir(base: Optional[Path] = None) -> Path:
    return (base or Path.cwd() / ".poor-cli") / TUNING_DIR_NAME


def tuning_path_for_date(date: datetime, base: Optional[Path] = None) -> Path:
    return tuning_dir(base) / f"{date.strftime('%Y-%m-%d')}.json"


def _serialize_profile(profile: ThinkingBudgetProfile) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records_analyzed": profile.total_records_analyzed,
        "estimated_savings_pct": profile.estimated_savings_pct,
        "budgets": dict(profile.budgets),
        "stats": {k: asdict(v) for k, v in profile.stats.items()},
    }


def run_retuning(base: Optional[Path] = None) -> Dict[str, Any]:
    """Run the optimizer and persist the resulting profile for today.

    Returns a summary dict including the written path + savings estimate.
    Safe to call from an AutomationRule cron trigger.
    """
    base_dir = base or Path.cwd() / ".poor-cli"
    out_dir = tuning_dir(base)
    out_dir.mkdir(parents=True, exist_ok=True)
    optimizer = ThinkingBudgetOptimizer(log_dir=base_dir)
    profile = optimizer.analyze()
    payload = _serialize_profile(profile)
    today = datetime.now(timezone.utc)
    out_path = tuning_path_for_date(today, base)
    # atomic write
    try:
        fd, tmp = tempfile.mkstemp(dir=str(out_dir), suffix=".json.tmp")
        try:
            os.write(fd, json.dumps(payload, indent=2).encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, str(out_path))
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    except Exception as exc:
        logger.warning("budget_retuning: failed to persist tuning: %s", exc)
        return {"status": "error", "error": str(exc), "profile": payload}
    logger.info("budget_retuning: wrote %s (records=%d, savings=%.1f%%)",
                out_path, profile.total_records_analyzed, profile.estimated_savings_pct)
    return {
        "status": "ok",
        "path": str(out_path),
        "records": profile.total_records_analyzed,
        "savings_pct": profile.estimated_savings_pct,
        "budgets": dict(profile.budgets),
    }


def list_tunings(base: Optional[Path] = None) -> list[Path]:
    """Return all tuning files on disk, newest first."""
    dir_ = tuning_dir(base)
    if not dir_.is_dir():
        return []
    files = sorted(dir_.glob("*.json"))
    return list(reversed(files))


def load_latest_tuning(base: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load the most recent tuning file without running a new analyze."""
    files = list_tunings(base)
    if not files:
        return None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("failed to load tuning %s: %s", files[0], exc)
    return None


def apply_tuning_to_optimizer(
    optimizer: ThinkingBudgetOptimizer,
    tuning_payload: Dict[str, Any],
) -> bool:
    """Hot-load a tuning payload into an existing optimizer instance.

    Overrides the optimizer's internal profile so subsequent ``get_budget``
    calls use the retuned values. Returns True on success.
    """
    budgets = tuning_payload.get("budgets")
    if not isinstance(budgets, dict):
        return False
    from .thinking_budget import ThinkingBudgetProfile
    profile = ThinkingBudgetProfile(
        budgets=dict(budgets),
        total_records_analyzed=int(tuning_payload.get("total_records_analyzed", 0) or 0),
        estimated_savings_pct=float(tuning_payload.get("estimated_savings_pct", 0.0) or 0.0),
    )
    optimizer._profile = profile  # type: ignore[reportPrivateUsage]
    return True
