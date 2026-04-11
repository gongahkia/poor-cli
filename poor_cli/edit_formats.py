"""Multiple edit format support for different model capabilities."""

from __future__ import annotations

import ast
import difflib
import json
import math
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

_SEARCH_MARKER = "<<<<<<< SEARCH"
_DIVIDER_MARKER = "======="
_REPLACE_MARKER = ">>>>>>> REPLACE"
_BRACKET_CHECK_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".kt", ".kts", ".php", ".rs", ".swift", ".ts", ".tsx",
}


@dataclass(frozen=True)
class RenderedEdit:
    """Rendered edit payload plus selection metadata."""

    format_name: str
    payload: str
    changed_lines: int
    used_fallback: bool = False


class EditFormat:
    """Base class for edit format renderers."""

    name: str = "base"

    def apply(self, content: str, **kwargs) -> Tuple[str, str]:
        """Apply edit, return (new_content, mode_description)."""
        raise NotImplementedError


class SearchReplaceFormat(EditFormat):
    """Exact search/replace plus aider-style SEARCH/REPLACE blocks."""

    name = "search_replace"

    def apply(
        self,
        content: str,
        old_text: str = "",
        new_text: str = "",
        replace_all: bool = False,
        blocks_text: str = "",
        **kw,
    ) -> Tuple[str, str]:
        edits = self._parse_blocks(blocks_text or kw.get("search_replace_text", ""))
        current = content
        matched_total = 0

        if edits:
            for search_text, replacement_text in edits:
                current, matched = self._apply_single(
                    current,
                    old_text=search_text,
                    new_text=replacement_text,
                    replace_all=False,
                )
                matched_total += matched
            _validate_or_raise(current, file_path=kw.get("file_path"), validate_syntax=kw.get("validate_syntax", False))
            return current, f"search_replace_blocks ({len(edits)} blocks)"

        current, matched_total = self._apply_single(
            current,
            old_text=old_text,
            new_text=new_text,
            replace_all=replace_all,
        )
        _validate_or_raise(current, file_path=kw.get("file_path"), validate_syntax=kw.get("validate_syntax", False))
        return current, f"search_replace (matched {matched_total}x)"

    def _parse_blocks(self, blocks_text: str) -> List[Tuple[str, str]]:
        if not blocks_text:
            return []

        lines = blocks_text.splitlines(keepends=True)
        idx = 0
        blocks: List[Tuple[str, str]] = []

        while idx < len(lines):
            line = lines[idx].rstrip("\r\n")
            if not line:
                idx += 1
                continue
            if line != _SEARCH_MARKER:
                raise ValueError("unexpected content outside SEARCH/REPLACE block")

            idx += 1
            search_lines: List[str] = []
            while idx < len(lines) and lines[idx].rstrip("\r\n") != _DIVIDER_MARKER:
                search_lines.append(lines[idx])
                idx += 1
            if idx >= len(lines):
                raise ValueError("unterminated SEARCH block")

            idx += 1
            replace_lines: List[str] = []
            while idx < len(lines) and lines[idx].rstrip("\r\n") != _REPLACE_MARKER:
                replace_lines.append(lines[idx])
                idx += 1
            if idx >= len(lines):
                raise ValueError("unterminated REPLACE block")

            idx += 1
            search_text = "".join(search_lines)
            if not search_text:
                raise ValueError("SEARCH block cannot be empty")
            blocks.append((search_text, "".join(replace_lines)))

        return blocks

    def _apply_single(
        self,
        content: str,
        old_text: str,
        new_text: str,
        replace_all: bool,
    ) -> Tuple[str, int]:
        if not old_text:
            raise ValueError("search_replace requires old_text")
        count = content.count(old_text)
        if count == 0:
            raise ValueError("old_text not found in file (0 matches)")
        if count > 1 and not replace_all:
            raise ValueError(f"old_text has {count} matches; use replace_all=True or provide more context")
        updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        return updated, count


class WholeFileFormat(EditFormat):
    """Replace entire file content."""

    name = "whole_file"

    def apply(self, content: str, new_text: str = "", **kw) -> Tuple[str, str]:
        _validate_or_raise(new_text, file_path=kw.get("file_path"), validate_syntax=kw.get("validate_syntax", False))
        return new_text, "whole_file"


class UnifiedDiffFormat(EditFormat):
    """Parse and apply unified diff hunks."""

    name = "unified_diff"
    _HUNK_RE = re.compile(r"^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@", re.MULTILINE)

    def apply(self, content: str, diff_text: str = "", **kw) -> Tuple[str, str]:
        if not diff_text:
            raise ValueError("unified_diff requires diff_text")

        hunks = self._parse_hunks(diff_text)
        if not hunks:
            raise ValueError("no valid diff hunks found in diff_text")

        original_lines = content.splitlines()
        trailing_newline = content.endswith("\n")
        result_lines = list(original_lines)
        offset = 0

        for old_start, old_count, _new_start, _new_count, old_chunk, new_chunk in hunks:
            start_idx = 0 if old_start == 0 else old_start - 1 + offset
            end_idx = start_idx + old_count
            current_chunk = result_lines[start_idx:end_idx]
            if current_chunk != old_chunk:
                raise ValueError(
                    f"unified_diff hunk mismatch at source line {old_start}: expected {old_chunk!r}, found {current_chunk!r}"
                )
            result_lines[start_idx:end_idx] = new_chunk
            offset += len(new_chunk) - old_count

        rendered = _join_lines(result_lines, trailing_newline)
        _validate_or_raise(rendered, file_path=kw.get("file_path"), validate_syntax=kw.get("validate_syntax", False))
        return rendered, f"unified_diff ({len(hunks)} hunks)"

    def _parse_hunks(self, diff_text: str) -> List[Tuple[int, int, int, int, List[str], List[str]]]:
        lines = diff_text.splitlines()
        idx = 0
        hunks: List[Tuple[int, int, int, int, List[str], List[str]]] = []

        while idx < len(lines):
            line = lines[idx]
            if line.startswith("--- ") or line.startswith("+++ "):
                idx += 1
                continue

            match = self._HUNK_RE.match(line)
            if not match:
                idx += 1
                continue

            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            idx += 1

            old_chunk: List[str] = []
            new_chunk: List[str] = []
            while idx < len(lines):
                body_line = lines[idx]
                if self._HUNK_RE.match(body_line):
                    break
                if body_line.startswith("--- ") and idx + 1 < len(lines) and lines[idx + 1].startswith("+++ "):
                    break
                if body_line.startswith("\\ "):
                    idx += 1
                    continue
                if not body_line:
                    raise ValueError("invalid unified_diff hunk line: missing prefix")
                prefix = body_line[0]
                payload = body_line[1:]
                if prefix == " ":
                    old_chunk.append(payload)
                    new_chunk.append(payload)
                elif prefix == "-":
                    old_chunk.append(payload)
                elif prefix == "+":
                    new_chunk.append(payload)
                else:
                    raise ValueError(f"invalid unified_diff hunk line prefix: {prefix!r}")
                idx += 1

            if len(old_chunk) != old_count:
                raise ValueError(
                    f"unified_diff old hunk line count mismatch: header={old_count}, body={len(old_chunk)}"
                )
            if len(new_chunk) != new_count:
                raise ValueError(
                    f"unified_diff new hunk line count mismatch: header={new_count}, body={len(new_chunk)}"
                )
            hunks.append((old_start, old_count, new_start, new_count, old_chunk, new_chunk))

        return hunks


class LineRangeFormat(EditFormat):
    """Replace lines by range."""

    name = "line_range"

    def apply(self, content: str, new_text: str = "", start_line: int = 0, end_line: int = 0, **kw) -> Tuple[str, str]:
        lines = content.splitlines(keepends=True)
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            raise ValueError(f"invalid line range {start_line}-{end_line} (file has {len(lines)} lines)")
        new_lines = new_text.splitlines(keepends=True)
        if new_text and not new_text.endswith("\n"):
            new_lines.append("")
        lines[start_line - 1:end_line] = new_lines
        rendered = "".join(lines)
        _validate_or_raise(rendered, file_path=kw.get("file_path"), validate_syntax=kw.get("validate_syntax", False))
        return rendered, f"line_range ({start_line}-{end_line})"


_FORMATS: Dict[str, EditFormat] = {
    "search_replace": SearchReplaceFormat(),
    "search_replace_block": SearchReplaceFormat(),
    "whole_file": WholeFileFormat(),
    "unified_diff": UnifiedDiffFormat(),
    "line_range": LineRangeFormat(),
}

_MODEL_FORMAT_HINTS: Dict[str, str] = {
    "anthropic/claude": "search_replace",
    "claude": "search_replace",
    "gemini": "search_replace",
    "gpt": "unified_diff",
    "openai/": "unified_diff",
    "llama": "whole_file",
    "codellama": "whole_file",
    "mistral": "whole_file",
    "qwen": "search_replace",
    "deepseek": "search_replace",
}


def _join_lines(lines: Sequence[str], trailing_newline: bool) -> str:
    if not lines:
        return ""
    return "\n".join(lines) + ("\n" if trailing_newline else "")


def _slice_to_text(lines: Sequence[str], start: int, end: int, trailing_newline: bool) -> str:
    if start >= end:
        return ""
    text = "\n".join(lines[start:end])
    if end < len(lines) or trailing_newline:
        text += "\n"
    return text


def _rough_token_count(text: str) -> int:
    return 0 if not text else max(1, math.ceil(len(text) / 4))


def _balanced_delimiters(text: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    openings = set(pairs.values())
    closings = set(pairs.keys())
    stack: List[str] = []
    quote: Optional[str] = None
    escaped = False

    for ch in text:
        if quote:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == quote:
                quote = None
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            continue
        if ch in openings:
            stack.append(ch)
            continue
        if ch in closings:
            if not stack or stack.pop() != pairs[ch]:
                return False

    return not stack and quote is None


def validate_edited_content(content: str, file_path: Optional[str] = None) -> Tuple[bool, str]:
    """Validate edited content using parser checks when cheap, bracket checks otherwise."""

    suffix = Path(file_path).suffix.lower() if file_path else ""

    try:
        if suffix == ".py":
            ast.parse(content or "\n")
            return True, "python_ast"
        if suffix == ".json":
            json.loads(content)
            return True, "json"
        if suffix == ".toml":
            tomllib.loads(content or "")
            return True, "toml"
        if suffix in _BRACKET_CHECK_EXTENSIONS and _balanced_delimiters(content):
            return True, "balanced_delimiters"
        if suffix in _BRACKET_CHECK_EXTENSIONS:
            return False, "unbalanced_delimiters"
        return True, "skipped"
    except (SyntaxError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return False, f"{suffix or 'content'} syntax invalid: {exc}"


def _validate_or_raise(content: str, file_path: Optional[str], validate_syntax: bool) -> None:
    if not (validate_syntax or file_path):
        return
    valid, reason = validate_edited_content(content, file_path=file_path)
    if not valid:
        raise ValueError(reason)


def estimate_changed_lines(original_content: str, updated_content: str) -> int:
    """Estimate changed logical lines without double-counting replace ops."""

    matcher = difflib.SequenceMatcher(
        a=original_content.splitlines(),
        b=updated_content.splitlines(),
    )
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
    return changed


def render_search_replace_blocks(
    original_content: str,
    updated_content: str,
    *,
    context_lines: int = 1,
) -> str:
    """Render a single aider-style SEARCH/REPLACE block spanning all edits."""

    if original_content == updated_content:
        raise ValueError("no changes to render")
    if not original_content:
        raise ValueError("search_replace blocks require existing file content")

    old_lines = original_content.splitlines()
    new_lines = updated_content.splitlines()
    old_trailing = original_content.endswith("\n")
    new_trailing = updated_content.endswith("\n")

    prefix = 0
    while prefix < len(old_lines) and prefix < len(new_lines) and old_lines[prefix] == new_lines[prefix]:
        prefix += 1

    suffix = 0
    max_suffix = min(len(old_lines) - prefix, len(new_lines) - prefix)
    while suffix < max_suffix and old_lines[-1 - suffix] == new_lines[-1 - suffix]:
        suffix += 1

    old_change_end = len(old_lines) - suffix
    new_change_end = len(new_lines) - suffix
    max_context = max(len(old_lines), len(new_lines))

    for ctx in range(context_lines, max_context + 1):
        leading_context = min(ctx, prefix)
        trailing_context = min(ctx, suffix)

        old_start = prefix - leading_context
        old_end = old_change_end + trailing_context
        new_start = prefix - leading_context
        new_end = new_change_end + trailing_context

        search_text = _slice_to_text(old_lines, old_start, old_end, old_trailing)
        replacement_text = _slice_to_text(new_lines, new_start, new_end, new_trailing)

        if search_text and not search_text.endswith("\n"):
            continue
        if replacement_text and not replacement_text.endswith("\n"):
            continue
        if search_text and original_content.count(search_text) == 1:
            return (
                f"{_SEARCH_MARKER}\n"
                f"{search_text}"
                f"{_DIVIDER_MARKER}\n"
                f"{replacement_text}"
                f"{_REPLACE_MARKER}\n"
            )

    raise ValueError("unable to render unique SEARCH/REPLACE block")


def render_unified_diff(
    original_content: str,
    updated_content: str,
    *,
    file_path: Optional[str] = None,
    context_lines: int = 3,
) -> str:
    """Render unified diff text."""

    file_label = file_path or "file"
    diff_lines = list(
        difflib.unified_diff(
            original_content.splitlines(),
            updated_content.splitlines(),
            fromfile=f"a/{file_label}",
            tofile=f"b/{file_label}",
            n=context_lines,
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    return "\n".join(diff_lines) + "\n"


def select_edit_format(
    original_content: str,
    updated_content: str,
    *,
    provider_preference: Optional[str] = None,
    is_new_file: bool = False,
) -> str:
    """Choose edit format from size heuristic plus provider preference."""

    changed_lines = estimate_changed_lines(original_content, updated_content)
    if is_new_file or not original_content:
        logger.warning("Falling back to whole_file edit format: new file or empty source content")
        return "whole_file"
    if changed_lines > 50:
        logger.warning("Falling back to whole_file edit format: %s changed lines", changed_lines)
        return "whole_file"
    if provider_preference == "whole_file":
        logger.warning("Falling back to whole_file edit format: provider preference requested whole_file")
        return "whole_file"
    if provider_preference in {"search_replace", "unified_diff"}:
        return provider_preference
    if changed_lines < 5:
        return "search_replace"
    return "unified_diff"


def render_compact_edit(
    original_content: str,
    updated_content: str,
    *,
    file_path: Optional[str] = None,
    provider_preference: Optional[str] = None,
    is_new_file: bool = False,
) -> RenderedEdit:
    """Render the most compact supported edit payload for the given change."""

    changed_lines = estimate_changed_lines(original_content, updated_content)
    chosen = select_edit_format(
        original_content,
        updated_content,
        provider_preference=provider_preference,
        is_new_file=is_new_file,
    )
    used_fallback = False

    if chosen == "search_replace":
        try:
            payload = render_search_replace_blocks(original_content, updated_content)
            return RenderedEdit(chosen, payload, changed_lines, used_fallback)
        except ValueError as exc:
            logger.warning("Falling back from search_replace to unified_diff: %s", exc)
            chosen = "unified_diff"
            used_fallback = True

    if chosen == "unified_diff":
        payload = render_unified_diff(original_content, updated_content, file_path=file_path)
        if payload:
            return RenderedEdit(chosen, payload, changed_lines, used_fallback)
        logger.warning("Falling back to whole_file edit format: unified_diff render produced empty payload")
        chosen = "whole_file"
        used_fallback = True

    logger.warning(
        "Using whole_file edit format (%s changed lines, approx_tokens=%s)",
        changed_lines,
        _rough_token_count(updated_content),
    )
    return RenderedEdit("whole_file", updated_content, changed_lines, True if chosen != "whole_file" else used_fallback)


def get_format(name: str) -> EditFormat:
    """Get edit format by name."""

    fmt = _FORMATS.get(name)
    if not fmt:
        raise ValueError(f"unknown edit format: {name}; available: {list(_FORMATS.keys())}")
    return fmt


def suggest_format_for_model(model_name: str, provider_name: Optional[str] = None) -> str:
    """Suggest provider-tuned edit format based on provider/model name."""

    provider = (provider_name or "").lower()
    if provider == "openai":
        return "unified_diff"
    if provider in {"anthropic", "claude", "gemini"}:
        return "search_replace"
    if provider == "ollama":
        return "whole_file"
    if provider == "openrouter":
        model_lower = model_name.lower()
        if "claude" in model_lower or "anthropic/" in model_lower or "gemini" in model_lower:
            return "search_replace"
        if "gpt" in model_lower or "openai/" in model_lower:
            return "unified_diff"
        if any(token in model_lower for token in ("llama", "mistral", "codellama")):
            return "whole_file"

    model_lower = model_name.lower()
    for prefix, fmt in _MODEL_FORMAT_HINTS.items():
        if prefix in model_lower:
            return fmt
    return "search_replace"
