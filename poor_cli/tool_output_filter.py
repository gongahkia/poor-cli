"""Tool output filtering middleware."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - optional fallback
    yaml = None

try:
    import jmespath
except ImportError:  # pragma: no cover - optional fallback
    jmespath = None

from .exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_TOOL_OUTPUT_MAX_TOKENS = 5000
FILTER_STATS_KEYS = (
    "filtered_calls",
    "projection_filtered_calls",
    "auto_filtered_calls",
    "tokens_saved",
)
DEFAULT_PROJECTIONS: Dict[str, List[str]] = {
    "gh_pr_list": ["number", "title", "state", "author.login", "url"],
    "gh_pr_view": ["number", "title", "body", "state", "author.login", "url"],
    "gh_issue_list": ["number", "title", "state", "author.login", "url"],
    "gh_issue_view": ["number", "title", "body", "state", "author.login", "url"],
    "git_status": ["branch", "modified", "added", "deleted", "untracked"],
    "list_directory": ["name", "type", "size"],
}

_SIMPLE_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_LIST_INDEX_RE = re.compile(r"^(.*)\[(\d+)\]$")


@dataclass
class ProjectionRule:
    extract: List[str] = field(default_factory=list)
    max_tokens: Optional[int] = None


@dataclass
class FilterRequest:
    arguments: Dict[str, Any]
    projection: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    explicit_projection: bool = False


@dataclass
class FilterResult:
    output: str
    applied: bool
    auto_filtered: bool
    projection: List[str] = field(default_factory=list)
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    note: str = ""


def empty_filter_stats() -> Dict[str, int]:
    return {key: 0 for key in FILTER_STATS_KEYS}


def merge_filter_stats(*stats: Optional[Dict[str, Any]]) -> Dict[str, int]:
    merged = empty_filter_stats()
    for stat in stats:
        if not isinstance(stat, dict):
            continue
        for key in FILTER_STATS_KEYS:
            merged[key] += int(stat.get(key, 0) or 0)
    return merged


class ToolOutputFilter:
    """Projection + size-aware tool output filtering."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        *,
        default_max_tokens: int = DEFAULT_TOOL_OUTPUT_MAX_TOKENS,
        config_path: Optional[Path] = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.default_max_tokens = max(1, int(default_max_tokens))
        self.config_path = config_path
        self._global_max_tokens = self.default_max_tokens
        self._user_rules: Dict[str, ProjectionRule] = {}
        self._load_config()

    def prepare_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        declaration: Optional[Dict[str, Any]] = None,
    ) -> FilterRequest:
        args = dict(arguments or {})
        declared = (
            ((declaration or {}).get("parameters") or {}).get("properties") or {}
            if isinstance(declaration, dict)
            else {}
        )

        projection: Optional[List[str]] = None
        explicit = False
        if "_projection" in args:
            projection = self._normalize_projection(args.pop("_projection"))
            explicit = projection is not None
        elif "projection" in args and "projection" not in declared:
            projection = self._normalize_projection(args.pop("projection"))
            explicit = projection is not None

        max_tokens: Optional[int] = None
        if "_output_max_tokens" in args:
            max_tokens = self._coerce_positive_int(args.pop("_output_max_tokens"))
        elif "max_tokens" in args and "max_tokens" not in declared:
            max_tokens = self._coerce_positive_int(args.pop("max_tokens"))

        return FilterRequest(
            arguments=args,
            projection=projection,
            max_tokens=max_tokens,
            explicit_projection=explicit,
        )

    def filter(
        self,
        tool_name: str,
        response: Any,
        *,
        projection: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        original_text: Optional[str] = None,
        explicit_projection: bool = False,
    ) -> FilterResult:
        rendered_original = original_text if original_text is not None else self._render_output(response)
        tokens_before = self._estimate_tokens(rendered_original)
        rule = self._resolve_rule(tool_name)
        limit = max_tokens or rule.max_tokens or self._global_max_tokens or self.default_max_tokens
        effective_projection = list(projection or [])
        auto_filtered = False
        note_parts: List[str] = []
        candidate_payload: Any = None
        candidate_text = rendered_original

        oversized = tokens_before > limit
        if not effective_projection and oversized:
            effective_projection = list(rule.extract)
            auto_filtered = bool(effective_projection)

        structured = self._to_structured_response(tool_name, response)
        if effective_projection:
            projected = self._apply_projection(structured, effective_projection)
            if projected is not None:
                candidate_payload = projected
                candidate_text = self._render_output(projected)
                note_parts.append(
                    "kept fields: " + ", ".join(effective_projection)
                )
                if oversized and not explicit_projection:
                    note_parts.append(
                        f"auto-filtered response over {limit} tokens"
                    )
            elif explicit_projection:
                note_parts.append("projection requested but response was not structured")

        if oversized and candidate_text == rendered_original and not note_parts:
            note_parts.append(f"auto-filtered response over {limit} tokens")

        if self._estimate_tokens(candidate_text) > limit:
            truncated_text, truncate_note = self._truncate_output(
                candidate_text,
                candidate_payload,
                limit,
            )
            candidate_text = truncated_text
            note_parts.append(truncate_note)
            auto_filtered = True

        if not note_parts:
            return FilterResult(
                output=rendered_original,
                applied=False,
                auto_filtered=False,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                tokens_saved=0,
            )

        note = "[tool-output-filter] " + "; ".join(dict.fromkeys(part for part in note_parts if part))
        final_output = candidate_text.rstrip()
        if final_output:
            final_output += "\n\n" + note
        else:
            final_output = note
        tokens_after = self._estimate_tokens(final_output)
        return FilterResult(
            output=final_output,
            applied=True,
            auto_filtered=auto_filtered or oversized,
            projection=effective_projection,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=max(0, tokens_before - tokens_after),
            note=note,
        )

    def _load_config(self) -> None:
        self._global_max_tokens = self.default_max_tokens
        self._user_rules = {}
        if yaml is None:
            return

        merged: Dict[str, Any] = {}
        for path in self._candidate_paths():
            if not path.is_file():
                continue
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                logger.warning("Failed to load tool projection config %s: %s", path, exc)
                continue
            if not isinstance(payload, dict):
                continue
            defaults = payload.get("defaults")
            if isinstance(defaults, dict):
                merged_defaults = merged.setdefault("defaults", {})
                merged_defaults.update(defaults)
            if "max_tokens" in payload:
                merged["max_tokens"] = payload.get("max_tokens")
            tool_rules = payload.get("tool_projections")
            if isinstance(tool_rules, dict):
                merged_rules = merged.setdefault("tool_projections", {})
                merged_rules.update(tool_rules)

        self._global_max_tokens = self._coerce_positive_int(
            ((merged.get("defaults") or {}).get("max_tokens"))
            or merged.get("max_tokens")
        ) or self.default_max_tokens

        tool_rules = merged.get("tool_projections") or {}
        if not isinstance(tool_rules, dict):
            return
        for pattern, raw_rule in tool_rules.items():
            normalized = self._normalize_rule(raw_rule)
            if normalized is not None:
                self._user_rules[str(pattern)] = normalized

    def _candidate_paths(self) -> List[Path]:
        if self.config_path:
            return [self.config_path]
        return [
            Path.home() / ".poor-cli" / "tool_projections.yaml",
            self.repo_root / ".poor-cli" / "tool_projections.yaml",
        ]

    def _resolve_rule(self, tool_name: str) -> ProjectionRule:
        if tool_name in self._user_rules:
            return self._user_rules[tool_name]
        for pattern, rule in self._user_rules.items():
            if fnmatch.fnmatch(tool_name, pattern):
                return rule
        if tool_name in DEFAULT_PROJECTIONS:
            return ProjectionRule(extract=list(DEFAULT_PROJECTIONS[tool_name]))
        return ProjectionRule()

    @staticmethod
    def _normalize_rule(raw_rule: Any) -> Optional[ProjectionRule]:
        if isinstance(raw_rule, list):
            extract = ToolOutputFilter._normalize_projection(raw_rule)
            return ProjectionRule(extract=extract or [])
        if not isinstance(raw_rule, dict):
            return None
        extract = ToolOutputFilter._normalize_projection(
            raw_rule.get("extract", raw_rule.get("fields"))
        ) or []
        max_tokens = ToolOutputFilter._coerce_positive_int(raw_rule.get("max_tokens"))
        return ProjectionRule(extract=extract, max_tokens=max_tokens)

    @staticmethod
    def _normalize_projection(raw_projection: Any) -> Optional[List[str]]:
        if raw_projection is None:
            return None
        if isinstance(raw_projection, str):
            return [raw_projection] if raw_projection.strip() else None
        if isinstance(raw_projection, Iterable):
            items = [str(item).strip() for item in raw_projection if str(item).strip()]
            return items or None
        return None

    @staticmethod
    def _coerce_positive_int(value: Any) -> Optional[int]:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return None
        return coerced if coerced > 0 else None

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def _render_output(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    def _to_structured_response(self, tool_name: str, response: Any) -> Any:
        if isinstance(response, (dict, list)):
            return response
        if isinstance(response, str):
            stripped = response.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except Exception:
                    pass
            if tool_name == "list_directory":
                parsed = self._parse_list_directory_output(response)
                if parsed is not None:
                    return parsed
            if tool_name == "git_status":
                parsed = self._parse_git_status_output(response)
                if parsed is not None:
                    return parsed
        return None

    def _apply_projection(self, data: Any, projection: List[str]) -> Any:
        if data is None or not projection:
            return None
        if isinstance(data, list) and all(self._is_simple_path(expr) for expr in projection):
            items = []
            for item in data:
                if not isinstance(item, dict):
                    items.append(item)
                    continue
                projected_item = self._project_mapping(item, projection)
                if projected_item:
                    items.append(projected_item)
            return items
        if isinstance(data, dict):
            return self._project_mapping(data, projection)
        return None

    def _project_mapping(self, data: Dict[str, Any], projection: List[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for expr in projection:
            value = self._search(expr, data)
            if value is None:
                continue
            if self._is_simple_path(expr):
                self._assign_nested_path(result, expr.split("."), value)
            else:
                result[self._alias(expr)] = value
        return result

    def _search(self, expression: str, data: Any) -> Any:
        expr = expression.replace("[]", "[*]")
        if jmespath is not None:
            try:
                return jmespath.search(expr, data)
            except Exception:
                pass
        return self._fallback_search(expr, data)

    def _fallback_search(self, expression: str, data: Any) -> Any:
        if not expression:
            return data
        if any(token in expression for token in ("{", "}", "|", "&", "?", ":")):
            return None
        return self._walk_path(data, expression.split("."))

    def _walk_path(self, current: Any, segments: List[str]) -> Any:
        if current is None:
            return None
        if not segments:
            return current
        segment = segments[0]
        if segment.endswith("[*]"):
            key = segment[:-3]
            target = current
            if key:
                if not isinstance(current, dict):
                    return None
                target = current.get(key)
            if not isinstance(target, list):
                return None
            values = []
            for item in target:
                value = self._walk_path(item, segments[1:])
                if value is None:
                    continue
                values.append(value)
            return values
        match = _LIST_INDEX_RE.match(segment)
        if match:
            key = match.group(1)
            index = int(match.group(2))
            target = current
            if key:
                if not isinstance(current, dict):
                    return None
                target = current.get(key)
            if not isinstance(target, list) or index >= len(target):
                return None
            return self._walk_path(target[index], segments[1:])
        if not isinstance(current, dict):
            return None
        return self._walk_path(current.get(segment), segments[1:])

    @staticmethod
    def _assign_nested_path(result: Dict[str, Any], path: List[str], value: Any) -> None:
        cursor = result
        for segment in path[:-1]:
            next_value = cursor.get(segment)
            if not isinstance(next_value, dict):
                next_value = {}
                cursor[segment] = next_value
            cursor = next_value
        cursor[path[-1]] = value

    @staticmethod
    def _alias(expression: str) -> str:
        alias = re.sub(r"[^A-Za-z0-9_]+", "_", expression).strip("_")
        return alias or "value"

    @staticmethod
    def _is_simple_path(expression: str) -> bool:
        return bool(_SIMPLE_PATH_RE.fullmatch(expression))

    def _truncate_output(
        self,
        rendered: str,
        payload: Any,
        max_tokens: int,
    ) -> tuple[str, str]:
        char_limit = max(256, max_tokens * 4 - 256)
        if isinstance(payload, list):
            kept: List[Any] = []
            for item in payload:
                trial = self._render_output(kept + [item])
                if len(trial) > char_limit and kept:
                    break
                if len(trial) > char_limit:
                    break
                kept.append(item)
            omitted = max(0, len(payload) - len(kept))
            if kept:
                return self._render_output(kept), f"truncated {omitted} trailing items"
        trimmed = rendered[:char_limit].rstrip()
        omitted_chars = max(0, len(rendered) - len(trimmed))
        return trimmed, f"truncated {omitted_chars} chars"

    @staticmethod
    def _parse_list_directory_output(text: str) -> Optional[List[Dict[str, str]]]:
        entries: List[Dict[str, str]] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("Contents of ") or stripped.startswith("total "):
                continue
            meta_match = re.match(r"^(DIR|FILE|LINK)\s+(\S+)\s+(.+)$", stripped)
            if meta_match:
                entries.append(
                    {
                        "type": meta_match.group(1).lower(),
                        "size": meta_match.group(2),
                        "name": meta_match.group(3),
                    }
                )
                continue
            if line and line[0] in "-dlcbsp":
                parts = stripped.split()
                if len(parts) >= 9:
                    entries.append(
                        {
                            "type": {"d": "dir", "l": "link"}.get(parts[0][0], "file"),
                            "size": parts[4],
                            "name": " ".join(parts[8:]),
                        }
                    )
        return entries or None

    @staticmethod
    def _parse_git_status_output(text: str) -> Optional[Dict[str, Any]]:
        lines = text.splitlines()
        if not lines:
            return None
        payload: Dict[str, Any] = {
            "branch": None,
            "modified": [],
            "added": [],
            "deleted": [],
            "renamed": [],
            "untracked": [],
        }
        if any(line.startswith("On branch ") for line in lines):
            section = ""
            for raw_line in lines:
                stripped = raw_line.strip()
                if stripped.startswith("On branch "):
                    payload["branch"] = stripped[len("On branch "):].strip()
                    continue
                if stripped.startswith("Changes to be committed"):
                    section = "staged"
                    continue
                if stripped.startswith("Changes not staged for commit"):
                    section = "unstaged"
                    continue
                if stripped.startswith("Untracked files"):
                    section = "untracked"
                    continue
                if not stripped or stripped.startswith("("):
                    continue
                if stripped.startswith("modified:"):
                    payload["modified"].append(stripped.split(":", 1)[1].strip())
                elif stripped.startswith("new file:"):
                    payload["added"].append(stripped.split(":", 1)[1].strip())
                elif stripped.startswith("deleted:"):
                    payload["deleted"].append(stripped.split(":", 1)[1].strip())
                elif stripped.startswith("renamed:"):
                    payload["renamed"].append(stripped.split(":", 1)[1].strip())
                elif section == "untracked" and ":" not in stripped:
                    payload["untracked"].append(stripped)
            return payload

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("## "):
                payload["branch"] = stripped[3:].split("...", 1)[0]
                continue
            if len(stripped) < 3:
                continue
            status = stripped[:2]
            path = stripped[3:].strip()
            if status == "??":
                payload["untracked"].append(path)
            elif "A" in status:
                payload["added"].append(path)
            elif "D" in status:
                payload["deleted"].append(path)
            elif "R" in status:
                payload["renamed"].append(path)
            elif "M" in status:
                payload["modified"].append(path)
        if any(payload[key] for key in ("modified", "added", "deleted", "renamed", "untracked")):
            return payload
        return None
