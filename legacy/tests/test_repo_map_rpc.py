import asyncio
from pathlib import Path
from types import SimpleNamespace

from poor_cli.repo_graph import RepoGraph
from poor_cli.server.handlers.repo_map import RepoMapHandlersMixin
from poor_cli.server.registry import REGISTRY


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _Server(RepoMapHandlersMixin):
    def __init__(self, core):
        self.core = core

    def _ensure_initialized(self):
        return None


def test_repo_map_top_expand_symbols_roundtrip(tmp_path):
    _write(tmp_path / "core.py", "from util import helper\n\ndef run():\n    return helper()\n")
    _write(tmp_path / "util.py", "def helper():\n    return 'ok'\n")
    graph = RepoGraph(tmp_path)
    graph.build_index()
    server = _Server(SimpleNamespace(_repo_graph=graph, _repo_root=tmp_path))

    top = asyncio.run(REGISTRY["repo_map.top"](server, {"limit": 99}))
    assert top["limit"] == 50
    assert top["files"]
    assert top["files"][0]["score"] >= top["files"][-1]["score"]

    core_entry = next(item for item in top["files"] if item["relative_path"] == "core.py")
    expanded = asyncio.run(REGISTRY["repo_map.expand"](server, {"path": core_entry["path"]}))
    assert expanded["imports"][0]["relative_path"] == "util.py"

    symbols = asyncio.run(REGISTRY["repo_map.symbols"](server, {"path": core_entry["path"]}))
    assert {"run"} <= {symbol["name"] for symbol in symbols["symbols"]}


def test_repo_map_symbol_extraction_uses_repo_graph(tmp_path):
    _write(
        tmp_path / "pkg" / "app.py",
        "class App:\n    def run(self):\n        return 1\n\ndef main():\n    return App().run()\n",
    )
    graph = RepoGraph(tmp_path)
    graph.build_index()

    symbols = graph.repo_map_symbols("pkg/app.py")["symbols"]
    assert [symbol["name"] for symbol in symbols] == ["App", "run", "main"]
    assert symbols[0]["kind"] == "class"
