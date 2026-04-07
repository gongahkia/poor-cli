"""Multiple edit format support for different model capabilities."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)


class EditFormat:
    """Base class for edit format renderers."""
    name: str = "base"
    def apply(self, content: str, **kwargs) -> Tuple[str, str]:
        """Apply edit, return (new_content, mode_description)."""
        raise NotImplementedError


class SearchReplaceFormat(EditFormat):
    """Current default: exact text search and replace."""
    name = "search_replace"
    def apply(self, content: str, old_text: str = "", new_text: str = "", replace_all: bool = False, **kw) -> Tuple[str, str]:
        if not old_text:
            raise ValueError("search_replace requires old_text")
        count = content.count(old_text)
        if count == 0:
            raise ValueError(f"old_text not found in file (0 matches)")
        if count > 1 and not replace_all:
            raise ValueError(f"old_text has {count} matches; use replace_all=True or provide more context")
        new_content = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        return new_content, f"search_replace (matched {count}x)"


class WholeFileFormat(EditFormat):
    """Replace entire file content. Best for small models that struggle with diffs."""
    name = "whole_file"
    def apply(self, content: str, new_text: str = "", **kw) -> Tuple[str, str]:
        return new_text, "whole_file"


class UnifiedDiffFormat(EditFormat):
    """Parse and apply unified diff hunks."""
    name = "unified_diff"
    _HUNK_RE = re.compile(r'^@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@', re.MULTILINE)

    def apply(self, content: str, diff_text: str = "", **kw) -> Tuple[str, str]:
        if not diff_text:
            raise ValueError("unified_diff requires diff_text")
        hunks = list(self._HUNK_RE.finditer(diff_text))
        if not hunks:
            raise ValueError("no valid diff hunks found in diff_text")
        lines = content.splitlines(keepends=True)
        offset = 0
        applied = 0
        for hunk in hunks:
            start = int(hunk.group(1)) - 1 + offset
            hunk_text = self._extract_hunk_body(diff_text, hunk)
            old_lines, new_lines = self._parse_hunk(hunk_text)
            end = start + len(old_lines)
            lines[start:end] = [l + "\n" if not l.endswith("\n") else l for l in new_lines]
            offset += len(new_lines) - len(old_lines)
            applied += 1
        result = "".join(lines)
        if content and not content.endswith("\n"):
            result = result.rstrip("\n")
        return result, f"unified_diff ({applied} hunks)"

    def _extract_hunk_body(self, diff_text: str, hunk_match: re.Match) -> str:
        start = hunk_match.end()
        next_hunk = self._HUNK_RE.search(diff_text, start)
        end = next_hunk.start() if next_hunk else len(diff_text)
        return diff_text[start:end]

    def _parse_hunk(self, body: str) -> Tuple[List[str], List[str]]:
        old_lines: List[str] = []
        new_lines: List[str] = []
        for line in body.splitlines():
            if line.startswith("\\ "): # "\ No newline at end of file" — skip metadata
                continue
            if line.startswith("-"):
                old_lines.append(line[1:])
            elif line.startswith("+"):
                new_lines.append(line[1:])
            elif line.startswith(" "):
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line.strip(): # non-empty, non-prefixed line treated as context
                old_lines.append(line)
                new_lines.append(line)
        return old_lines, new_lines


class LineRangeFormat(EditFormat):
    """Replace lines by range (existing behavior)."""
    name = "line_range"
    def apply(self, content: str, new_text: str = "", start_line: int = 0, end_line: int = 0, **kw) -> Tuple[str, str]:
        lines = content.splitlines(keepends=True)
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            raise ValueError(f"invalid line range {start_line}-{end_line} (file has {len(lines)} lines)")
        new_lines = new_text.splitlines(keepends=True)
        if new_text and not new_text.endswith("\n"):
            new_lines.append("")
        lines[start_line - 1:end_line] = new_lines
        return "".join(lines), f"line_range ({start_line}-{end_line})"


_FORMATS: Dict[str, EditFormat] = {
    "search_replace": SearchReplaceFormat(),
    "whole_file": WholeFileFormat(),
    "unified_diff": UnifiedDiffFormat(),
    "line_range": LineRangeFormat(),
}

# model → preferred format (frontier models handle search_replace well; small models need whole_file)
_MODEL_FORMAT_HINTS: Dict[str, str] = {
    "gpt-5": "search_replace",
    "gpt-5.1": "search_replace",
    "gpt-4": "search_replace",
    "claude": "search_replace",
    "gemini-2.5-pro": "search_replace",
    "gemini-2.5-flash": "search_replace",
    "llama": "whole_file",
    "codellama": "whole_file",
    "mistral": "whole_file",
    "qwen": "search_replace",
    "deepseek": "search_replace",
}


def get_format(name: str) -> EditFormat:
    """Get edit format by name."""
    fmt = _FORMATS.get(name)
    if not fmt:
        raise ValueError(f"unknown edit format: {name}; available: {list(_FORMATS.keys())}")
    return fmt


def suggest_format_for_model(model_name: str) -> str:
    """Suggest best edit format based on model name."""
    model_lower = model_name.lower()
    for prefix, fmt in _MODEL_FORMAT_HINTS.items():
        if prefix in model_lower:
            return fmt
    return "search_replace" # default for unknown models
