from pathlib import Path

from poor_cli.sandbox import (
    ToolCapability,
    evaluate_tool_access,
    permission_mode_from_preset,
    preset_from_permission_mode,
)


def test_permission_mode_and_preset_aliases_round_trip():
    assert preset_from_permission_mode("prompt") == "workspace-write"
    assert preset_from_permission_mode("danger-full-access") == "full-access"
    assert permission_mode_from_preset("review-only") == "auto-safe"
    assert permission_mode_from_preset("full-access") == "danger-full-access"


def test_workspace_write_requires_approval_for_mutations(tmp_path: Path):
    decision = evaluate_tool_access(
        tool_name="write_file",
        tool_args={"file_path": str(tmp_path / "note.txt")},
        tool_capabilities=[ToolCapability.FILESYSTEM_WRITE.value],
        permission_mode="prompt",
        sandbox_preset="workspace-write",
        trusted_roots=[tmp_path],
        mutation_paths=[str(tmp_path / "note.txt")],
    )

    assert decision.allowed is True
    assert decision.requires_approval is True


def test_read_only_preset_denies_mutations(tmp_path: Path):
    decision = evaluate_tool_access(
        tool_name="write_file",
        tool_args={"file_path": str(tmp_path / "note.txt")},
        tool_capabilities=[ToolCapability.FILESYSTEM_WRITE.value],
        permission_mode="prompt",
        sandbox_preset="read-only",
        trusted_roots=[tmp_path],
        mutation_paths=[str(tmp_path / "note.txt")],
    )

    assert decision.allowed is False
    assert "not allowed" in decision.reason


def test_review_only_safe_process_mode_blocks_non_allowlisted_commands(tmp_path: Path):
    safe = evaluate_tool_access(
        tool_name="bash",
        tool_args={"command": "pwd"},
        tool_capabilities=[ToolCapability.PROCESS_EXECUTE.value],
        permission_mode="prompt",
        sandbox_preset="review-only",
        trusted_roots=[tmp_path],
        mutation_paths=[],
    )
    unsafe = evaluate_tool_access(
        tool_name="bash",
        tool_args={"command": "touch demo.txt"},
        tool_capabilities=[ToolCapability.PROCESS_EXECUTE.value],
        permission_mode="prompt",
        sandbox_preset="review-only",
        trusted_roots=[tmp_path],
        mutation_paths=[],
    )

    assert safe.allowed is True
    assert unsafe.allowed is False
    assert "safe-process mode" in unsafe.reason


def test_safe_process_mode_uses_configured_safe_commands(tmp_path: Path):
    decision = evaluate_tool_access(
        tool_name="bash",
        tool_args={"command": "git status"},
        tool_capabilities=[ToolCapability.PROCESS_EXECUTE.value],
        permission_mode="auto-safe",
        sandbox_preset="workspace-write",
        trusted_roots=[tmp_path],
        mutation_paths=[],
        safe_process_commands=["git status"],
    )

    assert decision.allowed is True


def test_trusted_workspace_boundary_can_be_disabled(tmp_path: Path):
    decision = evaluate_tool_access(
        tool_name="write_file",
        tool_args={"file_path": str(tmp_path.parent / "note.txt")},
        tool_capabilities=[ToolCapability.FILESYSTEM_WRITE.value],
        permission_mode="prompt",
        sandbox_preset="workspace-write",
        trusted_roots=[tmp_path],
        mutation_paths=[str(tmp_path.parent / "note.txt")],
        enforce_trusted_workspace=False,
    )

    assert decision.allowed is True
    assert decision.requires_approval is True
