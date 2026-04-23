"""Tool-output egress accounting helpers."""

from __future__ import annotations

from typing import Dict


def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8", errors="replace")) // 4) if text else 0


def egress_summary(text: str, *, scanned: int = 0) -> Dict[str, int]:
    returned = len(text.encode("utf-8", errors="replace"))
    return {"scannedBytes": max(0, scanned), "returnedBytes": returned, "estimatedTokens": estimate_tokens(text)}


def render_egress_footer(text: str, *, scanned: int = 0) -> str:
    stats = egress_summary(text, scanned=scanned)
    return (
        f"[tool_egress returned_bytes={stats['returnedBytes']} "
        f"est_tokens={stats['estimatedTokens']}]"
    )


def with_egress_footer(text: str, *, scanned: int = 0) -> str:
    return f"{text}\n{render_egress_footer(text, scanned=scanned)}"


def truncate_with_notice(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return text
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text
    clipped = raw[:max_bytes].decode("utf-8", errors="replace")
    return f"{clipped}\n[truncated_to_bytes={max_bytes}]"
