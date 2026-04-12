import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

from poor_cli.context import ContextResult, FileContext
from poor_cli.context.file_selector import FileSelector, SelectionWeights
from poor_cli.context_assembly import ContextAssemblyOrchestrator
from poor_cli.repo_graph import RepoGraph
from poor_cli.skills import InstructionSkillContext


def _file(path: Path, *, mtime: float = 0.0, source: str = "auto") -> FileContext:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print('ok')\n", encoding="utf-8")
    return FileContext(
        path=str(path),
        content=path.read_text(encoding="utf-8"),
        size=path.stat().st_size,
        modified_time=mtime,
        language="python",
        source=source,
        selection_reason=source,
    )


class _FakeGraph:
    def __init__(self, scores=None, related=None):
        self.scores = scores or {}
        self.related = related or {}

    def pagerank_score(self, path):
        return self.scores.get(str(Path(path).resolve()), 0.0)

    def files_related_to(self, path, max_depth=2):
        return self.related.get(str(Path(path).resolve()), [])


def test_top_k_returns_sorted(tmp_path):
    hub = tmp_path / "hub.py"
    leaf = tmp_path / "leaf.py"
    hub.write_text("def hub(): pass\n", encoding="utf-8")
    leaf.write_text("from hub import hub\n", encoding="utf-8")
    graph = RepoGraph(tmp_path)
    with graph._connect() as conn:
        now = time.time()
        conn.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(hub.resolve()), "hub.py", "python", hub.stat().st_size, now, now, 1),
        )
        conn.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(leaf.resolve()), "leaf.py", "python", leaf.stat().st_size, now, now, 1),
        )
        conn.execute(
            "INSERT INTO edges (source_path, target_path, edge_type, weight) VALUES (?, ?, ?, ?)",
            (str(leaf.resolve()), str(hub.resolve()), "imports", 2.0),
        )

    ranked = graph.top_k(2)
    assert ranked == sorted(ranked, key=lambda item: (-item[1], item[0]))
    assert ranked[0][0] == str(hub.resolve())
    assert graph.pagerank_score("hub.py") == ranked[0][1]


def test_ranking_determinism_and_weighted_tie(tmp_path):
    a = _file(tmp_path / "a.py", mtime=0.0)
    b = _file(tmp_path / "b.py", mtime=10.0)
    scores = {a.path: 1.0, b.path: 0.0}
    selector = FileSelector(
        repo_graph=_FakeGraph(scores),
        weights=SelectionWeights(alpha=0.5, beta=0.5, gamma=0.0),
    )

    first = selector.rank([b, a])
    second = selector.rank([a, b])
    assert [item.file.path for item in first] == [a.path, b.path]
    assert [item.file.path for item in second] == [a.path, b.path]
    assert first[0].score == first[1].score


def test_pagerank_zero_disables_influence(tmp_path):
    hub = _file(tmp_path / "hub.py", mtime=0.0)
    recent_leaf = _file(tmp_path / "recent_leaf.py", mtime=10.0)
    selector = FileSelector(
        repo_graph=_FakeGraph({hub.path: 1.0, recent_leaf.path: 0.0}),
        weights={"recency": 1.0, "pagerank": 0.0, "import_distance": 0.0},
    )

    ranked = selector.rank([hub, recent_leaf])
    assert [item.file.path for item in ranked] == [recent_leaf.path, hub.path]


def test_pinned_files_survive_max_file_limit(tmp_path):
    pinned = _file(tmp_path / "pinned.py", mtime=0.0, source="pinned")
    recent = _file(tmp_path / "recent.py", mtime=10.0)
    selector = FileSelector(
        repo_graph=_FakeGraph({recent.path: 1.0}),
        weights=SelectionWeights(alpha=1.0, beta=1.0, gamma=0.0),
    )
    ranked_files = [item.file for item in selector.rank([recent, pinned], pinned_paths=[pinned.path])]

    from poor_cli.context import ContextManager

    selected = ContextManager._limit_preserving_pinned(ranked_files, 1, {pinned.path})
    assert pinned.path in [file_ctx.path for file_ctx in selected]


class _Rules:
    def render_prompt_prefix(self):
        return "rules"


class _ContextManager:
    max_tokens = 8000

    def __init__(self, files):
        self.files = files
        self._file_selector = None

    async def select_context_files(self, **kwargs):
        ranked = self._file_selector.rank(
            self.files,
            prompt=kwargs.get("message", ""),
            pinned_paths=kwargs.get("pinned_files", []),
            seed_paths=kwargs.get("explicit_files", []) + kwargs.get("pinned_files", []),
        )
        files = [item.file for item in ranked]
        return ContextResult(
            files=files,
            total_tokens=sum(file_ctx.tokens_estimate for file_ctx in files),
            truncated=False,
            message=f"Selected {len(files)} files",
            selected=[{"path": file_ctx.path, "reason": file_ctx.selection_reason} for file_ctx in files],
            excluded=[],
        )

    async def build_context_message(self, message, selection, max_tokens=None):
        return f"User request: {message}"


class _Core:
    def __init__(self, files, graph, *, task=None):
        self.config = SimpleNamespace(
            model=SimpleNamespace(provider="test", model_name="test-model"),
            plan_mode=SimpleNamespace(enabled=False),
        )
        self.provider = None
        self._system_instruction = "system"
        self._context_manager = _ContextManager(files)
        self._context_contract = None
        self._pending_events = []
        self._active_tool_declarations = []
        self._last_instruction_snapshot = None
        self._last_instruction_skill_plan = None
        self.tool_registry = None
        self._repo_graph = graph
        self._repo_graph_task = task
        self._repo_config = SimpleNamespace(
            preferences=SimpleNamespace(
                context={"selection_weights": {"alpha": 0.4, "beta": 0.4, "gamma": 0.2}}
            )
        )

    async def _ensure_repo_graph(self):
        return None

    def _record_context_preview(self, preview):
        self._last_context_preview = dict(preview)

    def _build_instruction_skill_context(self):
        return InstructionSkillContext(current_dir=str(Path.cwd()))

    def _configured_skill_search_paths(self):
        return []

    def _inspect_instruction_snapshot(self, *args, **kwargs):
        return _Rules()


class _PendingTask:
    def done(self):
        return False


def test_assembly_prefers_pagerank_hubs_over_leaves(tmp_path):
    hub = _file(tmp_path / "hub.py", mtime=0.0)
    leaf = _file(tmp_path / "leaf.py", mtime=10.0)
    core = _Core([leaf, hub], _FakeGraph({hub.path: 1.0, leaf.path: 0.0}))

    snapshot = asyncio.run(
        ContextAssemblyOrchestrator(core).assemble(
            prompt="inspect hub ranking",
            activate_tools=False,
        )
    )
    assert snapshot.files[0].path == hub.path


def test_cold_start_fallback_when_graph_missing(tmp_path):
    hub = _file(tmp_path / "hub.py", mtime=0.0)
    leaf = _file(tmp_path / "leaf.py", mtime=10.0)
    core = _Core([hub, leaf], _FakeGraph({hub.path: 1.0, leaf.path: 0.0}), task=_PendingTask())

    snapshot = asyncio.run(
        ContextAssemblyOrchestrator(core).assemble(
            prompt="inspect cold start",
            activate_tools=False,
        )
    )
    assert snapshot.files[0].path == leaf.path
