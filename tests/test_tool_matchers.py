"""Tests for poor_cli.tool_matchers (T7)."""

from __future__ import annotations

import pytest

from poor_cli.tool_matchers import (
    evaluate_rules,
    legacy_pattern_match,
    match_args,
)


# ──────────────── match_args ────────────────


def test_empty_matcher_matches_anything():
    assert match_args({}, {"foo": 1})
    assert match_args({}, {})


def test_equals_matches_scalar():
    assert match_args({"branch": {"equals": "main"}}, {"branch": "main"})
    assert not match_args({"branch": {"equals": "main"}}, {"branch": "dev"})


def test_one_of():
    rule = {"env": {"one_of": ["dev", "staging"]}}
    assert match_args(rule, {"env": "dev"})
    assert not match_args(rule, {"env": "prod"})


def test_contains_scalar_and_stringified():
    rule = {"cmd": {"contains": "rm -rf"}}
    assert match_args(rule, {"cmd": "shell: rm -rf /"})
    assert not match_args(rule, {"cmd": "ls"})


def test_starts_with_ends_with():
    assert match_args({"path": {"starts_with": "/tmp/"}}, {"path": "/tmp/a"})
    assert match_args({"path": {"ends_with": ".py"}}, {"path": "x.py"})
    assert not match_args({"path": {"starts_with": "/var"}}, {"path": "/tmp"})


def test_regex_matcher():
    rule = {"branch": {"matches_regex": r"^release/\d+$"}}
    assert match_args(rule, {"branch": "release/42"})
    assert not match_args(rule, {"branch": "main"})


def test_regex_invalid_pattern_returns_false():
    rule = {"x": {"matches_regex": "(unclosed"}}
    assert not match_args(rule, {"x": "anything"})


def test_greater_less_than_numeric():
    assert match_args({"n": {"greater_than": 5}}, {"n": 10})
    assert not match_args({"n": {"greater_than": 5}}, {"n": 5})
    assert match_args({"n": {"less_than": 5}}, {"n": 3})


def test_dot_path():
    rule = {"target.name": {"equals": "prod"}}
    assert match_args(rule, {"target": {"name": "prod"}})
    assert not match_args(rule, {"target": {"name": "dev"}})


def test_missing_arg_does_not_match():
    rule = {"branch": {"equals": "main"}}
    assert not match_args(rule, {"ref": "main"})


def test_all_keys_must_match():
    rule = {
        "branch": {"equals": "main"},
        "force": {"equals": True},
    }
    assert match_args(rule, {"branch": "main", "force": True})
    assert not match_args(rule, {"branch": "main", "force": False})


# ──────────────── legacy_pattern_match ────────────────


def test_legacy_pattern_glob():
    assert legacy_pattern_match("*rm -rf*", {"cmd": "rm -rf /"})
    assert not legacy_pattern_match("*rm -rf*", {"cmd": "ls"})


def test_legacy_pattern_empty_matches_anything():
    assert legacy_pattern_match("", {"x": 1})


# ──────────────── evaluate_rules ────────────────


def test_first_matching_rule_wins():
    rules = [
        {"tool": "git.push", "args_match": {"branch": {"equals": "main"}}, "outcome": "deny"},
        {"tool": "git.push", "args_match": {"force": {"equals": True}}, "outcome": "prompt"},
        {"tool": "git.push", "outcome": "allow"},
    ]
    # first rule matches — deny wins
    rule = evaluate_rules(rules, tool="git.push", args={"branch": "main"})
    assert rule["outcome"] == "deny"
    # second rule matches when force=True and branch != main
    rule = evaluate_rules(rules, tool="git.push", args={"branch": "dev", "force": True})
    assert rule["outcome"] == "prompt"
    # fallthrough → third rule
    rule = evaluate_rules(rules, tool="git.push", args={"branch": "dev"})
    assert rule["outcome"] == "allow"


def test_tool_filter_skips_other_tools():
    rules = [
        {"tool": "git.push", "args_match": {"branch": {"equals": "main"}}, "outcome": "deny"},
        {"tool": "git.status", "outcome": "allow"},
    ]
    rule = evaluate_rules(rules, tool="git.status", args={})
    assert rule["outcome"] == "allow"


def test_wildcard_tool_matches_any():
    rules = [{"tool": "*", "args_match": {}, "outcome": "prompt"}]
    rule = evaluate_rules(rules, tool="anything.here", args={"x": 1})
    assert rule["outcome"] == "prompt"


def test_no_match_returns_empty():
    rules = [
        {"tool": "git.push", "args_match": {"branch": {"equals": "main"}}, "outcome": "deny"},
    ]
    assert evaluate_rules(rules, tool="git.status", args={}) == {}


def test_legacy_pattern_field_still_works():
    rules = [
        {"tool": "bash", "pattern": "*rm -rf*", "outcome": "deny"},
        {"tool": "bash", "outcome": "allow"},
    ]
    rule = evaluate_rules(rules, tool="bash", args={"cmd": "rm -rf /"})
    assert rule["outcome"] == "deny"
    rule = evaluate_rules(rules, tool="bash", args={"cmd": "ls"})
    assert rule["outcome"] == "allow"
