from __future__ import annotations

from pathlib import Path

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
