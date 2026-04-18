#!/usr/bin/env python3
"""Bench helper: stdio process that intentionally stalls on TERM."""

from __future__ import annotations

import signal
import time


_STALL_SECONDS = 1.5


def _on_term(_signum: int, _frame) -> None:
    time.sleep(_STALL_SECONDS)


def main() -> int:
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
