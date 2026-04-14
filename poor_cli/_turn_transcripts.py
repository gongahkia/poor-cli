"""Transcript + pruning-sidecar I/O for TurnLifecycle.

Extracted from core_turn_lifecycle.py to keep that file under its line-budget cap.
All functions accept the TurnLifecycle instance as first argument.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


def save_transcript(core, history: List[Dict[str, Any]]) -> Optional[str]:
    """Save raw history to disk before compaction. Returns transcript path or None."""
    if not core.config or not getattr(core.config.context_compression, "preserve_transcripts", True):
        return None
    transcript_dir = Path.cwd() / getattr(core.config.context_compression, "transcript_dir", ".poor-cli/transcripts")
    try:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        session_id = getattr(core, "_last_run_id", None) or uuid.uuid4().hex[:12]
        ts = time.strftime("%Y%m%dT%H%M%S")
        dest = transcript_dir / f"{session_id}_{ts}.json"
        fd, tmp = tempfile.mkstemp(dir=str(transcript_dir), suffix=".tmp")
        try:
            os.write(fd, json.dumps(history, indent=None, default=str).encode())
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, str(dest))
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        logger.info("Saved pre-compaction transcript: %s (%d messages)", dest, len(history))
        return str(dest)
    except Exception as exc:
        logger.warning("Failed to save transcript: %s", exc)
        return None


def save_pruning_sidecar(core, pruned_turns: List[Dict[str, Any]]) -> Optional[str]:
    """Save pruned turns for later recovery."""
    if not pruned_turns:
        return None
    transcript_root = ".poor-cli/transcripts"
    if core.config and getattr(core.config, "context_compression", None):
        transcript_root = getattr(core.config.context_compression, "transcript_dir", transcript_root)
    sidecar_dir = Path.cwd() / transcript_root / "pruned"
    try:
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        session_id = getattr(core, "_last_run_id", None) or hashlib.sha1(str(time.time()).encode()).hexdigest()[:12]
        ts = time.strftime("%Y%m%dT%H%M%S")
        dest = sidecar_dir / f"{session_id}_{ts}_pruned.json"
        payload = {"runId": getattr(core, "_last_run_id", None), "createdAt": ts, "turns": pruned_turns}
        fd, tmp = tempfile.mkstemp(dir=str(sidecar_dir), suffix=".tmp")
        try:
            os.write(fd, json.dumps(payload, indent=None, default=str).encode())
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, str(dest))
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        logger.info("Saved pruning sidecar: %s (%d turns)", dest, len(pruned_turns))
        return str(dest)
    except Exception as exc:
        logger.warning("Failed to save pruning sidecar: %s", exc)
        return None
