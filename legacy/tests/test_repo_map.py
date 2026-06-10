from __future__ import annotations

from pathlib import Path

from poor_cli.repo_graph import RepoGraph
from poor_cli.repo_map import RepoMap


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_skeleton_cost_under_half_of_full_file(tmp_path) -> None:
    body = "\n".join(f"    value += {idx}" for idx in range(220))
    _write(
        tmp_path / "large.py",
        f"class LargeThing:\n    def compute(self):\n        value = 0\n{body}\n        return value\n",
    )
    graph = RepoGraph(tmp_path)
    graph.build_index()

    skeleton = RepoMap(tmp_path, graph=graph).skeleton_for("large.py")

    assert skeleton is not None
    assert skeleton.skeleton_tokens < skeleton.full_tokens * 0.5


def test_hot_symbols_matches_query_terms(tmp_path) -> None:
    _write(
        tmp_path / "auth.py",
        "def user_authenticate(user):\n    return bool(user)\n\nclass AuthStore:\n    pass\n",
    )
    graph = RepoGraph(tmp_path)
    graph.build_index()

    symbols = RepoMap(tmp_path, graph=graph).hot_symbols("user_auth", limit=10)

    names = {symbol.name for symbol in symbols}
    assert "user_authenticate" in names
    assert "AuthStore" in names


def test_diff_relevant_skeletons_includes_import_neighbors(tmp_path) -> None:
    _write(tmp_path / "a.py", "from b import helper\n\ndef run():\n    return helper()\n")
    _write(tmp_path / "b.py", "def helper():\n    return 1\n")
    graph = RepoGraph(tmp_path)
    graph.build_index()

    skeletons = RepoMap(tmp_path, graph=graph).diff_relevant_skeletons(["a.py"])

    paths = {skeleton.path for skeleton in skeletons}
    assert "a.py" in paths
    assert "b.py" in paths
