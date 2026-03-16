import json
from unittest.mock import AsyncMock, patch

import pytest

import poor_cli.web_search as web_search_module
from poor_cli.exceptions import FileOperationError, ToolExecutionError, ValidationError
from poor_cli.tools_async import ToolRegistryAsync


class _FakeAioHttpStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def iter_chunked(self, _size):
        for chunk in self._chunks:
            yield chunk


class _FakeAioHttpResponse:
    def __init__(self, *, status, url, headers=None, body_chunks=None):
        self.status = status
        self.url = url
        self.headers = headers or {}
        self.content = _FakeAioHttpStream(body_chunks or [b""])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClientSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, allow_redirects=False):
        self.requests.append({"url": url, "allow_redirects": allow_redirects})
        if not self._responses:
            raise AssertionError("No fake HTTP responses remaining")
        return self._responses.pop(0)


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


@pytest.mark.asyncio
async def test_apply_patch_unified_rejects_targets_outside_worktree(tmp_path):
    registry = ToolRegistryAsync()
    patch_text = """diff --git a/../../outside.txt b/../../outside.txt
--- a/../../outside.txt
+++ b/../../outside.txt
@@ -0,0 +1 @@
+oops
"""

    with pytest.raises(ValidationError, match="escapes working directory"):
        await registry.apply_patch_unified(
            patch=patch_text,
            path=str(tmp_path),
            check_only=True,
        )


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
async def test_run_tests_reports_truncation_flags():
    registry = ToolRegistryAsync()
    with patch.object(
        registry,
        "_run_command_capture",
        AsyncMock(
            return_value={
                "stdout": "x" * 20,
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "stdout_truncated": True,
                "stderr_truncated": False,
            }
        ),
    ):
        payload = json.loads(await registry.run_tests(command="pytest -q"))

    assert payload["ok"] is True
    assert payload["stdout_truncated"] is True
    assert payload["output_truncated"] is True


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
async def test_git_status_diff_raises_on_failed_git_subcommand():
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
            "stdout": "",
            "stderr": "git status failed",
            "exit_code": 1,
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
        with pytest.raises(ToolExecutionError, match="git status failed"):
            await registry.git_status_diff()


@pytest.mark.asyncio
async def test_format_and_lint_reports_truncation_flags(tmp_path):
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "formatted\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": True,
        "stderr_truncated": False,
    }

    with (
        patch("poor_cli.tools_async.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name in {"black", "ruff"} else None),
        patch.object(registry, "_run_command_capture", AsyncMock(return_value=result_payload)),
    ):
        payload = json.loads(await registry.format_and_lint(path=str(tmp_path), fix=False))

    assert payload["ok"] is True
    assert payload["results"][0]["stdout_truncated"] is True


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


@pytest.mark.asyncio
async def test_fetch_url_rejects_embedded_credentials():
    registry = ToolRegistryAsync()
    with pytest.raises(ValidationError, match="embedded credentials"):
        await registry.fetch_url("https://user:pass@example.com/secret")


@pytest.mark.asyncio
async def test_fetch_url_blocks_redirect_to_private_host():
    registry = ToolRegistryAsync()
    fake_session = _FakeClientSession(
        [
            _FakeAioHttpResponse(
                status=302,
                url="https://example.com/start",
                headers={"Location": "http://127.0.0.1:8080/admin"},
            )
        ]
    )

    with patch("poor_cli.tools_async.aiohttp.ClientSession", return_value=fake_session):
        with pytest.raises(ValidationError, match="local/private network"):
            await registry.fetch_url("https://example.com/start")

    assert fake_session.requests == [
        {"url": "https://example.com/start", "allow_redirects": False}
    ]


@pytest.mark.asyncio
async def test_fetch_url_reports_truncated_content():
    registry = ToolRegistryAsync()
    oversized_body = [b"a" * 70000]
    fake_session = _FakeClientSession(
        [
            _FakeAioHttpResponse(
                status=200,
                url="https://example.com/article",
                headers={"Content-Type": "text/plain; charset=utf-8"},
                body_chunks=oversized_body,
            )
        ]
    )

    with patch("poor_cli.tools_async.aiohttp.ClientSession", return_value=fake_session):
        payload = json.loads(await registry.fetch_url("https://example.com/article", max_chars=250))

    assert payload["url"] == "https://example.com/article"
    assert payload["content_truncated"] is True
    assert len(payload["content_excerpt"]) == 250


@pytest.mark.asyncio
async def test_read_file_shows_line_numbers(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    result = await registry.read_file(str(target))
    lines = result.splitlines()
    assert lines[0].startswith("     1\t") # first line numbered 1
    assert lines[1].startswith("     2\t")
    assert "alpha" in lines[0]
    assert "beta" in lines[1]
    assert "gamma" in lines[2]


@pytest.mark.asyncio
async def test_read_file_line_numbers_with_range(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "lines.txt"
    target.write_text("a\nb\nc\nd\ne\nf\ng\nh\n", encoding="utf-8")
    result = await registry.read_file(str(target), start_line=5, end_line=7)
    lines = result.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("     5\t") # offset matches file position
    assert lines[1].startswith("     6\t")
    assert lines[2].startswith("     7\t")


@pytest.mark.asyncio
async def test_read_file_line_numbers_right_justified(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "big.txt"
    target.write_text("".join(f"line{i}\n" for i in range(1, 101)), encoding="utf-8")
    result = await registry.read_file(str(target))
    lines = result.splitlines()
    num_field_1 = lines[0].split("\t")[0] # 6-char wide right-justified field
    num_field_100 = lines[99].split("\t")[0]
    assert len(num_field_1) == 6
    assert len(num_field_100) == 6
    assert num_field_1 == "     1"
    assert num_field_100 == "   100"


@pytest.mark.asyncio
async def test_read_file_empty_file_returns_empty(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "empty.txt"
    target.write_text("", encoding="utf-8")
    result = await registry.read_file(str(target))
    assert result == "" # no crash, empty string


@pytest.mark.asyncio
async def test_grep_uses_ripgrep_when_available():
    registry = ToolRegistryAsync()
    rg_stdout = "src/main.py:10: import os\nsrc/main.py:20: import sys\n"
    with (
        patch("poor_cli.tools_async.shutil.which", return_value="/usr/bin/rg"),
        patch.object(
            registry,
            "_run_command_capture",
            AsyncMock(return_value={
                "stdout": rg_stdout,
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }),
        ) as mock_capture,
    ):
        result = await registry.grep_files("import", path="/fake")
    mock_capture.assert_awaited_once() # subprocess path used
    assert "import os" in result
    assert "import sys" in result


@pytest.mark.asyncio
async def test_grep_falls_back_to_python_re(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "hello.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    with patch("poor_cli.tools_async.shutil.which", return_value=None):
        result = await registry.grep_files("beta", path=str(tmp_path))
    assert "beta" in result
    assert "hello.txt:2:" in result


@pytest.mark.asyncio
async def test_grep_context_lines_with_ripgrep():
    registry = ToolRegistryAsync()
    with (
        patch("poor_cli.tools_async.shutil.which", return_value="/usr/bin/rg"),
        patch.object(
            registry,
            "_run_command_capture",
            AsyncMock(return_value={
                "stdout": "file.py:5: match\n",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }),
        ) as mock_capture,
    ):
        await registry.grep_files("match", path="/fake", context_lines=2)
    cmd = mock_capture.call_args[0][0]
    assert "-C" in cmd
    assert "2" in cmd


@pytest.mark.asyncio
async def test_grep_context_lines_python_fallback(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "ctx.txt"
    target.write_text("line1\nline2\nMATCH\nline4\nline5\n", encoding="utf-8")
    with patch("poor_cli.tools_async.shutil.which", return_value=None):
        result = await registry.grep_files("MATCH", path=str(tmp_path), context_lines=1)
    assert "line2" in result # context before
    assert "MATCH" in result
    assert "line4" in result # context after


@pytest.mark.asyncio
async def test_grep_raised_caps(tmp_path):
    registry = ToolRegistryAsync()
    # create 60 files (exceeds old 50 cap) each with a match
    for i in range(60):
        f = tmp_path / f"f{i:03d}.txt"
        f.write_text(f"needle_{i}\n", encoding="utf-8")
    with patch("poor_cli.tools_async.shutil.which", return_value=None):
        result = await registry.grep_files("needle", path=str(tmp_path))
    assert "Found 60 matches" in result # all 60 found, not capped at 50


@pytest.mark.asyncio
async def test_grep_output_includes_line_numbers(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "numbered.txt"
    target.write_text("aaa\nbbb\nccc\n", encoding="utf-8")
    with patch("poor_cli.tools_async.shutil.which", return_value=None):
        result = await registry.grep_files("bbb", path=str(tmp_path))
    assert "numbered.txt:2: bbb" in result # format: file:line: content


@pytest.mark.asyncio
async def test_edit_file_replace_all_multiple_occurrences(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("foo\nbar\nfoo\nbaz\nfoo\n", encoding="utf-8")

    result = await registry.edit_file(
        file_path=str(target),
        old_text="foo",
        new_text="qux",
        replace_all=True,
    )

    assert target.read_text(encoding="utf-8") == "qux\nbar\nqux\nbaz\nqux\n"
    assert result.ok is True
    assert result.changed is True


@pytest.mark.asyncio
async def test_edit_file_replace_all_false_rejects_multiple(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("foo\nfoo\nfoo\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="multiple matches found"):
        await registry.edit_file(
            file_path=str(target),
            old_text="foo",
            new_text="bar",
            replace_all=False,
        )


@pytest.mark.asyncio
async def test_edit_file_replace_all_count_in_metadata(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("x\ny\nx\nz\nx\n", encoding="utf-8")

    result = await registry.edit_file(
        file_path=str(target),
        old_text="x",
        new_text="w",
        replace_all=True,
    )

    assert result.metadata["replacements"] == 3


@pytest.mark.asyncio
async def test_edit_file_replace_all_diff_shows_all_changes(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("aaa\nbbb\naaa\nccc\naaa\n", encoding="utf-8")

    result = await registry.edit_file(
        file_path=str(target),
        old_text="aaa",
        new_text="zzz",
        replace_all=True,
    )

    assert result.diff.count("-aaa") == 3
    assert result.diff.count("+zzz") == 3


@pytest.mark.asyncio
async def test_edit_file_replace_all_zero_matches_errors(tmp_path):
    registry = ToolRegistryAsync()
    target = tmp_path / "app.py"
    target.write_text("hello\nworld\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="Text not found in file"):
        await registry.edit_file(
            file_path=str(target),
            old_text="missing",
            new_text="replaced",
            replace_all=True,
        )


# --- git_log / git_add / git_commit tests ---

from poor_cli.tools_async import DEFAULT_TOOL_CAPABILITIES


@pytest.mark.asyncio
async def test_git_log_returns_recent_commits():
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "abc1234 initial commit\ndef5678 add feature\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
    with patch.object(registry, "_run_command_capture", AsyncMock(return_value=result_payload)) as mock_cap:
        output = await registry.git_log()
    assert "abc1234" in output
    assert "def5678" in output
    mock_cap.assert_awaited_once()


@pytest.mark.asyncio
async def test_git_log_respects_count_param(tmp_path):
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "abc1234 only one\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
    with patch.object(registry, "_run_command_capture", AsyncMock(return_value=result_payload)) as mock_cap:
        await registry.git_log(count=5, path=str(tmp_path))
    args = mock_cap.call_args[0][0] # first positional arg is argv list
    assert "-5" in args


@pytest.mark.asyncio
async def test_git_add_stages_specific_files(tmp_path):
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
    with patch.object(registry, "_run_command_capture", AsyncMock(return_value=result_payload)) as mock_cap:
        output = await registry.git_add(file_paths=["foo.py", "bar.py"], path=str(tmp_path))
    assert "2 file(s)" in output
    argv = mock_cap.call_args[0][0]
    assert argv == ["git", "add", "--", "foo.py", "bar.py"]


@pytest.mark.asyncio
async def test_git_add_rejects_dot_and_dash_A():
    registry = ToolRegistryAsync()
    with pytest.raises(ValidationError, match="Refusing to stage"):
        await registry.git_add(file_paths=["."])
    with pytest.raises(ValidationError, match="Refusing to stage"):
        await registry.git_add(file_paths=["-A"])
    with pytest.raises(ValidationError, match="Refusing to stage"):
        await registry.git_add(file_paths=["--all"])


@pytest.mark.asyncio
async def test_git_commit_creates_commit(tmp_path):
    registry = ToolRegistryAsync()
    result_payload = {
        "stdout": "[main abc1234] fix: resolve issue\n 1 file changed, 2 insertions(+)\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
    with patch.object(registry, "_run_command_capture", AsyncMock(return_value=result_payload)) as mock_cap:
        output = await registry.git_commit(message="fix: resolve issue", path=str(tmp_path))
    assert "abc1234" in output
    argv = mock_cap.call_args[0][0]
    assert argv == ["git", "commit", "-m", "fix: resolve issue"]


def test_git_commit_capability_is_git_write():
    assert "git:write" in DEFAULT_TOOL_CAPABILITIES["git_commit"]


@pytest.mark.asyncio
async def test_git_commit_empty_message_errors():
    registry = ToolRegistryAsync()
    with pytest.raises(ValidationError, match="must not be empty"):
        await registry.git_commit(message="")
    with pytest.raises(ValidationError, match="must not be empty"):
        await registry.git_commit(message="   ")
