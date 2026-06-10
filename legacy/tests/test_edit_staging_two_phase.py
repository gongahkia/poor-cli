import json

import pytest

from poor_cli.config import Config
from poor_cli.edit_staging import EditStage
from poor_cli.tools_async import ToolRegistryAsync


@pytest.mark.asyncio
async def test_write_file_stages_without_touching_disk(tmp_path):
    path = tmp_path / "demo.txt"
    registry = ToolRegistryAsync()

    result = await registry.write_file(str(path), "hello\n", _tool_call_id="call-1", _prompt="write demo")

    assert result.ok is True
    assert result.changed is False
    assert result.metadata["status"] == "staged"
    assert result.metadata["staged"] is True
    assert result.metadata["editId"]
    assert not path.exists()


@pytest.mark.asyncio
async def test_execute_tool_json_exposes_staged_status_at_top_level(tmp_path):
    path = tmp_path / "demo.txt"
    registry = ToolRegistryAsync()

    payload = json.loads(await registry.execute_tool("write_file", {"file_path": str(path), "content": "hello\n"}))

    assert payload["status"] == "staged"
    assert payload["editId"]
    assert payload["metadata"]["status"] == "staged"
    assert not path.exists()


@pytest.mark.asyncio
async def test_approving_staged_write_commits_file(tmp_path):
    path = tmp_path / "demo.txt"
    registry = ToolRegistryAsync()

    result = await registry.write_file(str(path), "hello\n")
    edit_id = result.metadata["editId"]
    committed = registry.edit_stage.commit_or_reject(edit_id, "approve")

    assert committed["status"] == "accepted"
    assert committed["finalized"] is True
    assert path.read_text(encoding="utf-8") == "hello\n"


@pytest.mark.asyncio
async def test_rejecting_staged_write_leaves_file_untouched(tmp_path):
    path = tmp_path / "demo.txt"
    path.write_text("before\n", encoding="utf-8")
    registry = ToolRegistryAsync()

    result = await registry.write_file(str(path), "after\n")
    edit_id = result.metadata["editId"]
    rejected = registry.edit_stage.commit_or_reject(edit_id, "reject")

    assert rejected["status"] == "rejected"
    assert rejected["finalized"] is True
    assert path.read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
async def test_concurrent_staged_edits_different_paths_are_independent(tmp_path):
    one = tmp_path / "one.txt"
    two = tmp_path / "two.txt"
    one.write_text("one\n", encoding="utf-8")
    two.write_text("two\n", encoding="utf-8")
    registry = ToolRegistryAsync()

    first = await registry.write_file(str(one), "ONE\n")
    second = await registry.write_file(str(two), "TWO\n")
    registry.edit_stage.commit_or_reject(first.metadata["editId"], "approve")
    registry.edit_stage.commit_or_reject(second.metadata["editId"], "reject")

    assert one.read_text(encoding="utf-8") == "ONE\n"
    assert two.read_text(encoding="utf-8") == "two\n"


def test_mandatory_stage_blocks_unapproved_bypass(tmp_path):
    stage = EditStage()
    stage.set_mandatory(True)

    with pytest.raises(RuntimeError, match="mandatory diff preview"):
        stage.assert_can_bypass(str(tmp_path / "demo.txt"))


@pytest.mark.asyncio
async def test_auto_approve_edits_applies_immediately(tmp_path):
    path = tmp_path / "demo.txt"
    config = Config()
    config.agentic.auto_approve_edits = True
    registry = ToolRegistryAsync()
    registry.config = config

    result = await registry.write_file(str(path), "hello\n")

    assert result.changed is True
    assert result.metadata.get("staged") is not True
    assert path.read_text(encoding="utf-8") == "hello\n"
    assert any(event["operation"] == "diff.auto_approve" for event in registry.edit_stage.audit_events)
