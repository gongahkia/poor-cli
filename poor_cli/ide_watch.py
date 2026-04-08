"""
IDE watch mode for poor-cli.

Monitors source files for inline instruction comments (# poor-cli: ...)
and triggers the agent when files are saved. Works with any editor.

Usage:
    poor-cli watch [--pattern "*.py"] [--debounce 2]

Comment syntax:
    # poor-cli: add error handling to this function
    // poor-cli: refactor this block
    -- poor-cli: add indexes for this query
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .exceptions import setup_logger

logger = setup_logger(__name__)

# patterns to detect poor-cli inline instructions
COMMENT_PATTERNS = [
    re.compile(r'#\s*poor-cli:\s*(.+)$', re.MULTILINE),
    re.compile(r'//\s*poor-cli:\s*(.+)$', re.MULTILINE),
    re.compile(r'--\s*poor-cli:\s*(.+)$', re.MULTILINE),
    re.compile(r'/\*\s*poor-cli:\s*(.+?)\s*\*/', re.MULTILINE),
]

DEFAULT_DEBOUNCE_SECONDS = 2.0
DEFAULT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".c", ".cpp", ".rb", ".php"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".poor-cli", ".venv", "target", "build", "dist"}


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


class FileWatcher:
    """Watches files for changes and triggers callbacks on poor-cli instructions.

    This is the canonical file watcher for poor-cli. Supports two interfaces:
    1. Callback-based: pass on_instruction/on_execute to start()
    2. Async-generator: use watch_changes() for generic file-change iteration
    """

    def __init__(
        self,
        root: Optional[str] = None,
        extensions: Optional[Set[str]] = None,
        patterns: Optional[List[str]] = None,
        debounce: float = DEFAULT_DEBOUNCE_SECONDS,
        on_instruction: Optional[Callable] = None,
        on_execute: Optional[Callable] = None,
    ):
        self._root = Path(root or os.getcwd()).resolve()
        self._extensions = extensions or DEFAULT_EXTENSIONS
        self._patterns = patterns # glob patterns (overrides extensions if set)
        self._debounce = debounce
        self._on_instruction = on_instruction
        self._on_execute = on_execute
        self._running = False
        self._mtimes: Dict[str, float] = {}
        self._processed: Set[str] = set() # instruction hashes already handled

    async def start(self) -> None:
        """Start watching for file changes."""
        self._running = True
        logger.info("watching %s for poor-cli instructions", self._root)
        self._snapshot_mtimes()

        while self._running:
            changed = self._detect_changes()
            for file_path in changed:
                instructions = scan_file_for_instructions(file_path)
                for instr in instructions:
                    key = f"{instr['file']}:{instr['line']}:{instr['instruction']}"
                    if key in self._processed:
                        continue
                    self._processed.add(key)
                    logger.info("found instruction in %s:%d: %s",
                                instr["file"], instr["line"], instr["instruction"])
                    try: # audit log
                        from .audit_log import get_audit_logger, AuditEventType
                        get_audit_logger().log_event(AuditEventType.TOOL_EXECUTION, operation="ide_watch:instruction_found", target=instr["file"], details={"line": instr["line"], "instruction": instr["instruction"]})
                    except Exception:
                        pass
                    if self._on_instruction:
                        try:
                            await self._on_instruction(instr)
                        except Exception as exc:
                            logger.error("instruction handler failed: %s", exc)
                    if self._on_execute:
                        try:
                            await self._on_execute(instr)
                        except Exception as exc:
                            logger.error("execute handler failed: %s", exc)
            await asyncio.sleep(self._debounce)

    def stop(self) -> None:
        self._running = False

    def _matches_file(self, fname: str) -> bool:
        """Check if a filename matches configured patterns or extensions."""
        if self._patterns:
            import fnmatch
            return any(fnmatch.fnmatch(fname, p) for p in self._patterns)
        return Path(fname).suffix.lower() in self._extensions

    async def watch_changes(self) -> "AsyncIterator[List[str]]":
        """Async generator yielding lists of changed file paths (generic interface)."""
        from typing import AsyncIterator
        self._snapshot_mtimes()
        while True:
            await asyncio.sleep(self._debounce)
            changed = self._detect_changes()
            if changed:
                yield changed

    def _snapshot_mtimes(self) -> None:
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                if not self._matches_file(fname):
                    continue
                fpath = Path(dirpath) / fname
                try:
                    self._mtimes[str(fpath)] = fpath.stat().st_mtime
                except OSError:
                    pass

    def _detect_changes(self) -> List[str]:
        changed = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                if not self._matches_file(fname):
                    continue
                fpath = Path(dirpath) / fname
                fp = str(fpath)
                try:
                    mtime = fpath.stat().st_mtime
                except OSError:
                    continue
                if fp not in self._mtimes or self._mtimes[fp] < mtime:
                    self._mtimes[fp] = mtime
                    changed.append(fp)
        return changed
