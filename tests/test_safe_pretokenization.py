import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.context import ContextResult, FileContext
from poor_cli.context_assembly import ContextAssemblyOrchestrator
from poor_cli.code_tokenizer import safe_pretokenize
from poor_cli.core import PoorCLICore
from poor_cli.economy import EconomySavingsTracker
from poor_cli.skills import InstructionSkillContext
from poor_cli.token_counter import get_token_counter


PY_FIXTURE = '''"""module docs"""
# remove
def alpha(value):
    """function docs"""


    if value:
        return "keep"


    return "also keep"
'''


class _Provider:
    model_name = "test-model"

    def get_capabilities(self):
        return SimpleNamespace(max_context_tokens=100000)

    def get_history(self):
        return []

    def update_prompt_prefix(self, _prefix):
        return None


class _ContextManager:
    max_tokens = 8000

    def __init__(self, path: Path, *, source: str = "auto", include_full_content: bool = False):
        self.path = path
        self.source = source
        self.include_full_content = include_full_content

    async def select_context_files(self, **_kwargs):
        content = self.path.read_text()
        file_ctx = FileContext(
            path=str(self.path),
            content=content,
            size=len(content),
            modified_time=0.0,
            language="python",
            source=self.source,
            include_full_content=self.include_full_content,
            selection_reason=self.source,
        )
        return ContextResult(
            files=[file_ctx],
            total_tokens=file_ctx.tokens_estimate,
            truncated=False,
            message="Selected 1 files",
            selected=[{"path": str(self.path), "reason": self.source, "tokenEstimate": file_ctx.tokens_estimate}],
            excluded=[],
        )

    async def build_context_message(self, message, selection, max_tokens=None):
        file_ctx = selection.files[0]
        return f"## Context Files\n--- file: {file_ctx.path}\n{file_ctx.content}\n\nUser request: {message}"


class _Core:
    def __init__(self, path: Path, *, source: str = "auto", include_full_content: bool = False):
        self.config = Config()
        self.config.model.provider = "test"
        self.config.model.model_name = "test-model"
        self.provider = _Provider()
        self._system_instruction = "system"
        self._context_manager = _ContextManager(path, source=source, include_full_content=include_full_content)
        self._context_contract = None
        self._pending_events = []
        self._active_tool_declarations = []
        self._last_instruction_snapshot = None
        self._last_instruction_skill_plan = None
        self.tool_registry = SimpleNamespace(render_todos_for_context=lambda: "")
        self._tiered_compactor = None
        self._context_compressor = None
        self._economy_tracker = EconomySavingsTracker()

    async def _ensure_repo_graph(self):
        return None

    def _record_context_preview(self, preview):
        self._last_context_preview = dict(preview)

    def _build_instruction_skill_context(self):
        return InstructionSkillContext(current_dir=str(Path.cwd()))

    def _configured_skill_search_paths(self):
        return []

    def _inspect_instruction_snapshot(self, *args, **kwargs):
        return SimpleNamespace(render_prompt_prefix=lambda: "rules")

    async def _activate_tools_for_prompt(self, *args, **kwargs):
        return None

    def _git_context_summary_cached(self):
        return ""


def _assemble(core):
    return asyncio.run(ContextAssemblyOrchestrator(core).assemble(prompt="inspect helper"))


def test_pretokenize_preserves_parseability():
    compressed = safe_pretokenize(PY_FIXTURE, ".py")
    ast.parse(compressed)


def test_pretokenize_reduces_tokens_by_at_least_5pct():
    compressed = safe_pretokenize(PY_FIXTURE, ".py")
    counter = get_token_counter()
    before = counter.count(PY_FIXTURE).count
    after = counter.count(compressed).count
    assert (before - after) / before >= 0.05


def test_malformed_python_returns_original():
    original = "def broken(:\n    pass\n"
    assert safe_pretokenize(original, ".py") == original


def test_feature_flag_default_off(tmp_path):
    path = tmp_path / "helper.py"
    path.write_text(PY_FIXTURE)
    core = _Core(path)
    snapshot = _assemble(core)
    assert core.config.context.safe_pretokenization is False
    assert snapshot.files[0].content == PY_FIXTURE
    assert snapshot.files[0].pretokenized is False


def test_flag_on_pretokenizes_context_file_and_records_savings(tmp_path):
    path = tmp_path / "helper.py"
    path.write_text(PY_FIXTURE)
    core = _Core(path)
    core.config.context.safe_pretokenization = True
    snapshot = _assemble(core)
    file_ctx = snapshot.files[0]
    summary = core._economy_tracker.get_summary()
    assert file_ctx.pretokenized is True
    assert file_ctx.tokens_saved > 0
    assert "# remove" not in snapshot.message
    assert summary["tokens_saved_by_safe_pretokenization"] == file_ctx.tokens_saved
    assert summary["safe_pretokenization_by_file"][str(path)] == file_ctx.tokens_saved


def test_edit_target_round_trips_raw_when_flag_on(tmp_path):
    path = tmp_path / "target.py"
    path.write_text(PY_FIXTURE)
    core = _Core(path, source="explicit", include_full_content=True)
    core.config.context.safe_pretokenization = True
    snapshot = asyncio.run(ContextAssemblyOrchestrator(core).assemble(prompt="edit target.py"))
    assert snapshot.files[0].content == path.read_text()
    assert PY_FIXTURE in snapshot.message
    assert snapshot.files[0].pretokenized is False


def test_cost_and_savings_roll_up_safe_pretokenization():
    core = object.__new__(PoorCLICore)
    core.tool_registry = None
    core._mcp_manager = None
    core._block_cache = None
    core._semantic_cache = None
    core._economy_tracker = EconomySavingsTracker()
    core._economy_tracker.record_safe_pretokenization("a.py", 100, 70)
    core._session_total_input_tokens = 0
    core._session_total_output_tokens = 0
    core._session_total_cost_usd = 0.0
    core._session_cache_creation_input_tokens = 0
    core._session_cache_read_input_tokens = 0
    core._session_provider_cache_hits = 0
    core._session_provider_cache_misses = 0
    summary = core.get_session_cost_summary()
    savings = core.get_economy_savings()
    assert summary["safe_pretokenization_tokens_saved"] == 30
    assert summary["safePretokenizationTokensSaved"] == 30
    assert savings["tokensSaved"] == 30
    assert savings["by_source"][0]["source"] == "safe_pretokenization"
