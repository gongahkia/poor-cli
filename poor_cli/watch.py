"""
Compatibility shim — canonical implementation is in ide_watch.py.

This module re-exports FileWatcher with the async-generator interface
for backward compatibility. New code should import from ide_watch.
"""

from .ide_watch import FileWatcher, scan_directory_for_instructions # noqa: F401
from typing import AsyncIterator, List, Optional


async def run_watch_mode(
    repl,
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
        combined = "\n".join(parts)
        await repl.process_request(combined, request_origin="automation")
