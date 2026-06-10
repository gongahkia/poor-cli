"""Session-scoped blob store for truncated tool results (Proposal E.2).

When a tool returns more than ``max_result_tokens`` worth of content, the
dispatcher stashes the full blocks here under a fresh ``result_id`` and
returns a middle-out-truncated copy to the model. A follow-up
``tool_blob.get({result_id})`` call retrieves the full content verbatim.

Philosophical bearings (PROPOSAL-E §1):

- **Agent-centric.** The agent sees exactly what size it can handle; the
  handle (result_id) is explicit in ``metadata.result_id`` so the agent
  decides when it's worth spending tokens on the rest.
- **Token-frugal.** A 50k-token diff never touches the model context
  unless the agent explicitly fetches it. Default truncation budget is
  ~8k tokens; the rest sits in-process.
- **Correctness over savings.** The agent is told exactly how much was
  trimmed (``metadata.original_token_estimate``) and gets the head + tail
  of the content — enough to reason about overall shape. Nothing is
  silently dropped.

Ring-buffered by total byte size so long sessions don't leak memory. Per
session, in-process only; no disk, no network. Session end = blobs gone.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional

from poor_cli.tool_blocks import ContentBlock


@dataclass
class _BlobEntry:
    result_id: str
    content: List[ContentBlock]
    size_bytes: int
    created_at: float
    original_token_estimate: int


class SessionBlobStore:
    """Per-session blob ring. Ordered so oldest entries evict first when the
    total byte cap is exceeded."""

    def __init__(self, *, cap_bytes: int = 4 * 1024 * 1024) -> None:
        self._entries: "OrderedDict[str, _BlobEntry]" = OrderedDict()
        self._cap_bytes = max(1024, cap_bytes)
        self._total_bytes = 0
        self._lock = threading.Lock()

    def put(self, content: List[ContentBlock], *, original_token_estimate: int) -> str:
        """Stash full content under a fresh ``result_id``. Evicts oldest
        blobs until total stays under cap_bytes."""
        size = _blocks_bytes(content)
        result_id = "blob_" + uuid.uuid4().hex[:12]
        entry = _BlobEntry(
            result_id=result_id,
            content=list(content),
            size_bytes=size,
            created_at=time.time(),
            original_token_estimate=original_token_estimate,
        )
        with self._lock:
            self._entries[result_id] = entry
            self._total_bytes += size
            while self._total_bytes > self._cap_bytes and self._entries:
                # Pop oldest
                old_id, old = self._entries.popitem(last=False)
                self._total_bytes -= old.size_bytes
        return result_id

    def get(self, result_id: str) -> Optional[_BlobEntry]:
        with self._lock:
            return self._entries.get(result_id)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "total_bytes": self._total_bytes,
                "cap_bytes": self._cap_bytes,
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0


def _blocks_bytes(content: List[ContentBlock]) -> int:
    """Rough UTF-8 byte estimate. We don't care about exact accounting — we
    care about bounding total memory within an order of magnitude."""
    total = 0
    for block in content:
        if hasattr(block, "to_dict"):
            try:
                for value in block.to_dict().values():
                    if isinstance(value, str):
                        total += len(value.encode("utf-8"))
                    elif isinstance(value, (list, tuple)):
                        for v in value:
                            if isinstance(v, str):
                                total += len(v.encode("utf-8"))
            except Exception:
                total += 256  # pessimistic
        else:
            total += len(str(block).encode("utf-8"))
    return max(1, total)
