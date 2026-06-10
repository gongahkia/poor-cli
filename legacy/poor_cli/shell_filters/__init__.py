from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

Filter = Callable[[str], str]
CommandPattern = Tuple[str, ...]
REGISTRY: Dict[CommandPattern, Filter] = {}
_SHELL_OPERATORS = frozenset({"&&", "||", ";", "|", "(", ")", "&", "\n", "\r"})
_DEFAULT_TINY_OUTPUT_BYTES = 300


@dataclass(frozen=True)
class ShellFilterResult:
    output: str
    raw_output: str
    applied: bool = False
    filter_name: str = ""
    original_size: int = 0
    filtered_size: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    reduction_pct: float = 0.0
    reason: str = ""


def register(command_pattern: Iterable[str]) -> Callable[[Filter], Filter]:
    pattern = tuple(str(part) for part in command_pattern)

    def decorator(func: Filter) -> Filter:
        REGISTRY[pattern] = func
        return func

    return decorator


def parse_command_argv(command: str) -> Optional[Tuple[str, ...]]:
    stripped = str(command or "").strip()
    if not stripped:
        return None
    try:
        parts = tuple(shlex.split(stripped, posix=True))
    except ValueError:
        return None
    if not parts or any(part in _SHELL_OPERATORS for part in parts):
        return None
    return (Path(parts[0]).name, *parts[1:])


def match_command(command: str) -> Optional[CommandPattern]:
    argv = parse_command_argv(command)
    if argv is None:
        return None
    matches = [pattern for pattern in REGISTRY if len(argv) >= len(pattern) and argv[: len(pattern)] == pattern]
    return max(matches, key=len) if matches else None


def apply(command: str, output: str, config: object = None) -> ShellFilterResult:
    raw = str(output)
    original_size = len(raw.encode("utf-8"))
    if not _enabled(config):
        return _passthrough(raw, original_size, "disabled")
    if original_size <= _tiny_output_bytes(config):
        return _passthrough(raw, original_size, "tiny")
    pattern = match_command(command)
    if pattern is None:
        return _passthrough(raw, original_size, "no_match")
    filter_func = REGISTRY.get(pattern)
    if filter_func is None:
        return _passthrough(raw, original_size, "no_filter")
    try:
        filtered = filter_func(raw)
    except Exception as exc:
        logger.warning("shell filter failed for %s: %s", " ".join(pattern), exc)
        return _passthrough(raw, original_size, "error")
    if not filtered or filtered == raw:
        return _passthrough(raw, original_size, "unchanged")
    filtered_size = len(filtered.encode("utf-8"))
    if filtered_size >= original_size:
        return _passthrough(raw, original_size, "not_smaller")
    before = _estimate_tokens(raw)
    after = _estimate_tokens(filtered)
    saved = max(0, before - after)
    reduction = round((1 - (filtered_size / max(1, original_size))) * 100, 1)
    return ShellFilterResult(
        output=filtered,
        raw_output=raw,
        applied=True,
        filter_name=" ".join(pattern),
        original_size=original_size,
        filtered_size=filtered_size,
        tokens_before=before,
        tokens_after=after,
        tokens_saved=saved,
        reduction_pct=reduction,
    )


def _passthrough(raw: str, original_size: int, reason: str) -> ShellFilterResult:
    tokens = _estimate_tokens(raw)
    return ShellFilterResult(
        output=raw,
        raw_output=raw,
        original_size=original_size,
        filtered_size=original_size,
        tokens_before=tokens,
        tokens_after=tokens,
        reason=reason,
    )


def _enabled(config: object = None) -> bool:
    cfg = getattr(config, "rtk_lite", None) if config is not None else None
    enabled = getattr(cfg, "enabled", True)
    return bool(enabled)


def _tiny_output_bytes(config: object = None) -> int:
    cfg = getattr(config, "rtk_lite", None) if config is not None else None
    raw = getattr(cfg, "tiny_output_bytes", _DEFAULT_TINY_OUTPUT_BYTES)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_TINY_OUTPUT_BYTES


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4) if text else 0


from . import cargo, git, ls, npm  # noqa: E402,F401
