"""Declarative YAML permission DSL."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from .command_validator import CommandRisk, get_command_validator


_STRICTNESS = {"allow": 0, "ask": 1, "deny": 2}
_TOOL_ALIASES = {"run_shell": "bash", "shell": "bash"}


@dataclass(frozen=True)
class PermissionDslRule:
    index: int
    tool: str
    when: Dict[str, Any]
    behavior: str
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "tool": self.tool,
            "when": dict(self.when),
            "behavior": self.behavior,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PermissionDslDecision:
    behavior: str
    rule: Optional[PermissionDslRule] = None
    reason: str = ""
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "behavior": self.behavior,
            "rule": self.rule.to_dict() if self.rule else None,
            "reason": self.reason,
            "errors": list(self.errors),
        }


class PermissionDsl:
    def __init__(self, repo_root: Optional[Path] = None, path: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.path = path or (self.repo_root / ".poor-cli" / "permissions.yml")
        self.labels_path = self.repo_root / ".poor-cli" / "labels.yml"
        self._rules: List[PermissionDslRule] = []
        self._errors: List[Dict[str, Any]] = []
        self._default_unmatched = "ask"
        self._loaded = False

    def load(self) -> None:
        self._loaded = True
        self._rules = []
        self._errors = []
        self._default_unmatched = "ask"
        if not self.path.is_file():
            return
        try:
            payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            self._errors.append({"path": str(self.path), "error": str(exc)})
            return
        if not isinstance(payload, dict):
            self._errors.append({"path": str(self.path), "error": "permissions file must be a mapping"})
            return
        defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
        self._default_unmatched = _normalize_behavior(defaults.get("unmatched") or "ask")
        raw_rules = payload.get("rules") or []
        if not isinstance(raw_rules, list):
            self._errors.append({"path": str(self.path), "error": "rules must be a list"})
            return
        for index, raw in enumerate(raw_rules):
            try:
                self._rules.append(_parse_rule(index, raw))
            except Exception as exc:
                self._errors.append({"path": str(self.path), "rule": index, "error": str(exc)})

    def show(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return {
            "path": str(self.path),
            "defaults": {"unmatched": self._default_unmatched},
            "rules": [rule.to_dict() for rule in self._rules],
            "errors": self.errors(),
        }

    def errors(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return list(self._errors)

    def evaluate(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[PermissionDslDecision]:
        self._ensure_loaded()
        if not self.path.is_file():
            return None
        ctx = dict(context or {})
        ctx.setdefault("repo_labels", self._load_repo_labels())
        for rule in self._rules:
            if not _tool_matches(rule.tool, tool_name):
                continue
            if _predicates_match(rule.when, tool_name, tool_args, ctx):
                return PermissionDslDecision(rule.behavior, rule=rule, reason=rule.reason, errors=self.errors())
        return PermissionDslDecision(self._default_unmatched, reason="unmatched", errors=self.errors())

    def explain(self, tool_name: str, tool_args: Dict[str, Any], *, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        decision = self.evaluate(tool_name, tool_args, context=context)
        return {
            "toolName": tool_name,
            "input": tool_args,
            "decision": decision.to_dict() if decision else None,
            "errors": self.errors(),
        }

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _load_repo_labels(self) -> List[str]:
        if not self.labels_path.is_file():
            return []
        try:
            payload = yaml.safe_load(self.labels_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return []
        if isinstance(payload, list):
            return [str(item) for item in payload]
        if isinstance(payload, dict):
            labels = payload.get("labels", [])
            if isinstance(labels, list):
                return [str(item) for item in labels]
            return [str(key) for key, value in payload.items() if bool(value)]
        return []


_MCP_MARKETPLACE_REASON = "newly installed MCP tool, awaiting review"
_MCP_MARKETPLACE_SOURCE = "mcp_marketplace"


def ensure_mcp_default_deny_rules(
    repo_root: Optional[Path],
    server_name: str,
    tool_names: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Add conservative deny rules for newly installed marketplace tools."""
    root = (repo_root or Path.cwd()).resolve()
    path = root / ".poor-cli" / "permissions.yml"
    payload = _load_permissions_payload(path)
    rules = payload.setdefault("rules", [])
    if not isinstance(rules, list):
        rules = []
        payload["rules"] = rules

    patterns = _mcp_tool_patterns(server_name, tool_names)
    existing = {
        str(rule.get("tool"))
        for rule in rules
        if isinstance(rule, dict)
        and rule.get("source") == _MCP_MARKETPLACE_SOURCE
        and str(rule.get("server") or "") == server_name
    }
    for pattern in patterns:
        if pattern in existing:
            continue
        rules.append({
            "tool": pattern,
            "deny": True,
            "reason": _MCP_MARKETPLACE_REASON,
            "source": _MCP_MARKETPLACE_SOURCE,
            "server": server_name,
        })
    _write_permissions_payload(path, payload)
    return {"path": str(path), "server": server_name, "rulesAdded": len(set(patterns) - existing)}


def remove_mcp_default_deny_rules(repo_root: Optional[Path], server_name: str) -> Dict[str, Any]:
    root = (repo_root or Path.cwd()).resolve()
    path = root / ".poor-cli" / "permissions.yml"
    payload = _load_permissions_payload(path)
    rules = payload.get("rules")
    if not isinstance(rules, list):
        return {"path": str(path), "server": server_name, "rulesRemoved": 0}
    kept = []
    removed = 0
    for rule in rules:
        if (
            isinstance(rule, dict)
            and rule.get("source") == _MCP_MARKETPLACE_SOURCE
            and str(rule.get("server") or "") == server_name
        ):
            removed += 1
            continue
        kept.append(rule)
    payload["rules"] = kept
    _write_permissions_payload(path, payload)
    return {"path": str(path), "server": server_name, "rulesRemoved": removed}


def combine_behaviors(left: str, right: str) -> str:
    a = _normalize_behavior(left)
    b = _normalize_behavior(right)
    return a if _STRICTNESS[a] >= _STRICTNESS[b] else b


def _parse_rule(index: int, raw: Any) -> PermissionDslRule:
    if not isinstance(raw, dict):
        raise ValueError("rule must be a mapping")
    tool = str(raw.get("tool") or "*").strip() or "*"
    when = raw.get("when") if isinstance(raw.get("when"), dict) else {}
    behavior_values = [name for name in ("allow", "deny", "ask") if name in raw]
    if len(behavior_values) != 1:
        raise ValueError("rule must set exactly one of allow, deny, ask")
    behavior = behavior_values[0] if bool(raw.get(behavior_values[0])) else "ask"
    _validate_predicates(when)
    return PermissionDslRule(
        index=index,
        tool=tool,
        when=dict(when),
        behavior=_normalize_behavior(behavior),
        reason=str(raw.get("reason") or "").strip(),
    )


def _validate_predicates(when: Dict[str, Any]) -> None:
    for pattern in _as_list(when.get("command_matches")):
        re.compile(str(pattern))


def _predicates_match(when: Dict[str, Any], tool_name: str, tool_args: Dict[str, Any], context: Dict[str, Any]) -> bool:
    if not when:
        return True
    checks = []
    if "path_matches" in when:
        paths = _extract_paths(tool_args)
        patterns = [str(pattern) for pattern in _as_list(when.get("path_matches"))]
        checks.append(bool(paths) and any(fnmatch(path, pattern) for path in paths for pattern in patterns))
    if "command_matches" in when:
        command = _extract_command(tool_name, tool_args)
        checks.append(any(re.search(str(pattern), command) for pattern in _as_list(when.get("command_matches"))))
    if "command_class" in when:
        checks.append(_command_class_matches(str(when.get("command_class")), _extract_command(tool_name, tool_args)))
    if "provider_in" in when:
        checks.append(str(context.get("provider", "")) in {str(item) for item in _as_list(when.get("provider_in"))})
    if "model_in" in when:
        checks.append(str(context.get("model", "")) in {str(item) for item in _as_list(when.get("model_in"))})
    if "agent_name" in when:
        agent = str(tool_args.get("agent") or tool_args.get("agent_name") or "")
        checks.append(agent == str(when.get("agent_name")))
    if "repo_label" in when:
        checks.append(str(when.get("repo_label")) in {str(label) for label in context.get("repo_labels", [])})
    return bool(checks) and all(checks)


def _extract_paths(tool_args: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    for key in ("path", "file_path", "source", "destination", "target", "repo_path"):
        value = tool_args.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    for key in ("paths", "files", "context_files"):
        value = tool_args.get(key)
        if isinstance(value, list):
            paths.extend(str(item) for item in value if str(item))
    return paths


def _extract_command(tool_name: str, tool_args: Dict[str, Any]) -> str:
    if _canonical_tool(tool_name) != "bash":
        return ""
    return str(tool_args.get("command") or tool_args.get("cmd") or tool_args.get("input") or "")


def _command_class_matches(expected: str, command: str) -> bool:
    if not command:
        return False
    risk = get_command_validator(strict_mode=False).validate(command).risk_level
    expected_norm = expected.strip().lower()
    if expected_norm == "destructive":
        return risk in {CommandRisk.HIGH, CommandRisk.CRITICAL}
    return risk.value == expected_norm


def _tool_matches(rule_tool: str, actual_tool: str) -> bool:
    rule = _canonical_tool(rule_tool)
    actual = _canonical_tool(actual_tool)
    return rule == "*" or fnmatch(actual, rule)


def _canonical_tool(value: str) -> str:
    text = str(value or "").strip()
    return _TOOL_ALIASES.get(text, text)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _normalize_behavior(value: Any) -> str:
    text = str(value or "ask").strip().lower()
    if text not in _STRICTNESS:
        raise ValueError("behavior must be allow, deny, or ask")
    return text


def _load_permissions_payload(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "defaults": {"unmatched": "ask"}, "rules": []}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("version", 1)
    payload.setdefault("defaults", {"unmatched": "ask"})
    payload.setdefault("rules", [])
    return payload


def _write_permissions_payload(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _mcp_tool_patterns(server_name: str, tool_names: Sequence[str] | None) -> List[str]:
    server = str(server_name or "").strip()
    names = [str(name).strip() for name in (tool_names or []) if str(name).strip()]
    if names:
        return names
    return [f"{server}:*", f"mcp__{server}__*"]


def input_from_cli(tool_name: str, raw: str) -> Dict[str, Any]:
    text = str(raw or "")
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    if _canonical_tool(tool_name) == "bash":
        return {"command": text}
    return {"path": text}
