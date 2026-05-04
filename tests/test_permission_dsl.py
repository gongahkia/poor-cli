from pathlib import Path

from poor_cli.permission_dsl import PermissionDsl, combine_behaviors
from poor_cli.permission_rules import PermissionRuleEngine


def _write_permissions(root: Path, text: str) -> None:
    path = root / ".poor-cli" / "permissions.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_path_matches_allow_and_deny(tmp_path):
    _write_permissions(
        tmp_path,
        """
version: 1
defaults:
  unmatched: ask
rules:
  - tool: write_file
    when:
      path_matches: ["src/**"]
    allow: true
  - tool: write_file
    when:
      path_matches: ["infra/**"]
    deny: true
""",
    )
    dsl = PermissionDsl(tmp_path)

    assert dsl.evaluate("write_file", {"file_path": "src/app.py"}).behavior == "allow"
    assert dsl.evaluate("write_file", {"file_path": "infra/ci.yml"}).behavior == "deny"
    assert dsl.evaluate("write_file", {"file_path": "README.md"}).behavior == "ask"


def test_command_matches_and_command_class(tmp_path):
    _write_permissions(
        tmp_path,
        """
version: 1
rules:
  - tool: run_shell
    when:
      command_matches: ['^pytest(\\s|$)']
    allow: true
  - tool: run_shell
    when:
      command_class: destructive
    deny: true
""",
    )
    dsl = PermissionDsl(tmp_path)

    assert dsl.evaluate("bash", {"command": "pytest tests"}).behavior == "allow"
    assert dsl.evaluate("bash", {"command": "rm -rf build"}).behavior == "deny"


def test_provider_model_agent_and_repo_label_predicates(tmp_path):
    _write_permissions(
        tmp_path,
        """
version: 1
rules:
  - tool: "*"
    when:
      provider_in: ["openai"]
      model_in: ["gpt-test"]
      repo_label: internal-only
    deny: true
  - tool: delegate_task
    when:
      agent_name: security-reviewer
    allow: true
""",
    )
    labels = tmp_path / ".poor-cli" / "labels.yml"
    labels.write_text("labels:\n  - internal-only\n", encoding="utf-8")
    dsl = PermissionDsl(tmp_path)

    assert dsl.evaluate("read_file", {}, context={"provider": "openai", "model": "gpt-test"}).behavior == "deny"
    assert dsl.evaluate("delegate_task", {"agent": "security-reviewer"}).behavior == "allow"


def test_composition_strictness_helpers():
    assert combine_behaviors("allow", "deny") == "deny"
    assert combine_behaviors("ask", "allow") == "ask"
    assert combine_behaviors("allow", "allow") == "allow"


def test_permission_rules_engine_composes_with_dsl(tmp_path):
    _write_permissions(
        tmp_path,
        """
version: 1
rules:
  - tool: write_file
    when:
      path_matches: ["src/**"]
    deny: true
""",
    )
    engine = PermissionRuleEngine(tmp_path)
    engine.add_session_rule("write_file", "allow", "*")

    match = engine.evaluate("write_file", {"file_path": "src/app.py"})

    assert match is not None
    assert match.behavior == "deny"


def test_bad_regex_surfaces_parse_error_without_crashing(tmp_path):
    _write_permissions(
        tmp_path,
        """
version: 1
rules:
  - tool: run_shell
    when:
      command_matches: ["["]
    allow: true
""",
    )
    dsl = PermissionDsl(tmp_path)

    decision = dsl.evaluate("bash", {"command": "pytest"})

    assert decision is not None
    assert decision.behavior == "ask"
    assert dsl.errors()


def test_explain_returns_matched_rule_details(tmp_path):
    _write_permissions(
        tmp_path,
        """
version: 1
rules:
  - tool: delegate_task
    when:
      agent_name: security-reviewer
    allow: true
    reason: "security reviewer is approved"
""",
    )
    dsl = PermissionDsl(tmp_path)

    explanation = dsl.explain("delegate_task", {"agent": "security-reviewer"})

    assert explanation["decision"]["behavior"] == "allow"
    assert explanation["decision"]["rule"]["tool"] == "delegate_task"
    assert explanation["decision"]["reason"] == "security reviewer is approved"
