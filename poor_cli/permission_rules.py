"""
Permission rule evaluation and persistence.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


_COMPOUND_OPERATORS = {"&&", "||", ";", "|"}


@dataclass(frozen=True)
class PermissionRule:
    tool_name: str
    behavior: str  # allow | deny | ask
    rule_content: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "toolName": self.tool_name,
            "behavior": self.behavior,
            "ruleContent": self.rule_content,
            "source": self.source,
        }


@dataclass(frozen=True)
class PermissionRuleMatch:
    behavior: str
    rule: PermissionRule
    segment: str = ""

    def to_dict(self) -> Dict[str, str]:
        payload = self.rule.to_dict()
        payload["segment"] = self.segment
        return payload


class PermissionRuleEngine:
    """Loads permission rules from user/project/local/session scopes."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.user_settings_path = Path.home() / ".poor-cli" / "settings.json"
        self.project_settings_path = self.repo_root / ".poor-cli" / "settings.json"
        self.local_settings_path = self.repo_root / ".poor-cli" / "settings.local.json"
        self._session_rules: List[PermissionRule] = []

    def add_session_rule(self, tool_name: str, behavior: str, rule_content: str = "") -> PermissionRule:
        rule = PermissionRule(
            tool_name=str(tool_name).strip(),
            behavior=self._normalize_behavior(behavior),
            rule_content=str(rule_content or "").strip(),
            source="session",
        )
        self._session_rules.insert(0, rule)
        return rule

    def clear_session_rules(self) -> None:
        self._session_rules = []

    def add_persistent_rule(
        self,
        *,
        scope: str,
        tool_name: str,
        behavior: str,
        rule_content: str = "",
    ) -> PermissionRule:
        normalized_scope = str(scope).strip().lower()
        if normalized_scope not in {"user", "project", "local"}:
            raise ValueError("scope must be one of: user, project, local")
        path = self._settings_path_for_scope(normalized_scope)
        payload = self._read_settings_payload(path)
        permissions = payload.setdefault("permissions", {})
        rules = permissions.setdefault("rules", [])
        if not isinstance(rules, list):
            rules = []
            permissions["rules"] = rules

        rule = PermissionRule(
            tool_name=str(tool_name).strip(),
            behavior=self._normalize_behavior(behavior),
            rule_content=str(rule_content or "").strip(),
            source=normalized_scope,
        )
        rules.append(
            {
                "toolName": rule.tool_name,
                "behavior": rule.behavior,
                "ruleContent": rule.rule_content,
            }
        )
        self._write_settings_payload(path, payload)
        return rule

    def list_rules(self) -> Dict[str, List[Dict[str, str]]]:
        return {
            "session": [rule.to_dict() for rule in self._session_rules],
            "local": [rule.to_dict() for rule in self._load_local_rules()],
            "project": [rule.to_dict() for rule in self._load_project_rules()],
            "user": [rule.to_dict() for rule in self._load_user_rules()],
        }

    def blanket_denied_tools(self) -> List[str]:
        """Return tool names hidden by the first blanket rule in precedence order."""
        first_blanket_behavior: Dict[str, str] = {}
        for rule in self._effective_rules():
            tool_key = rule.tool_name.strip().lower()
            if not tool_key or tool_key in first_blanket_behavior:
                continue
            if not self._is_blanket_pattern(rule.rule_content):
                continue
            first_blanket_behavior[tool_key] = rule.behavior
        return sorted(
            tool_name
            for tool_name, behavior in first_blanket_behavior.items()
            if behavior == "deny"
        )

    def is_tool_blanket_denied(self, tool_name: str) -> bool:
        actual = str(tool_name or "").strip().lower()
        if not actual:
            return False
        for rule in self._effective_rules():
            if not self._tool_name_matches(rule.tool_name, actual):
                continue
            if not self._is_blanket_pattern(rule.rule_content):
                continue
            return rule.behavior == "deny"
        return False

    def evaluate(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[PermissionRuleMatch]:
        normalized_tool = str(tool_name or "").strip().lower()
        if not normalized_tool:
            return None

        rules = self._effective_rules()
        if normalized_tool == "bash":
            return self._evaluate_bash_rules(rules, tool_args)

        subject = self._render_tool_subject(tool_args)
        for rule in rules:
            if not self._tool_name_matches(rule.tool_name, normalized_tool):
                continue
            if not self._rule_content_matches(rule.rule_content, subject):
                continue
            return PermissionRuleMatch(behavior=rule.behavior, rule=rule)
        return None

    def _evaluate_bash_rules(
        self,
        rules: List[PermissionRule],
        tool_args: Dict[str, Any],
    ) -> Optional[PermissionRuleMatch]:
        command = str(tool_args.get("command") or tool_args.get("cmd") or "").strip()
        if not command:
            return None
        segments = self._split_compound_command(command)
        if not segments:
            segments = [command]

        segment_matches: List[Optional[PermissionRuleMatch]] = []
        for segment in segments:
            segment_match = self._match_bash_segment(rules, segment)
            segment_matches.append(segment_match)

        for match in segment_matches:
            if match is not None and match.behavior == "deny":
                return match
        for match in segment_matches:
            if match is not None and match.behavior == "ask":
                return match

        if segment_matches and all(match is not None and match.behavior == "allow" for match in segment_matches):
            return next(match for match in segment_matches if match is not None)
        if any(match is not None and match.behavior == "allow" for match in segment_matches):
            allow_match = next(match for match in segment_matches if match is not None and match.behavior == "allow")
            synthetic = PermissionRule(
                tool_name="bash",
                behavior="ask",
                rule_content="(partial-match)",
                source="engine",
            )
            return PermissionRuleMatch(behavior="ask", rule=synthetic, segment=allow_match.segment)

        return None

    def _match_bash_segment(
        self,
        rules: List[PermissionRule],
        segment: str,
    ) -> Optional[PermissionRuleMatch]:
        normalized_segment = segment.strip()
        if not normalized_segment:
            return None
        for rule in rules:
            if not self._tool_name_matches(rule.tool_name, "bash"):
                continue
            if not self._rule_content_matches(rule.rule_content, normalized_segment):
                continue
            return PermissionRuleMatch(
                behavior=rule.behavior,
                rule=rule,
                segment=normalized_segment,
            )
        return None

    @staticmethod
    def _rule_content_matches(pattern: str, subject: str) -> bool:
        normalized_pattern = str(pattern or "").strip()
        if not normalized_pattern:
            return True
        if normalized_pattern == "*":
            return True
        if subject == normalized_pattern:
            return True
        return fnmatch(subject, normalized_pattern)

    @staticmethod
    def _tool_name_matches(rule_tool_name: str, actual_tool_name: str) -> bool:
        rule = str(rule_tool_name or "").strip().lower()
        actual = str(actual_tool_name or "").strip().lower()
        if not rule or not actual:
            return False
        if rule == "*":
            return True
        if any(ch in rule for ch in "*?[]"):
            return fnmatch(actual, rule)
        if actual == rule:
            return True
        if rule.startswith("mcp__") and actual.startswith(f"{rule}__"):
            return True
        return False

    @staticmethod
    def _is_blanket_pattern(pattern: str) -> bool:
        normalized = str(pattern or "").strip()
        return not normalized or normalized == "*"

    @staticmethod
    def _render_tool_subject(tool_args: Dict[str, Any]) -> str:
        try:
            return json.dumps(tool_args, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(tool_args)

    @staticmethod
    def _split_compound_command(command: str) -> List[str]:
        if not command.strip():
            return []
        normalized = re.sub(r"(\&\&|\|\||;|\|)", r" \1 ", command)
        try:
            tokens = shlex.split(normalized)
        except ValueError:
            fallback = re.split(r"(?:\&\&|\|\||;|\|)", command)
            return [chunk.strip() for chunk in fallback if chunk.strip()]
        segments: List[str] = []
        current: List[str] = []
        for token in tokens:
            if token in _COMPOUND_OPERATORS:
                if current:
                    segments.append(" ".join(current).strip())
                    current = []
                continue
            current.append(token)
        if current:
            segments.append(" ".join(current).strip())
        return [segment for segment in segments if segment]

    def _effective_rules(self) -> List[PermissionRule]:
        rules: List[PermissionRule] = []
        rules.extend(self._session_rules)
        rules.extend(self._load_local_rules())
        rules.extend(self._load_project_rules())
        rules.extend(self._load_user_rules())
        return rules

    def _load_local_rules(self) -> List[PermissionRule]:
        return self._load_rules_from_file(self.local_settings_path, source="local")

    def _load_project_rules(self) -> List[PermissionRule]:
        return self._load_rules_from_file(self.project_settings_path, source="project")

    def _load_user_rules(self) -> List[PermissionRule]:
        return self._load_rules_from_file(self.user_settings_path, source="user")

    def _load_rules_from_file(self, path: Path, *, source: str) -> List[PermissionRule]:
        data = self._read_settings_payload(path)
        if not data:
            return []
        permissions = data.get("permissions")
        if not isinstance(permissions, dict):
            return []

        rules: List[PermissionRule] = []

        raw_rules = permissions.get("rules")
        if isinstance(raw_rules, list):
            for entry in raw_rules:
                parsed = self._parse_rule_entry(entry, default_behavior="ask", source=source)
                if parsed is not None:
                    rules.append(parsed)

        for behavior in ("allow", "deny", "ask"):
            bucket = permissions.get(behavior)
            if not isinstance(bucket, list):
                continue
            for entry in bucket:
                parsed = self._parse_rule_entry(entry, default_behavior=behavior, source=source)
                if parsed is not None:
                    rules.append(parsed)

        return rules

    def _parse_rule_entry(
        self,
        entry: Any,
        *,
        default_behavior: str,
        source: str,
    ) -> Optional[PermissionRule]:
        behavior = self._normalize_behavior(default_behavior)

        if isinstance(entry, str):
            raw = entry.strip()
            if not raw:
                return None
            if ":" in raw:
                tool_name, _, rule_content = raw.partition(":")
            else:
                tool_name, rule_content = raw, ""
            return PermissionRule(
                tool_name=tool_name.strip().lower(),
                behavior=behavior,
                rule_content=rule_content.strip(),
                source=source,
            )

        if not isinstance(entry, dict):
            return None
        tool_name = str(entry.get("toolName") or entry.get("tool_name") or "").strip().lower()
        if not tool_name:
            return None
        explicit_behavior = entry.get("behavior")
        if isinstance(explicit_behavior, str) and explicit_behavior.strip():
            behavior = self._normalize_behavior(explicit_behavior)
        rule_content = str(entry.get("ruleContent") or entry.get("rule_content") or "").strip()
        return PermissionRule(
            tool_name=tool_name,
            behavior=behavior,
            rule_content=rule_content,
            source=source,
        )

    @staticmethod
    def _normalize_behavior(raw: str) -> str:
        behavior = str(raw or "").strip().lower()
        if behavior not in {"allow", "deny", "ask"}:
            return "ask"
        return behavior

    def _settings_path_for_scope(self, scope: str) -> Path:
        if scope == "user":
            return self.user_settings_path
        if scope == "project":
            return self.project_settings_path
        return self.local_settings_path

    @staticmethod
    def _read_settings_payload(path: Path) -> Dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _write_settings_payload(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
