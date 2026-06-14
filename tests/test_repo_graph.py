from __future__ import annotations

import time
from pathlib import Path

import poor_cli.repo_graph as repo_graph
from poor_cli.repo_graph import RepoGraph
from poor_cli.store import RunStore
from poor_cli.tools import ToolDispatcher


def _sample_repo(root: Path) -> None:
    (root / "core.py").write_text(
        "from utils import helper\n\n"
        "class AppCore:\n"
        "    def run(self) -> str:\n"
        "        return helper()\n\n"
        "def run() -> str:\n"
        "    core = AppCore()\n"
        "    return core.run()\n",
        encoding="utf-8",
    )
    (root / "cli.py").write_text(
        "from core import run\n\ndef execute() -> str:\n    return run()\n",
        encoding="utf-8",
    )
    (root / "utils.py").write_text("def helper() -> str:\n    return 'ok'\n", encoding="utf-8")


def _sample_js_repo(root: Path) -> None:
    (root / "util.js").write_text("export function helper() {\n  return 'ok';\n}\n", encoding="utf-8")
    (root / "core.js").write_text(
        "import { helper } from './util.js';\n\n"
        "export function run() {\n"
        "  return helper();\n"
        "}\n\n"
        "export const arrow = () => run();\n\n"
        "class App {\n"
        "  method() {\n"
        "    return run();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "cli.js").write_text("import { run } from './core.js';\n\nfunction execute() {\n  return run();\n}\n", encoding="utf-8")


def test_repo_graph_indexes_python_symbols_imports_and_callers(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    graph = RepoGraph(tmp_path).build_index()

    assert graph.definition_of("AppCore") == {
        "name": "AppCore",
        "kind": "class",
        "path": "core.py",
        "line_start": 3,
        "line_end": 5,
        "scope": "",
    }
    assert graph.imports_of("cli.py") == {"path": "cli.py", "imports": ["core"]}
    assert graph.callers_of("helper") == [{"path": "core.py", "calls": "helper", "call_count": 1}]
    assert [item["name"] for item in graph.find_symbol("run")] == ["run", "run"]
    assert {item["path"] for item in graph.subgraph("execute", max_depth=2)["files"]} == {"cli.py", "core.py", "utils.py"}


def test_repo_graph_indexes_javascript_symbols_imports_and_callers(tmp_path: Path) -> None:
    _sample_js_repo(tmp_path)
    graph = RepoGraph(tmp_path).build_index()

    assert graph.definition_of("App")["path"] == "core.js"
    assert graph.definition_of("method")["scope"] == "App"
    assert graph.definition_of("arrow")["kind"] == "function"
    assert graph.imports_of("core.js") == {"path": "core.js", "imports": ["./util.js"]}
    assert graph.callers_of("helper") == [{"path": "core.js", "calls": "helper", "call_count": 1}]
    assert {item["path"] for item in graph.subgraph("execute", max_depth=2)["files"]} == {"cli.js", "core.js", "util.js"}


def test_repo_graph_refreshes_after_python_file_mutation(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    graph = RepoGraph(tmp_path).build_index()
    assert graph.definition_of("new_entry") is None

    (tmp_path / "extra.py").write_text("def new_entry() -> str:\n    return 'new'\n", encoding="utf-8")

    definition = graph.refresh_if_stale().definition_of("new_entry")
    assert definition is not None
    assert definition["path"] == "extra.py"


def test_repo_graph_incremental_refresh_reparses_changed_files_only(tmp_path: Path, monkeypatch) -> None:
    _sample_repo(tmp_path)
    graph = RepoGraph(tmp_path).build_index()
    calls = []
    original_parse = repo_graph._parse_python

    def spy_parse(root: Path, path: Path):
        calls.append(path.name)
        return original_parse(root, path)

    monkeypatch.setattr(repo_graph, "_parse_python", spy_parse)
    (tmp_path / "utils.py").write_text("def helper() -> str:\n    return 'ok'\n\ndef extra() -> str:\n    return 'new'\n", encoding="utf-8")

    graph.refresh_if_stale()

    assert calls == ["utils.py"]
    assert graph.definition_of("extra")["path"] == "utils.py"


def test_repo_graph_watch_refreshes_changed_files(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    graph = RepoGraph(tmp_path).build_index()

    with graph.watch(interval_seconds=0.01):
        (tmp_path / "extra.py").write_text("def watched_entry() -> str:\n    return 'new'\n", encoding="utf-8")
        deadline = time.monotonic() + 2.0
        definition = None
        while time.monotonic() < deadline:
            definition = graph.definition_of("watched_entry")
            if definition is not None:
                break
            time.sleep(0.02)

    assert definition is not None
    assert definition["path"] == "extra.py"


def test_graph_tools_are_replayable_builtin_tools(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="graph", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)

    found = dispatcher.call("find_symbol", {"query": "AppCore"})
    definition = dispatcher.call("definition_of", {"symbol": "execute"})
    imports = dispatcher.call("imports_of", {"path": "core.py"})
    callers = dispatcher.call("callers_of", {"symbol": "run"})
    subgraph = dispatcher.call("subgraph", {"seed": "execute", "max_depth": 1})

    assert found.output[0]["path"] == "core.py"
    assert definition.output["path"] == "cli.py"
    assert imports.output["imports"] == ["utils"]
    assert {item["path"] for item in callers.output} == {"cli.py", "core.py"}
    assert {item["path"] for item in subgraph.output["files"]} == {"cli.py", "core.py"}
    assert len(store.list_artifacts(run_id, "tool.result")) == 5
    store.close()


def test_graph_tools_refresh_after_codebase_mutation(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="graph", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)
    assert dispatcher.call("definition_of", {"symbol": "new_entry"}).output is None

    (tmp_path / "extra.py").write_text("def new_entry() -> str:\n    return 'new'\n", encoding="utf-8")

    found = dispatcher.call("find_symbol", {"query": "new_entry"})
    assert found.output[0]["path"] == "extra.py"
    store.close()
