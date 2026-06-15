from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from poor_cli.config import empty_config, save_repo_config
from poor_cli.store import RunStore
from poor_cli.tools import ToolDispatcher, ToolReplayMiss, ToolResult, load_tool_entry_points


def _run_id(store: RunStore, root: Path) -> str:
    return store.create_run(user_goal="goal", repo_path=root, git_commit_start="abc", mode="balanced", budget={})


def test_builtin_tools_cover_v0_surface(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)

    written = dispatcher.call("write_file", {"path": "src/example.txt", "content": "hello world\n"})
    read = dispatcher.call("read_file", {"path": "src/example.txt"})
    edited = dispatcher.call("edit", {"path": "src/example.txt", "old": "world", "new": "poor-cli"})
    globbed = dispatcher.call("glob", {"pattern": "src/*.txt"})
    grepped = dispatcher.call("grep", {"pattern": "poor-cli", "glob": "src/*.txt"})
    shell = dispatcher.call("shell", {"command": "printf shell-ok"})
    emitted = dispatcher.call("replay_emit", {"value": {"ok": True}})

    assert written.ok is True
    assert read.output["content"] == "hello world\n"
    assert edited.output["replacements"] == 1
    assert globbed.output["matches"] == ["src/example.txt"]
    assert grepped.output["matches"][0]["line"] == 1
    assert shell.output["stdout"] == "shell-ok"
    assert emitted.output["value"] == {"ok": True}
    assert len(store.list_artifacts(run_id, "tool.result")) == 7
    store.close()


def test_tool_dispatcher_replays_cached_result_without_execution(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    path = tmp_path / "note.txt"
    path.write_text("original", encoding="utf-8")

    first = ToolDispatcher(store, run_id, workdir=tmp_path).call("read_file", {"path": "note.txt"})
    path.write_text("changed", encoding="utf-8")
    replayed = ToolDispatcher(store, run_id, workdir=tmp_path, replay_only=True).call("read_file", {"path": "note.txt"})

    assert first.output["content"] == "original"
    assert replayed.output["content"] == "original"
    assert replayed.cached is True
    store.close()


def test_tool_dispatcher_fails_closed_on_replay_miss(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)

    with pytest.raises(ToolReplayMiss):
        ToolDispatcher(store, run_id, workdir=tmp_path, replay_only=True).call("replay_emit", {"value": "missing"})

    assert store.list_events(run_id)[0]["type"] == "tool.cache_miss"
    store.close()


def test_tool_entry_points_extend_dispatcher_defaults(tmp_path: Path, monkeypatch) -> None:
    def external_tool(args):
        return ToolResult(name="audit", ok=True, output={"value": args["value"]})

    class EntryPoint:
        name = "audit"

        def load(self):
            return external_tool

    class EntryPoints:
        def select(self, group: str):
            assert group == "poor_cli.tools"
            return [EntryPoint()]

    monkeypatch.setattr("poor_cli.extensions.entry_points", lambda: EntryPoints())
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)

    assert load_tool_entry_points() == {"audit": external_tool}
    result = ToolDispatcher(store, run_id, workdir=tmp_path).call("audit", {"value": 7})

    assert result.output == {"value": 7}
    store.close()


def test_shell_tool_blocks_network_and_outside_writes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)

    network = dispatcher.call("shell", {"command": "curl https://example.com"})
    outside = dispatcher.call("shell", {"command": "touch ../outside.txt"})

    assert network.ok is False
    assert "network" in str(network.error)
    assert outside.ok is False
    assert "outside workdir" in str(outside.error)
    assert not (tmp_path.parent / "outside.txt").exists()
    store.close()


def test_shell_tool_blocks_complex_shell_escape_forms(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)
    blocked = [
        "printf $(curl https://example.com)",
        "printf `curl https://example.com`",
        "cat <(printf hi)",
        "cat <<EOF\nhi\nEOF",
        "bash -c 'curl https://example.com'",
        "sh -c 'curl https://example.com'",
        "zsh -c 'curl https://example.com'",
        "alias c=curl; c https://example.com",
        "function c { curl https://example.com; }; c",
        "env curl https://example.com",
        "command curl https://example.com",
        "printf hi >/tmp/outside.txt",
        "printf hi >> ~/.zshrc",
        "printf hi 2>/tmp/err.txt",
        "printf hi > ../outside.txt",
    ]

    for command in blocked:
        result = dispatcher.call("shell", {"command": command})
        assert result.ok is False, command
        assert result.raw["reason"]
        assert result.raw["remediation"]

    assert not (tmp_path.parent / "outside.txt").exists()
    store.close()


def test_shell_tool_allows_low_risk_commands(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, check=True)

    assert dispatcher.call("shell", {"command": "printf ok > inside.txt"}).ok is True
    assert dispatcher.call("shell", {"command": "git status --short"}).ok is True
    assert dispatcher.call("shell", {"command": "python -m pytest --version"}).ok is True

    store.close()


def test_tool_dispatcher_validates_builtin_args(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    result = ToolDispatcher(store, run_id, workdir=tmp_path).call("read_file", {})

    assert result.ok is False
    assert "missing required path" in str(result.error)
    assert store.list_artifacts(run_id, "tool.result")
    store.close()


def test_web_search_custom_endpoint_records_citations(tmp_path: Path, monkeypatch) -> None:
    config = empty_config()
    config["tools"] = {
        "web": {
            "mode": "custom",
            "search_endpoint": "https://search.test/api",
            "allow_domains": ["search.test", "example.com"],
        }
    }
    save_repo_config(config, tmp_path)
    monkeypatch.setattr("poor_cli.web_tools.socket.getaddrinfo", lambda host, port: [(0, 0, 0, "", ("93.184.216.34", 0))])

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self, *_args):
            return b'{"results":[{"title":"Example","url":"https://example.com/a","snippet":"s"}]}'

        def geturl(self):
            return "https://search.test/api"

    monkeypatch.setattr("poor_cli.web_tools.urlopen", lambda request, timeout=10: FakeResponse())
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)

    result = ToolDispatcher(store, run_id, workdir=tmp_path).call("web_search", {"query": "example"})

    assert result.ok is True
    assert result.output["results"][0]["url"] == "https://example.com/a"
    assert result.output["replay_id"]
    assert store.list_artifacts(run_id, "web.search")
    assert store.list_artifacts(run_id, "web.citation")
    store.close()


def test_web_fetch_blocks_private_redirect_and_truncates(tmp_path: Path, monkeypatch) -> None:
    config = empty_config()
    config["tools"] = {"web": {"allow_domains": ["public.test"], "max_bytes": 12}}
    save_repo_config(config, tmp_path)

    def getaddrinfo(host, port):
        ip = "93.184.216.34" if host == "public.test" else "127.0.0.1"
        return [(0, 0, 0, "", (ip, 0))]

    class FakeResponse:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self, *_args):
            return b"<html><script>x()</script><body>Hello world from public web</body></html>"

        def geturl(self):
            return "https://public.test/page"

    monkeypatch.setattr("poor_cli.web_tools.socket.getaddrinfo", getaddrinfo)
    monkeypatch.setattr("poor_cli.web_tools.urlopen", lambda request, timeout=10: FakeResponse())
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)

    blocked_scheme = dispatcher.call("web_fetch", {"url": "file:///etc/passwd"})
    blocked_host = dispatcher.call("web_fetch", {"url": "http://127.0.0.1/"})
    fetched = dispatcher.call("web_fetch", {"url": "https://public.test/page"})

    assert blocked_scheme.ok is False
    assert "scheme" in str(blocked_scheme.error)
    assert blocked_host.ok is False
    assert "private" in str(blocked_host.error)
    assert fetched.ok is True
    assert fetched.output["truncated"] is True
    assert "script" not in fetched.output["content"].lower()
    assert store.list_artifacts(run_id, "web.fetch")
    assert store.list_artifacts(run_id, "web.cache")
    store.close()


def test_web_fetch_rejects_redirect_to_private_ip(tmp_path: Path, monkeypatch) -> None:
    import urllib.error

    config = empty_config()
    config["tools"] = {"web": {"allow_domains": ["public.test"]}}
    save_repo_config(config, tmp_path)
    monkeypatch.setattr("poor_cli.web_tools.socket.getaddrinfo", lambda host, port: [(0, 0, 0, "", ("93.184.216.34", 0))])

    def redirect(_request, timeout=10):
        raise urllib.error.HTTPError("https://public.test/r", 302, "found", {"Location": "http://127.0.0.1/"}, None)

    monkeypatch.setattr("poor_cli.web_tools.urlopen", redirect)
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)

    result = ToolDispatcher(store, run_id, workdir=tmp_path).call("web_fetch", {"url": "https://public.test/r"})

    assert result.ok is False
    assert "localhost" in str(result.error) or "private" in str(result.error)
    store.close()
