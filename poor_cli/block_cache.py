"""Block-level prompt cache helpers."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from typing import Any, Sequence

ANTHROPIC_CACHE_CONTROL_MAX_BLOCKS = 4


@dataclass
class BlockCacheStats:
    path: str
    hits: int = 0
    misses: int = 0
    tokens: int = 0


@dataclass(frozen=True)
class _Segment:
    text: str
    block_id: str = ""
    path: str = ""
    tokens: int = 0

    @property
    def cacheable(self) -> bool:
        return bool(self.block_id)


class BlockCacheSession:
    def __init__(
        self,
        *,
        rolling_window: int = 64,
        anthropic_max_blocks: int = ANTHROPIC_CACHE_CONTROL_MAX_BLOCKS,
    ) -> None:
        self._file_order: dict[str, int] = {}
        self._stats: dict[str, BlockCacheStats] = {}
        self._rolling: deque[bool] = deque(maxlen=max(1, int(rolling_window)))
        self.anthropic_max_blocks = max(0, int(anthropic_max_blocks))

    def stabilize_files(self, files: Sequence[Any]) -> tuple[Any, ...]:
        for file_ctx in files:
            path = str(getattr(file_ctx, "path", "") or "")
            if path and path not in self._file_order:
                self._file_order[path] = len(self._file_order)
        return tuple(
            sorted(
                files,
                key=lambda file_ctx: self._file_order.get(str(getattr(file_ctx, "path", "") or ""), 10**9),
            )
        )

    def provider_message(
        self,
        message: str,
        files: Sequence[Any],
        *,
        provider_name: str,
        block_capable: bool = True,
    ) -> Any:
        provider = provider_name.strip().lower()
        if provider not in {"anthropic", "openai"} or not block_capable:
            return message
        segments = self._split_message(str(message or ""), self.stabilize_files(files))
        if not any(segment.cacheable for segment in segments):
            return message
        content: list[dict[str, Any]] = []
        marked = 0
        seen_in_payload: set[str] = set()
        for segment in segments:
            block = {"type": "text", "text": segment.text}
            if segment.cacheable:
                can_track = provider == "openai" or marked < self.anthropic_max_blocks
                if can_track and segment.block_id not in seen_in_payload:
                    self._record(segment)
                    seen_in_payload.add(segment.block_id)
                if provider == "anthropic" and marked < self.anthropic_max_blocks:
                    block["cache_control"] = {"type": "ephemeral"}
                    marked += 1
            content.append(block)
        return content

    def get_stats(self) -> dict[str, Any]:
        hits = sum(stat.hits for stat in self._stats.values())
        misses = sum(stat.misses for stat in self._stats.values())
        total = hits + misses
        rolling_total = len(self._rolling)
        rolling_hits = sum(1 for hit in self._rolling if hit)
        return {
            "blocks": len(self._stats),
            "hits": hits,
            "misses": misses,
            "hit_rate_pct": round(hits / total * 100, 1) if total else 0.0,
            "rolling_hit_rate_pct": round(rolling_hits / rolling_total * 100, 1) if rolling_total else 0.0,
            "by_block": [
                {
                    "path": stat.path,
                    "hits": stat.hits,
                    "misses": stat.misses,
                    "tokens": stat.tokens,
                }
                for stat in sorted(self._stats.values(), key=lambda s: self._file_order.get(s.path, 10**9))
            ],
        }

    def _record(self, segment: _Segment) -> None:
        stat = self._stats.setdefault(
            segment.block_id,
            BlockCacheStats(path=segment.path, tokens=max(0, int(segment.tokens))),
        )
        hit = stat.hits + stat.misses > 0
        if hit:
            stat.hits += 1
        else:
            stat.misses += 1
        stat.tokens = max(stat.tokens, int(segment.tokens))
        self._rolling.append(hit)

    def _split_message(self, message: str, files: Sequence[Any]) -> list[_Segment]:
        ranges: list[tuple[int, int, Any]] = []
        used: list[tuple[int, int]] = []
        for file_ctx in files:
            file_range = self._find_file_section(message, file_ctx)
            if file_range is None:
                continue
            start, end = file_range
            if start >= end or any(start < old_end and end > old_start for old_start, old_end in used):
                continue
            ranges.append((start, end, file_ctx))
            used.append((start, end))
        if not ranges:
            return [_Segment(message)]
        ranges.sort(key=lambda item: item[0])
        segments: list[_Segment] = []
        cursor = 0
        for start, end, file_ctx in ranges:
            if start > cursor:
                segments.append(_Segment(message[cursor:start]))
            text = message[start:end]
            path = str(getattr(file_ctx, "path", "") or "")
            block_id = self._block_id(path, text)
            tokens = max(1, len(text) // 4)
            segments.append(_Segment(text=text, block_id=block_id, path=path, tokens=tokens))
            cursor = end
        if cursor < len(message):
            segments.append(_Segment(message[cursor:]))
        return [segment for segment in segments if segment.text]

    def _find_file_section(self, message: str, file_ctx: Any) -> tuple[int, int] | None:
        path = str(getattr(file_ctx, "path", "") or "")
        if not path:
            return None
        for marker in (f"### {path} [", f"### {path}\n", f"--- file: {path}"):
            start = message.find(marker)
            if start >= 0:
                return self._section_bounds(message, start, marker.startswith("### "))
        content = str(getattr(file_ctx, "content", "") or "").strip()
        if len(content) < 8:
            return None
        start = message.find(content)
        if start < 0:
            return None
        return start, start + len(content)

    @staticmethod
    def _section_bounds(message: str, start: int, fenced: bool) -> tuple[int, int]:
        if fenced:
            fence_start = message.find("\n```", start)
            if fence_start >= 0:
                fence_end = message.find("\n```", fence_start + 4)
                if fence_end >= 0:
                    return start, fence_end + 4
        candidates = [
            idx for idx in (
                message.find("\n\n### ", start + 1),
                message.find("\n\n--- file: ", start + 1),
                message.find("\n\nUser request:", start + 1),
            )
            if idx >= 0
        ]
        return start, min(candidates) if candidates else len(message)

    @staticmethod
    def _block_id(path: str, text: str) -> str:
        raw = f"file\x00{path}\x00{text}"
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def enforce_anthropic_cache_control_limit(
    request_params: dict[str, Any],
    *,
    max_blocks: int = ANTHROPIC_CACHE_CONTROL_MAX_BLOCKS,
) -> None:
    blocks: list[dict[str, Any]] = []
    _collect_cache_blocks(request_params.get("system"), blocks)
    _collect_cache_blocks(request_params.get("tools"), blocks)
    _collect_cache_blocks(request_params.get("messages"), blocks)
    overflow = len(blocks) - max(0, int(max_blocks))
    if overflow <= 0:
        return
    for block in blocks[:overflow]:
        block.pop("cache_control", None)


def _collect_cache_blocks(value: Any, blocks: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if "cache_control" in value:
            blocks.append(value)
        for child in value.values():
            _collect_cache_blocks(child, blocks)
    elif isinstance(value, list):
        for child in value:
            _collect_cache_blocks(child, blocks)


def has_cache_control_block(value: Any) -> bool:
    blocks: list[dict[str, Any]] = []
    _collect_cache_blocks(value, blocks)
    return bool(blocks)


def strip_cache_control_annotations(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_cache_control_annotations(child)
            for key, child in value.items()
            if key != "cache_control"
        }
    if isinstance(value, list):
        return [strip_cache_control_annotations(child) for child in value]
    return value
