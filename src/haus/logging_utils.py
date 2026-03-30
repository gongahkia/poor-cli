from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_CONFIGURED = False


def _resolve_log_file() -> Path:
    """Resolve default project log file path.

    Prefers `_HAUS_ROOT` when available (set by `haus view`), then falls
    back to the current working directory.
    """
    root = Path(os.environ.get("_HAUS_ROOT", os.getcwd()))
    return root / "out" / "logs" / "haus.log"


def configure_logging(component: str = "haus") -> logging.Logger:
    """Configure process-level logging once and return a named logger."""
    global _CONFIGURED

    if not _CONFIGURED:
        level_name = os.environ.get("HAUS_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Remove existing handlers so reloading (uvicorn) does not duplicate logs.
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        formatter = logging.Formatter(_DEFAULT_FORMAT)

        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root_logger.addHandler(stream)

        log_file = _resolve_log_file()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        _CONFIGURED = True

    return logging.getLogger(component)


def new_request_id(prefix: str) -> str:
    """Return a compact identifier for tracing one chat/sync operation."""
    return f"{prefix}-{uuid4().hex[:8]}"
