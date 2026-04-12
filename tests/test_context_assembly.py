import asyncio
from pathlib import Path
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.context import ContextResult, FileContext
from poor_cli.context_assembly import ContextAssemblyOrchestrator, ContextSnapshot
from poor_cli.skills import InstructionSkillContext


class _Provider:
    def __init__(self, history=None, *, max_context_tokens=100000):
        self._history = [dict(message) for message in (history or [])]
        self._max_context_tokens = max_context_tokens
        self.model_name = "test-model"
        self.prompt_prefix = ""

    def get_capabilities(self):
        return SimpleNamespace(max_context_tokens=self._max_context_tokens)

    def get_history(self):
        return [dict(message) for message in self._history]

    def set_history(self, history):
        self._history = [dict(message) for message in history]

    def update_prompt_prefix(self, prefix):
        self.prompt_prefix = prefix


class _ContextManager:
    max_tokens = 8000

    def __init__(self, path: Path):
        self.path = path

    async def select_context_files(self, **kwargs):
        content = self.path.read_text()
        file_ctx = FileContext(
            path=str(self.path),
            content=content,
            size=len(content),
            modified_time=0.0,
            language="python",
            source="explicit",
            include_full_content=True,
            selection_reason="explicit",
        )
        return ContextResult(
            files=[file_ctx],
            total_tokens=file_ctx.tokens_estimate,
            truncated=False,
            message="Selected 1 files",
            selected=[{"path": str(self.path), "reason": "explicit"}],
            excluded=[],
        )

    async def build_context_message(self, message, selection, max_tokens=None):
        file_ctx = selection.files[0]
        return f"## Context Files\n--- file: {file_ctx.path}\n{file_ctx.content}\n\nUser request: {message}"


class _Rules:
    def __init__(self, text="rules"):
        self.text = text

    def render_prompt_prefix(self):
        return self.text


class _ToolRegistry:
    def render_todos_for_context(self):
        return ""


class _Compactor:
    def __init__(self, calls):
        self.calls = calls

    async def compact(self, history, **kwargs):
        self.calls.append("optimizer")
        return SimpleNamespace(history=[dict(message) for message in history])


class _Compressor:
    def __init__(self, calls):
        self.calls = calls

    async def compress_auto(self, history, *args, **kwargs):
        self.calls.append("compressor")
        return [{"role": "user", "content": "tiny"}]


class _Core:
    def __init__(self, path: Path, *, history=None, max_context_tokens=100000):
        self.config = Config()
        self.config.model.provider = "test"
        self.config.model.model_name = "test-model"
        self.provider = _Provider(history, max_context_tokens=max_context_tokens)
        self._system_instruction = "system"
        self._context_manager = _ContextManager(path)
        self._context_contract = None
        self._pending_events = []
        self._active_tool_declarations = [{"name": "read_file"}]
        self._last_instruction_snapshot = None
        self._last_instruction_skill_plan = None
        self.tool_registry = _ToolRegistry()
        self._tiered_compactor = None
        self._context_compressor = None

    async def _ensure_repo_graph(self):
        return None

    def _record_context_preview(self, preview):
        self._last_context_preview = dict(preview)

    def _build_instruction_skill_context(self):
        return InstructionSkillContext(current_dir=str(Path.cwd()))

    def _configured_skill_search_paths(self):
        return []

    def _inspect_instruction_snapshot(self, *args, **kwargs):
        return _Rules("rules")

    async def _activate_tools_for_prompt(self, *args, **kwargs):
        self._active_tool_declarations = [{"name": "read_file"}, {"name": "grep_files"}]

    def _git_context_summary_cached(self):
        return "git summary"


def _assemble(core, prompt="inspect app.py"):
    return asyncio.run(ContextAssemblyOrchestrator(core).assemble(prompt=prompt))


def test_assemble_returns_snapshot_with_all_fields(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("print('hi')\n")
    snapshot = _assemble(_Core(path))
    assert isinstance(snapshot, ContextSnapshot)
    assert snapshot.system_prompt == "system"
    assert snapshot.rules == "rules"
    assert snapshot.files[0].path == str(path)
    assert snapshot.messages[0]["content"] == snapshot.message
    assert snapshot.tool_schemas == ({"name": "read_file"}, {"name": "grep_files"})
    assert snapshot.provider == "test"
    assert snapshot.model == "test-model"
    assert snapshot.key
    assert sum(value for key, value in snapshot.tokens.items() if key != "total") == snapshot.tokens["total"]
    assert "User request: inspect app.py" in snapshot.message


def test_budget_respected_when_over_calls_optimizer(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("print('hi')\n")
    calls = []
    core = _Core(path, history=[{"role": "user", "content": "x" * 200}], max_context_tokens=1)
    core._tiered_compactor = _Compactor(calls)
    core._context_compressor = _Compressor(calls)
    snapshot = _assemble(core)
    assert calls == ["optimizer", "compressor"]
    assert snapshot.history == ({"role": "user", "content": "tiny"},)


def test_key_stable_when_inputs_unchanged(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("print('hi')\n")
    core = _Core(path)
    first = _assemble(core).key
    second = _assemble(core).key
    assert first == second


def test_key_changes_when_file_content_changes(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("print('hi')\n")
    core = _Core(path)
    first = _assemble(core).key
    path.write_text("print('bye')\n")
    second = _assemble(core).key
    assert first != second
