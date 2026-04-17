"""Per-session tool-call recorder.

The dispatcher (``poor_cli.tool_dispatcher``) calls ``recorder.record(rec, args)``
after every tool dispatch when the request ctx has a ``session_recorder``
attribute. The recorder keeps an in-memory ring buffer of the session's
calls, along with a coarse-grained view of which files the tools declared
they touched.

This exists so ``meta.call_history`` and ``meta.what_changed`` (Proposal D)
can introspect session state without the agent having to keep it in chat
context. Two invariants from PROPOSAL-D-DISCOVERY.md §1 apply:

  - **Agent-centric.** The recorder only feeds meta.* tools. There's no
    user command that reads it. If the user wants call history they use
    the audit log.
  - **Token-frugal.** Ring-buffered at 1000 entries so long sessions don't
    accumulate unbounded memory (and, when summarised by meta.call_history,
    never blow the model's context).

Session-scoped. No persistence. Session end = data gone.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Set

from poor_cli.tool_dispatcher import CallRecord


# Tools whose args declare the files they touch. When one of these runs
# successfully, we extract path-like args and add them to
# ``SessionRecorder._file_writes`` so ``meta.what_changed`` can render a
# "what did my tools mutate this session" table.
#
# Keep this list narrow. A tool like ``task.run`` might mutate anything via
# subprocess; we don't guess. Listed tools use declared path args only —
# honest and predictable.
_MUTATING_PATH_ARGS: Dict[str, List[str]] = {
    "git.stage":   ["paths"],
    "git.unstage": ["paths"],
    "git.commit":  [],  # paths come from staged files; we don't know until after
    "hunks.stage": ["file"],
    "hunks.reset": ["file"],
    "fs.write":    ["path"],       # for a future fs.write tool
    "deploy.run":  [],             # side effects unknown
}


@dataclass
class RecordedCall:
    """One tool dispatch. Composed of the dispatcher's CallRecord plus the
    original args (needed by meta.what_changed) and a wall-clock timestamp."""

    rec: CallRecord
    args: Dict[str, Any]
    at: float

    @property
    def tool(self) -> str:
        return self.rec.tool

    @property
    def outcome(self) -> str:
        """Short categorical outcome used by meta.call_history TableBlocks."""
        if self.rec.timeout:
            return "timeout"
        if self.rec.is_error:
            return "err"
        if self.rec.degraded:
            return "degraded"
        return "ok"


@dataclass
class SessionRecorder:
    """One per chat session. Lives on ``ctx.session_recorder`` via the
    server handler. Reads-only from meta.* tools; writes from the dispatcher.
    """

    max_records: int = 1000
    records: Deque[RecordedCall] = field(default_factory=deque)
    started_at: float = field(default_factory=time.time)
    # Paths touched by *declared* mutating tools this session. Best-effort —
    # see ``_MUTATING_PATH_ARGS`` for the whitelist.
    _file_writes: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def record(self, rec: CallRecord, args: Optional[Dict[str, Any]] = None) -> None:
        """Persist one dispatch into the session's ring buffer. Called from
        the dispatcher after each call; safe to invoke from any thread that
        owns the recorder (meta tools run in the same event loop)."""
        args = dict(args or {})
        call = RecordedCall(rec=rec, args=args, at=time.time())
        self.records.append(call)
        # Enforce ring-buffer cap.
        while len(self.records) > self.max_records:
            self.records.popleft()
        # Track files touched by known-mutating tools on success only —
        # errors shouldn't be presented as "changed this" to the agent.
        if not rec.is_error:
            for path in _extract_paths(rec.tool, args):
                entry = self._file_writes.setdefault(
                    path, {"first_touched_by": rec.tool, "touches": 0}
                )
                entry["touches"] += 1

    def recent(self, *, n: int = 20, tool_filter: Optional[str] = None) -> List[RecordedCall]:
        """Return the last N calls (chronological order, oldest→newest among
        the slice). Optional ``tool_filter`` restricts to an exact tool name."""
        if tool_filter:
            out = [c for c in self.records if c.tool == tool_filter]
        else:
            out = list(self.records)
        return out[-max(1, n):]

    def file_writes(self) -> List[Dict[str, Any]]:
        """Return ``[{path, first_touched_by, touches}, ...]`` stable-sorted
        by path. Used by meta.what_changed."""
        rows: List[Dict[str, Any]] = []
        for path in sorted(self._file_writes):
            entry = self._file_writes[path]
            rows.append({
                "path": path,
                "first_touched_by": entry["first_touched_by"],
                "touches": entry["touches"],
            })
        return rows

    def reset(self) -> None:
        """Test hook — forget everything."""
        self.records.clear()
        self._file_writes.clear()
        self.started_at = time.time()


def _extract_paths(tool: str, args: Dict[str, Any]) -> Iterable[str]:
    """Pull path-like strings out of tool args, per the ``_MUTATING_PATH_ARGS``
    whitelist. Yields zero paths for tools not in the whitelist (so
    ``task.run`` etc. contribute nothing)."""
    keys = _MUTATING_PATH_ARGS.get(tool)
    if not keys:
        return
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value:
            yield value
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str) and v:
                    yield v
