"""Structured arg matchers for Phase-C T7 permission rules.

A matcher is a small dict like ``{"equals": "main"}`` or
``{"one_of": ["dev", "staging"]}``. It evaluates against a scalar arg value
drawn from the handler's structured args by path.

This replaces the stringified-args regex scheme where rules matched
``vim.inspect(args)``. Old-style rules with only a ``pattern`` field still
work via ``legacy_pattern_match`` so deployed policies don't break.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence


_MATCHER_KEYS = {
    "equals", "contains", "matches_regex", "one_of",
    "greater_than", "less_than", "starts_with", "ends_with",
}


def _get_path(args: Mapping[str, Any], path: str) -> Any:
    """Walk ``args`` by dot-separated path. Returns ``_MISSING`` if any
    segment doesn't exist so the caller can distinguish 'arg is None' from
    'arg not provided'."""
    current: Any = args
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


_MISSING = object()


def _match_scalar(matcher: Mapping[str, Any], value: Any) -> bool:
    """Evaluate a matcher dict against a single arg value. Unknown keys
    count as non-matching (safe default)."""
    if "equals" in matcher:
        return value == matcher["equals"]
    if "one_of" in matcher:
        return value in (matcher["one_of"] or [])
    if "contains" in matcher:
        if value is None:
            return False
        return str(matcher["contains"]) in str(value)
    if "starts_with" in matcher:
        return str(value or "").startswith(str(matcher["starts_with"]))
    if "ends_with" in matcher:
        return str(value or "").endswith(str(matcher["ends_with"]))
    if "matches_regex" in matcher:
        pattern = matcher["matches_regex"]
        if value is None:
            return False
        try:
            return re.search(pattern, str(value)) is not None
        except re.error:
            return False
    if "greater_than" in matcher:
        try:
            return float(value) > float(matcher["greater_than"])
        except (TypeError, ValueError):
            return False
    if "less_than" in matcher:
        try:
            return float(value) < float(matcher["less_than"])
        except (TypeError, ValueError):
            return False
    return False


def match_args(args_match: Mapping[str, Any], args: Mapping[str, Any]) -> bool:
    """Return True iff every ``path → matcher`` entry in ``args_match``
    evaluates to True against ``args``. Missing path always fails the match
    for that key — rules should declare ``{"equals": None}`` if they want
    to require absence of an arg explicitly (handled via _get_path).

    An empty ``args_match`` evaluates to True (matches any args)."""
    if not args_match:
        return True
    for path, matcher in args_match.items():
        if not isinstance(matcher, Mapping):
            return False
        value = _get_path(args, path)
        if value is _MISSING:
            # Special case: equals:None still matches a truly-missing arg
            if matcher.get("equals", _MISSING) is None:
                continue
            return False
        if not _match_scalar(matcher, value):
            return False
    return True


def legacy_pattern_match(pattern: str, args: Mapping[str, Any]) -> bool:
    """Backward-compat shim. Matches ``pattern`` against ``repr(args)`` with
    shell-glob-style ``*`` wildcards. Returns True iff the pattern matches."""
    if not pattern:
        return True
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    try:
        return re.search(regex, repr(args)) is not None
    except re.error:
        return False


def evaluate_rules(
    rules: Sequence[Mapping[str, Any]],
    *,
    tool: str,
    args: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Walk the rule list top-to-bottom; first match wins. Returns the
    matched rule (so callers have the outcome field) or an empty dict if
    no rule matched."""
    for rule in rules:
        rule_tool = rule.get("tool") or rule.get("toolName")
        if rule_tool and rule_tool != tool and rule_tool != "*":
            continue
        # New-style matcher
        am = rule.get("args_match")
        if am is not None:
            if match_args(am, args):
                return rule
            continue
        # Legacy pattern
        pattern = rule.get("pattern")
        if pattern is not None:
            if legacy_pattern_match(pattern, args):
                return rule
            continue
        # Rule has only a tool (no matchers) → matches any args.
        return rule
    return {}
