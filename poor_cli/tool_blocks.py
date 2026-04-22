"""Typed content blocks for tool results (Proposal B / C T11).

Tool handlers return ``ToolResult`` instances with a list of typed blocks
instead of a raw string. The frontend renders each block kind appropriately
(DiffAdd/DiffDelete for DiffBlock, markdown tables for TableBlock, etc.), and
provider adapters serialize the blocks into the provider's tool-result format.

Old-style string-returning handlers are wrapped automatically by the
dispatcher into ``[TextBlock(text=result)]`` for backward compatibility during
the migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union


@dataclass
class TextBlock:
    """Plain text. The default block kind for prose, short status messages,
    and small diagnostic output."""

    text: str
    kind: Literal["text"] = "text"

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "text": self.text}


@dataclass
class CodeBlock:
    """Syntax-highlighted code. ``language`` drives the frontend's filetype."""

    language: str
    code: str
    kind: Literal["code"] = "code"

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "language": self.language, "code": self.code}


@dataclass
class DiffBlock:
    """Before/after content for a file. The frontend renders with DiffAdd
    + DiffDelete highlights and can route the block into the diff review panel."""

    file: str
    before: str
    after: str
    kind: Literal["diff"] = "diff"

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "file": self.file, "before": self.before, "after": self.after}


@dataclass
class TableBlock:
    """Tabular data. Rendered as a markdown table by the frontend and as a
    plain-text aligned table for providers that don't support tables."""

    columns: List[str]
    rows: List[List[str]]
    kind: Literal["table"] = "table"

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "columns": self.columns, "rows": self.rows}


@dataclass
class FileRefBlock:
    """A pointer to a file location. Lets the agent's output be clickable
    (gf in the chat buffer) without spilling raw paths into prose."""

    path: str
    line: Optional[int] = None
    kind: Literal["file"] = "file"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"kind": self.kind, "path": self.path}
        if self.line is not None:
            out["line"] = self.line
        return out


@dataclass
class ImageBlock:
    """Base64-encoded image. Providers that support vision (Anthropic, Gemini)
    can consume these directly; others get a placeholder TextBlock."""

    media_type: str
    data_base64: str
    kind: Literal["image"] = "image"

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "media_type": self.media_type, "data_base64": self.data_base64}


ContentBlock = Union[TextBlock, CodeBlock, DiffBlock, TableBlock, FileRefBlock, ImageBlock]


@dataclass
class ToolResult:
    """Structured return value from a tool handler.

    Metadata conventions:
      - ``metadata["degraded"]``: str — set when the handler took a fallback
        code path (e.g. raw CLI instead of a preferred client integration).
      - ``metadata["token_cost"]``: dict — ``{"in": int, "out": int}`` when
        the tool spent tokens internally (used by cost attribution — Proposal C T8).
      - ``metadata["wall_time_ms"]``: int — populated by the dispatcher.
      - ``metadata["retry_attempts"]``: int — populated by the retry wrapper.
      - ``metadata["timeout"]``: bool — set when the tool timed out before
        returning a final result (partial blocks precede).
      - ``metadata["validation_error"]``: bool — set when args failed schema
        validation (the content is a repair message for the model).
    """

    content: List[ContentBlock]
    is_error: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": [block.to_dict() for block in self.content],
            "is_error": self.is_error,
            "metadata": self.metadata,
        }

    @classmethod
    def text(cls, text: str, *, is_error: bool = False, **metadata: Any) -> "ToolResult":
        """Convenience constructor for the single-TextBlock common case."""
        return cls(content=[TextBlock(text=text)], is_error=is_error, metadata=dict(metadata))

    @classmethod
    def error(cls, message: str, **metadata: Any) -> "ToolResult":
        """Convenience constructor for error results."""
        return cls(content=[TextBlock(text=message)], is_error=True, metadata=dict(metadata))


def wrap_legacy_result(value: Any) -> ToolResult:
    """Adapter for handlers that still return strings/dicts. Used by the
    dispatcher during the migration so callers can be rolled over one at a
    time without breaking the return contract.
    """
    if isinstance(value, ToolResult):
        return value
    if isinstance(value, str):
        return ToolResult.text(value)
    if isinstance(value, dict):
        return ToolResult.text(str(value), legacy=True)
    return ToolResult.text(repr(value), legacy=True)
