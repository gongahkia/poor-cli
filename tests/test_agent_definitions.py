from pathlib import Path
from unittest.mock import MagicMock

from poor_cli.agent_definitions import AgentDefinitionRegistry, effective_allowed_tools
from poor_cli.sub_agent import SubAgent


AVAILABLE_TOOLS = {
    "read_file",
    "glob_files",
    "grep_files",
    "list_directory",
    "git_status",
    "git_diff",
    "git_log",
    "semantic_search",
    "write_file",
    "edit_file",
    "bash",
    "delegate_task",
    "spawn_parallel_agents",
}


def _write_agent(root: Path, name: str, text: str) -> Path:
    path = root / ".poor-cli" / "agents" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_round_trip_parse_sample_definitions():
    registry = AgentDefinitionRegistry(Path.cwd(), available_tools=AVAILABLE_TOOLS)
    names = {definition.name for definition in registry.list()}

    assert {"researcher", "security-reviewer"}.issubset(names)
    assert registry.errors() == []
    security = registry.get("security-reviewer")
    assert security is not None
    assert security.provider == "anthropic"
    assert security.max_output_tokens == 2048
    assert "security review subagent" in security.system_prompt


def test_invalid_frontmatter_records_error_and_skips_registration(tmp_path):
    _write_agent(
        tmp_path,
        "bad-name",
        "---\nname: Bad_Name\nallowed_tools:\n  - read_file\n---\nPrompt",
    )

    registry = AgentDefinitionRegistry(tmp_path, available_tools=AVAILABLE_TOOLS)

    assert registry.get("Bad_Name") is None
    assert registry.list() == []
    assert "invalid agent name" in registry.errors()[0]["error"]


def test_name_must_match_filename_stem(tmp_path):
    _write_agent(
        tmp_path,
        "researcher",
        "---\nname: security-reviewer\nallowed_tools:\n  - read_file\n---\nPrompt",
    )

    registry = AgentDefinitionRegistry(tmp_path, available_tools=AVAILABLE_TOOLS)

    assert registry.list() == []
    assert "must match filename stem" in registry.errors()[0]["error"]


def test_tool_whitelist_intersects_with_denies_and_hard_deny(tmp_path):
    path = _write_agent(
        tmp_path,
        "writer",
        (
            "---\n"
            "name: writer\n"
            "allowed_tools:\n"
            "  - read_file\n"
            "  - write_file\n"
            "  - delegate_task\n"
            "denied_tools:\n"
            "  - write_file\n"
            "---\n"
            "Prompt"
        ),
    )
    definition = AgentDefinitionRegistry.parse(path)

    assert effective_allowed_tools(definition, AVAILABLE_TOOLS) == {"read_file"}


def test_custom_agent_definition_filters_subagent_tools(tmp_path):
    _write_agent(
        tmp_path,
        "reviewer",
        (
            "---\n"
            "name: reviewer\n"
            "allowed_tools:\n"
            "  - read_file\n"
            "  - write_file\n"
            "denied_tools:\n"
            "  - write_file\n"
            "---\n"
            "Review prompt"
        ),
    )
    definition = AgentDefinitionRegistry(tmp_path, available_tools=AVAILABLE_TOOLS).get("reviewer")
    parent = MagicMock()
    parent.config.agentic.sub_agent_max_depth = 2
    parent.config.agentic.sub_agent_max_iterations = 10
    parent.config.agentic.sub_agent_timeout = 120
    parent.config.agentic.sub_agent_max_input_tokens = 40000
    parent.config.agentic.sub_agent_max_output_tokens = 12000
    parent.config.agentic.sub_agent_max_cost_usd = 0.5
    parent.config.agentic.sub_agent_default_denied_tools = ["write_file"]
    parent._sub_agent_depth = 0
    parent.tool_registry.get_tool_declarations.return_value = [{"name": name} for name in sorted(AVAILABLE_TOOLS)]

    agent = SubAgent(parent, agent_definition=definition)

    names = {tool["name"] for tool in agent._resolve_filtered_tools()}
    assert names == {"read_file"}
