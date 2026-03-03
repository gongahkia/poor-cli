"""
Directory watch mode for triggering AI analysis on file changes.
"""

import asyncio
import fnmatch
import os
from typing import AsyncIterator, Dict, List, Optional


class FileWatcher:
    """Polling file watcher with debounce and glob filtering."""

    def __init__(
        self,
        directory: str,
        patterns: Optional[List[str]] = None,
        debounce: float = 2.0,
    ):
        self.directory = os.path.abspath(directory)
        self.patterns = patterns
        self.debounce = debounce

    def _matches(self, file_name: str) -> bool:
        if not self.patterns:
            return True
        return any(fnmatch.fnmatch(file_name, pattern) for pattern in self.patterns)

    def _snapshot(self) -> Dict[str, float]:
        snapshot: Dict[str, float] = {}
        for root, _, files in os.walk(self.directory):
            for name in files:
                if not self._matches(name):
                    continue
                path = os.path.join(root, name)
                try:
                    snapshot[path] = os.stat(path).st_mtime
                except OSError:
                    continue
        return snapshot

    async def watch(self) -> AsyncIterator[List[str]]:
        previous = self._snapshot()
        while True:
            await asyncio.sleep(self.debounce)
            current = self._snapshot()
            changed: List[str] = []

            for path, mtime in current.items():
                if path not in previous or previous[path] != mtime:
                    changed.append(path)

            if changed:
                yield changed

            previous = current


async def run_watch_mode(
    repl,
    directory: str,
    prompt: str,
    patterns: Optional[List[str]] = None,
) -> None:
    """Watch directory and process request whenever files change."""
    watcher = FileWatcher(directory=directory, patterns=patterns)
    async for changed_files in watcher.watch():
        parts: List[str] = ["The following files changed:\n"]
        for file_path in changed_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                parts.append(f"File: {file_path}\n```\n{content}\n```\n")
            except Exception:
                continue

        parts.append(prompt)
        combined = "\n".join(parts)
        await repl.process_request(combined)
