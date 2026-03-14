import json
from unittest.mock import AsyncMock, patch

import pytest

import poor_cli.web_search as web_search_module
from poor_cli.exceptions import FileOperationError, ValidationError
from poor_cli.tools_async import ToolRegistryAsync


def test_github_tools_registered_only_when_gh_exists():
    with patch("poor_cli.tools_async.shutil.which", return_value=None):
        registry = ToolRegistryAsync()
        assert "gh_pr_list" not in registry.tools
        assert "web_search" in registry.tools

    with patch("poor_cli.tools_async.shutil.which", return_value="/usr/bin/gh"):
        registry = ToolRegistryAsync()
        assert "gh_pr_list" in registry.tools
        assert "gh_pr_view" in registry.tools


def test_extended_tools_are_registered():
    registry = ToolRegistryAsync()
    for tool_name in {
        "run_tests",
        "git_status_diff",
        "apply_patch_unified",
        "format_and_lint",
        "dependency_inspect",
        "fetch_url",
        "json_yaml_edit",
        "process_logs",
    }:
        assert tool_name in registry.tools


@pytest.mark.asyncio
async def test_web_search_uses_brave_when_key_present():
    registry = ToolRegistryAsync()
    with (
        patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "abc"}, clear=False),
        patch.object(web_search_module, "brave_search", AsyncMock(return_value="brave result")) as mock_brave,
    ):
        result = await registry.web_search("latest updates")
    assert result == "brave result"
    mock_brave.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_search_falls_back_to_duckduckgo():
    registry = ToolRegistryAsync()
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(web_search_module, "duckduckgo_search", AsyncMock(return_value="ddg result")) as mock_ddg,
    ):
        result = await registry.web_search("latest updates")
    assert result == "ddg result"
    mock_ddg.assert_awaited_once()


@pytest.mark.asyncio
async def test_json_yaml_edit_updates_json_file(tmp_path):
    registry = ToolRegistryAsync()
    config_path = tmp_path / "config.json"
    config_path.write_text('{"api":{"timeout":5}}', encoding="utf-8")

    result = await registry.json_yaml_edit(
        file_path=str(config_path),
        updates_json='{"api.timeout": 10, "feature.enabled": true}',
    )

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated["api"]["timeout"] == 10
    assert updated["feature"]["enabled"] is True
    assert result.ok is True
    assert result.operation == "json_yaml_edit"
    assert result.changed is True
    assert result.diff.startswith("---")


@pytest.mark.asyncio
async def test_write_file_returns_structured_diff(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "notes.txt"

    result = await registry.write_file(str(target), "hello\nworld\n")

    assert target.read_text(encoding="utf-8") == "hello\nworld\n"
    assert result.ok is True
    assert result.operation == "write_file"
    assert result.changed is True
    assert result.metadata["created"] is True
    assert "+hello" in result.diff


@pytest.mark.asyncio
async def test_edit_file_exact_match_returns_structured_diff(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("print('old')\n", encoding="utf-8")

    result = await registry.edit_file(
        file_path=str(target),
        old_text="print('old')",
        new_text="print('new')",
    )

    assert target.read_text(encoding="utf-8") == "print('new')\n"
    assert result.ok is True
    assert result.operation == "edit_file"
    assert result.metadata["mode"] == "exact_replace"
    assert "-print('old')" in result.diff
    assert "+print('new')" in result.diff


@pytest.mark.asyncio
async def test_edit_file_rejects_missing_match(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="Text not found in file"):
        await registry.edit_file(
            file_path=str(target),
            old_text="beta",
            new_text="gamma",
        )


@pytest.mark.asyncio
async def test_edit_file_rejects_multiple_matches(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("dup\ndup\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="multiple matches found"):
        await registry.edit_file(
            file_path=str(target),
            old_text="dup",
            new_text="done",
        )


@pytest.mark.asyncio
async def test_edit_file_line_range_returns_structured_diff(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = await registry.edit_file(
        file_path=str(target),
        start_line=2,
        end_line=2,
        new_text="delta\n",
    )

    assert target.read_text(encoding="utf-8") == "alpha\ndelta\ngamma\n"
    assert result.changed is True
    assert result.metadata["mode"] == "line_range"
    assert "-beta" in result.diff
    assert "+delta" in result.diff


@pytest.mark.asyncio
async def test_preview_mutation_does_not_write_file(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "notes.txt"

    result = await registry.preview_mutation(
        "write_file",
        {"file_path": str(target), "content": "preview only\n"},
    )

    assert result.ok is True
    assert result.operation == "write_file"
    assert result.changed is True
    assert result.metadata["preview"] is True
    assert not target.exists()


@pytest.mark.asyncio
async def test_write_file_preserves_original_content_when_atomic_replace_fails(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "notes.txt"
    target.write_text("stable\n", encoding="utf-8")

    with patch("poor_cli.tools_async.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(FileOperationError, match="Failed to write file"):
            await registry.write_file(str(target), "changed\n")

    assert target.read_text(encoding="utf-8") == "stable\n"


@pytest.mark.asyncio
async def test_apply_patch_unified_check_only_returns_structured_outcome(tmp_path):
    registry = ToolRegistryAsync()
    patch_text = """diff --git a/demo.txt b/demo.txt
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-old
+new
"""

    with patch.object(
        registry,
        "_run_command_capture",
        AsyncMock(
            return_value={
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }
        ),
    ):
        result = await registry.apply_patch_unified(
            patch=patch_text,
            path=str(tmp_path),
            check_only=True,
        )

    assert result.ok is True
    assert result.operation == "apply_patch_unified"
    assert result.changed is False
    assert result.metadata["check_only"] is True
    assert result.metadata["paths"] == [str((tmp_path / "demo.txt").resolve())]


def test_narrow_mutation_arguments_filters_patch_to_selected_file(tmp_path):
    registry = ToolRegistryAsync()
    patch_text = """diff --git a/demo.txt b/demo.txt
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-old
+new
diff --git a/other.txt b/other.txt
--- a/other.txt
+++ b/other.txt
@@ -1 +1 @@
-left
+right
"""

    narrowed = registry.narrow_mutation_arguments(
        "apply_patch_unified",
        {"patch": patch_text, "path": str(tmp_path)},
        [str((tmp_path / "other.txt").resolve())],
    )

    assert "demo.txt" not in narrowed["patch"]
    assert "other.txt" in narrowed["patch"]


def test_narrow_mutation_arguments_filters_patch_to_selected_hunk(tmp_path):
    registry = ToolRegistryAsync()
    patch_text = """diff --git a/demo.txt b/demo.txt
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-old
+new
@@ -4 +4 @@
-left
+right
"""

    narrowed = registry.narrow_mutation_arguments(
        "apply_patch_unified",
        {"patch": patch_text, "path": str(tmp_path)},
        [],
        [{"path": str((tmp_path / "demo.txt").resolve()), "index": 1}],
    )

    assert "@@ -1 +1 @@" not in narrowed["patch"]
    assert "@@ -4 +4 @@" in narrowed["patch"]


@pytest.mark.asyncio
async def test_process_logs_summarizes_errors(tmp_path):
    registry = ToolRegistryAsync()
    log_file = tmp_path / "app.log"
    log_file.write_text(
        "2026-03-03 10:00:00 INFO startup complete\n"
        "2026-03-03 10:01:00 ERROR db timeout after 30s\n"
        "2026-03-03 10:01:05 ERROR db timeout after 31s\n",
        encoding="utf-8",
    )

    summary = json.loads(await registry.process_logs(path=str(log_file)))

    assert summary["lines_analyzed"] >= 3
    assert summary["level_counts"]["error"] >= 2
    assert summary["top_errors"]


@pytest.mark.asyncio
async def test_run_tests_returns_structured_payload():
    registry = ToolRegistryAsync()
    with patch.object(
        registry,
        "_run_command_capture",
        AsyncMock(
            return_value={
                "stdout": "FAILED tests/test_x.py::test_case - assertion\n",
                "stderr": "",
                "exit_code": 1,
                "timed_out": False,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }
        ),
    ):
        payload = json.loads(await registry.run_tests(command="pytest tests/ -v"))

    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["command"].startswith("pytest")


@pytest.mark.asyncio
async def test_git_status_diff_returns_risk_hints():
    registry = ToolRegistryAsync()
    sequence = [
        {
            "stdout": "/repo\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        },
        {
            "stdout": "M  .github/workflows/tests.yml\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        },
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
        {"stdout": "", "stderr": "", "exit_code": 0, "timed_out": False, "stdout_truncated": False, "stderr_truncated": False},
    ]

    with patch.object(registry, "_run_command_capture", AsyncMock(side_effect=sequence)):
        payload = json.loads(await registry.git_status_diff())

    assert payload["repository_root"] == "/repo"
    assert payload["risk_hints"]


@pytest.mark.asyncio
async def test_git_status_uses_cwd_not_shell_string(tmp_path):
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "On branch main\nnothing to commit, working tree clean\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }

    with patch.object(
        registry,
        "_run_command_capture",
        AsyncMock(return_value=result_payload),
    ) as mock_capture:
        output = await registry.git_status(path=str(tmp_path))

    assert "On branch main" in output
    mock_capture.assert_awaited_once_with(
        ["git", "status"],
        timeout=30,
        cwd=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_git_diff_passes_pathspec_as_argv(tmp_path):
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "diff --git a/app.py b/app.py\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }

    with patch.object(
        registry,
        "_run_command_capture",
        AsyncMock(return_value=result_payload),
    ) as mock_capture:
        output = await registry.git_diff(path=str(tmp_path), file_path="app.py")

    assert output.startswith("diff --git")
    mock_capture.assert_awaited_once_with(
        ["git", "diff", "--", "app.py"],
        timeout=30,
        cwd=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_fetch_url_blocks_private_hosts():
    registry = ToolRegistryAsync()
    with pytest.raises(ValidationError):
        await registry.fetch_url("http://127.0.0.1:8080")
