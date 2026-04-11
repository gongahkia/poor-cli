import asyncio
import importlib.util
import subprocess
from pathlib import Path

import pytest

from poor_cli.context_providers import _resolve_codebase
from poor_cli.repo_graph import RepoGraph


TREE_SITTER_MODULES = (
    "tree_sitter",
    "tree_sitter_python",
    "tree_sitter_lua",
    "tree_sitter_javascript",
    "tree_sitter_typescript",
    "tree_sitter_rust",
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.name", "poor-cli")
    _git(repo, "config", "user.email", "poor-cli@example.com")


def _build_sample_repo(repo: Path) -> None:
    _write(
        repo / "core.py",
        """
from utils import helper

class AppCore:
    def run(self) -> str:
        return helper()

def run() -> str:
    core = AppCore()
    return core.run()
""".strip()
        + "\n",
    )
    _write(
        repo / "app.py",
        """
from core import run

def main() -> str:
    return run()
""".strip()
        + "\n",
    )
    _write(
        repo / "cli.py",
        """
from core import AppCore, run

def execute() -> str:
    return run()
""".strip()
        + "\n",
    )
    _write(
        repo / "utils.py",
        """
def helper() -> str:
    return "ok"
""".strip()
        + "\n",
    )


def test_repo_map_ranks_core_and_respects_token_budget(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _build_sample_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    graph = RepoGraph(tmp_path)
    graph.build_index()

    ranked = graph.rank_files_for_query([], limit=4)
    assert ranked
    assert ranked[0][0].endswith("core.py")

    workspace_map = graph.build_repo_map(token_budget=120)
    assert workspace_map
    assert "core.py (rank=" in workspace_map
    assert "class AppCore" in workspace_map
    assert len(workspace_map) // 4 <= 120
    assert workspace_map.index("core.py") < workspace_map.index("utils.py")


def test_repo_map_cache_invalidates_on_unstaged_file_change(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _build_sample_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    graph = RepoGraph(tmp_path)
    graph.build_index()
    first_map = graph.build_repo_map(token_budget=120)
    first_cache = graph._load_cached_map_data(graph._repo_state_fingerprint())
    assert first_cache is not None
    assert graph.should_reindex() == "skip"

    core_path = tmp_path / "core.py"
    core_path.write_text(
        core_path.read_text(encoding="utf-8")
        + "\n\ndef bootstrap() -> str:\n    return run()\n",
        encoding="utf-8",
    )

    assert graph.should_reindex() == "incremental"

    second_map = graph.build_repo_map(token_budget=160)
    second_cache = graph._load_cached_map_data(graph._repo_state_fingerprint())
    assert second_cache is not None
    assert second_cache["generated_at"] >= first_cache["generated_at"]
    assert "bootstrap" in second_map
    assert second_map != first_map


def test_codebase_provider_returns_workspace_map_when_requested(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _build_sample_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    graph = RepoGraph(tmp_path)
    graph.build_index()

    class FakeCore:
        def __init__(self, repo_graph: RepoGraph) -> None:
            self._repo_graph = repo_graph
            self.tool_registry = None

    result = asyncio.run(_resolve_codebase("workspace-map", FakeCore(graph)))
    assert result.startswith("[workspace map]\n")
    assert "core.py (rank=" in result


@pytest.mark.skipif(
    any(importlib.util.find_spec(module_name) is None for module_name in TREE_SITTER_MODULES),
    reason="tree-sitter optional deps not installed",
)
@pytest.mark.parametrize(
    ("language_name", "source_text", "expected_symbol", "expected_import", "expected_call"),
    [
        (
            "python",
            "import os\nfrom utils import helper\nclass App:\n    def run(self):\n        helper()\n",
            "App",
            "utils",
            "helper",
        ),
        (
            "lua",
            'local mod = require("core.utils")\nlocal function helper(x) return x end\nfunction M.run(a)\n  helper(a)\nend\n',
            "helper",
            "core.utils",
            "helper",
        ),
        (
            "javascript",
            'import dep from "./dep";\nconst helper = () => dep();\nfunction main() { helper(); }\n',
            "main",
            "./dep",
            "helper",
        ),
        (
            "typescript",
            'import type { Foo } from "./types";\nexport class App extends Base { method(): void { helper(); } }\nconst helper = (x: number): number => x\n',
            "App",
            "./types",
            "helper",
        ),
        (
            "rust",
            "use crate::utils::helper;\nstruct App;\nimpl App { fn run(&self) { helper(); } }\n",
            "App",
            "crate::utils::helper",
            "helper",
        ),
    ],
)
def test_tree_sitter_extracts_target_languages(
    tmp_path: Path,
    language_name: str,
    source_text: str,
    expected_symbol: str,
    expected_import: str,
    expected_call: str,
) -> None:
    graph = RepoGraph(tmp_path)
    payload = graph._extract_treesitter_data(source_text, language_name)
    assert payload is not None
    assert expected_symbol in {symbol["name"] for symbol in payload["symbols"]}
    assert expected_import in payload["imports"]
    assert expected_call in payload["calls"]
