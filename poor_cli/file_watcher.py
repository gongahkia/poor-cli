"""
File watcher for poor-cli.

Monitors source files for inline instruction comments (# poor-cli: ...)
and exposes callback and async-generator consumption over one event queue.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import fnmatch
import inspect
import os
import re
import time
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Deque, Dict, List, Optional, Set

from .exceptions import setup_logger

logger = setup_logger(__name__)

COMMENT_PATTERNS = [
    re.compile(r'#\s*poor-cli:\s*(.+)$', re.MULTILINE),
    re.compile(r'//\s*poor-cli:\s*(.+)$', re.MULTILINE),
    re.compile(r'--\s*poor-cli:\s*(.+)$', re.MULTILINE),
    re.compile(r'/\*\s*poor-cli:\s*(.+?)\s*\*/', re.MULTILINE),
]

DEFAULT_DEBOUNCE_SECONDS = 2.0
DEFAULT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".c", ".cpp", ".rb", ".php"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".poor-cli", ".venv", "target", "build", "dist"}
RULE_FILE_NAMES = {"AGENTS.md", "CLAUDE.md"}
_WATCHER_REGISTRY: weakref.WeakSet[Any] = weakref.WeakSet()
_RECENT_ACTIONS: Deque[Dict[str, Any]] = deque(maxlen=100)


@dataclass(frozen=True)
class FileEvent:
    paths: tuple[str, ...]

    @property
    def path(self) -> str:
        return self.paths[0] if self.paths else ""


def scan_file_for_instructions(file_path: str) -> List[Dict[str, Any]]:
    """Scan a file for poor-cli inline instruction comments."""
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    instructions = []
    for pattern in COMMENT_PATTERNS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            instructions.append({
                "file": file_path,
                "line": line_num,
                "instruction": match.group(1).strip(),
                "full_match": match.group(0).strip(),
            })
    return instructions


def scan_directory_for_instructions(
    root: Optional[str] = None,
    extensions: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Scan all files in a directory for poor-cli instructions."""
    root_path = Path(root or os.getcwd()).resolve()
    exts = extensions or DEFAULT_EXTENSIONS
    all_instructions = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in exts:
                all_instructions.extend(scan_file_for_instructions(str(fpath)))

    return all_instructions


def _iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def collect_watch_status(root: Optional[str | Path] = None, action_limit: int = 20) -> Dict[str, Any]:
    requested_root = Path(root).resolve() if root is not None else None
    watchers = [
        watcher for watcher in list(_WATCHER_REGISTRY)
        if (watcher._running or watcher._mtimes) and (requested_root is None or watcher._root == requested_root)
    ]
    if not watchers:
        watchers = [FileWatcher(root=root or os.getcwd(), register=False)]
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for watcher in watchers:
        for row in watcher.status_rows():
            key = f"{row.get('path')}:{row.get('ignored')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    limit = max(0, int(action_limit or 20))
    actions = list(_RECENT_ACTIONS)[-limit:] if limit else []
    return {"watches": rows, "recent_actions": actions}


class FileWatcher:
    """Watches files for changes and triggers callbacks on poor-cli instructions."""

    def __init__(
        self,
        root: Optional[str | Path] = None,
        extensions: Optional[Set[str]] = None,
        patterns: Optional[List[str]] = None,
        debounce: float = DEFAULT_DEBOUNCE_SECONDS,
        debounce_ms: Optional[int] = None,
        ignore: Optional[List[str]] = None,
        on_change: Optional[Callable[[FileEvent], Any]] = None,
        on_instruction: Optional[Callable[[dict], Any]] = None,
        on_execute: Optional[Callable[[dict], Any]] = None,
        register: bool = True,
    ):
        self._root = Path(root or os.getcwd()).resolve()
        self._extensions = extensions or DEFAULT_EXTENSIONS
        self._patterns = patterns
        self._debounce = debounce if debounce_ms is None else debounce_ms / 1000
        self._ignore = self._load_ignore_patterns(ignore)
        self._on_instruction = on_instruction
        self._on_execute = on_execute
        self._change_callbacks: List[Callable[[FileEvent], Any]] = []
        if on_change is not None:
            self._change_callbacks.append(on_change)
        self._running = False
        self._mtimes: Dict[str, float] = {}
        self._last_change_at: Dict[str, str] = {}
        self._processed: Set[str] = set()
        self._events: asyncio.Queue[FileEvent] = asyncio.Queue()
        self._subscribers: Set[asyncio.Queue[FileEvent | None]] = set()
        self._run_task: Optional[asyncio.Task[None]] = None
        if register:
            _WATCHER_REGISTRY.add(self)

    def on_change(self, callback: Callable[[FileEvent], Any]) -> None:
        self._change_callbacks.append(callback)

    async def start(self) -> None:
        """Start watching for file changes."""
        self._ensure_started()
        if self._run_task is not None:
            await self._run_task

    def stop(self) -> None:
        was_running = self._running
        self._running = False
        if was_running:
            for queue in list(self._subscribers):
                queue.put_nowait(None)

    async def __aiter__(self) -> AsyncIterator[FileEvent]:
        queue: asyncio.Queue[FileEvent | None] = asyncio.Queue()
        self._subscribers.add(queue)
        self._ensure_started()
        try:
            while self._running:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self._subscribers.discard(queue)
            if not self._subscribers and not self._change_callbacks:
                self.stop()

    async def watch_changes(self) -> AsyncIterator[List[str]]:
        """Async generator yielding lists of changed file paths."""
        async for event in self:
            yield list(event.paths)

    def _ensure_started(self) -> None:
        if self._run_task is not None and not self._run_task.done():
            return
        self._running = True
        logger.info("watching %s for poor-cli instructions", self._root)
        self._snapshot_mtimes()
        self._run_task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        try:
            while self._running:
                changed = self._detect_changes()
                if changed:
                    await self._events.put(FileEvent(tuple(changed)))
                await self._dispatch_pending_events()
                if self._running:
                    await asyncio.sleep(self._debounce)
        finally:
            self._running = False
            await self._dispatch_pending_events()

    async def _dispatch_pending_events(self) -> None:
        while not self._events.empty():
            event = await self._events.get()
            for queue in list(self._subscribers):
                queue.put_nowait(event)
            for callback in list(self._change_callbacks):
                await self._call_maybe_async(callback, event)
            await self._handle_instruction_event(event)

    async def _handle_instruction_event(self, event: FileEvent) -> None:
        for file_path in event.paths:
            for instr in scan_file_for_instructions(file_path):
                key = f"{instr['file']}:{instr['line']}:{instr['instruction']}"
                if key in self._processed:
                    continue
                self._processed.add(key)
                logger.info("found instruction in %s:%d: %s", instr["file"], instr["line"], instr["instruction"])
                try:
                    from .audit_log import AuditEventType, get_audit_logger
                    get_audit_logger().log_event(
                        AuditEventType.TOOL_EXECUTION,
                        operation="ide_watch:instruction_found",
                        target=instr["file"],
                        details={"line": instr["line"], "instruction": instr["instruction"]},
                    )
                except Exception:
                    pass
                if self._on_instruction:
                    outcome, duration_ms = await self._call_maybe_async(self._on_instruction, instr)
                    self._record_action(instr, "instruction", outcome, duration_ms)
                if self._on_execute:
                    outcome, duration_ms = await self._call_maybe_async(self._on_execute, instr)
                    self._record_action(instr, "execute", outcome, duration_ms)

    async def _call_maybe_async(self, callback: Callable[[Any], Any], arg: Any) -> tuple[str, int]:
        started = time.perf_counter()
        try:
            result = callback(arg)
            if inspect.isawaitable(result):
                await result
            return "ok", int((time.perf_counter() - started) * 1000)
        except Exception as exc:
            logger.error("watch handler failed: %s", exc)
            return f"error: {exc}", int((time.perf_counter() - started) * 1000)

    def _record_action(self, instr: dict, action: str, outcome: str, duration_ms: int) -> None:
        _RECENT_ACTIONS.append({
            "at": _now_iso(),
            "trigger_path": str(instr.get("file") or ""),
            "action": action,
            "outcome": outcome,
            "duration_ms": duration_ms,
        })

    def _matches_file(self, fname: str) -> bool:
        """Check if a filename matches configured patterns or extensions."""
        if Path(fname).name in RULE_FILE_NAMES:
            return True
        if self._patterns:
            return any(fnmatch.fnmatch(fname, p) for p in self._patterns)
        return Path(fname).suffix.lower() in self._extensions

    def _snapshot_mtimes(self) -> None:
        for fpath in self._iter_matching_files():
            try:
                self._mtimes[str(fpath)] = fpath.stat().st_mtime
            except OSError:
                pass

    def _detect_changes(self) -> List[str]:
        changed = []
        for fpath in self._iter_matching_files():
            fp = str(fpath)
            try:
                mtime = fpath.stat().st_mtime
            except OSError:
                continue
            if fp not in self._mtimes or self._mtimes[fp] < mtime:
                self._mtimes[fp] = mtime
                self._last_change_at[fp] = _iso_from_timestamp(mtime)
                changed.append(fp)
        return changed

    def _iter_matching_files(self, include_ignored: bool = False) -> list[Path]:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            if include_ignored:
                dirnames[:] = [d for d in dirnames if (Path(dirpath) / d).name not in SKIP_DIRS]
            else:
                dirnames[:] = [d for d in dirnames if not self._skip_dir(Path(dirpath) / d)]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if self._matches_file(fname) and (include_ignored or not self._is_ignored(fpath)):
                    files.append(fpath)
        return files

    def _skip_dir(self, path: Path) -> bool:
        return path.name in SKIP_DIRS or self._is_ignored(path)

    def _load_ignore_patterns(self, ignore: Optional[List[str]]) -> list[str]:
        patterns = list(ignore or [])
        gitignore = self._root / ".gitignore"
        try:
            patterns.extend(
                line.strip()
                for line in gitignore.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        except OSError:
            pass
        return patterns

    def _is_ignored(self, path: Path) -> bool:
        return self._ignore_match(path) != ""

    def _ignore_match(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self._root).as_posix()
        except ValueError:
            return ""
        for pattern in self._ignore:
            if self._matches_ignore_pattern(rel, path.name, pattern):
                return pattern
        return ""

    def _matches_ignore_pattern(self, rel: str, name: str, pattern: str) -> bool:
        pattern = pattern.rstrip()
        if not pattern or pattern.startswith("!"):
            return False
        if pattern.endswith("/"):
            prefix = pattern.rstrip("/")
            return rel == prefix or rel.startswith(f"{prefix}/")
        if "/" in pattern:
            return fnmatch.fnmatch(rel, pattern)
        return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, f"*/{pattern}")

    def status_rows(self) -> List[Dict[str, Any]]:
        glob = ",".join(self._patterns or sorted(self._extensions))
        rows: List[Dict[str, Any]] = []
        for fpath in self._iter_matching_files(include_ignored=True):
            fp = str(fpath.resolve())
            ignored_by = self._ignore_match(fpath)
            try:
                last_change_at = self._last_change_at.get(fp) or _iso_from_timestamp(fpath.stat().st_mtime)
            except OSError:
                last_change_at = self._last_change_at.get(fp, "")
            rows.append({
                "path": fp,
                "glob": glob,
                "last_change_at": last_change_at,
                "last_match": ignored_by,
                "ignored": bool(ignored_by),
            })
        return rows


async def run_watch_mode(
    repl: Any,
    directory: str,
    prompt: str,
    patterns: Optional[List[str]] = None,
) -> None:
    """Watch directory and process request whenever files change."""
    watcher = FileWatcher(root=directory, patterns=patterns)
    async for changed_files in watcher.watch_changes():
        parts: List[str] = ["The following files changed:\n"]
        for file_path in changed_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                parts.append(f"File: {file_path}\n```\n{content}\n```\n")
            except Exception:
                continue
        parts.append(prompt)
        await repl.process_request("\n".join(parts), request_origin="automation")
