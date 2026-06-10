"""Tests for MemGPT-style working memory and delta-based context updates."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from poor_cli.working_memory import (
    WorkingMemory,
    WorkingMemoryManager,
    ContextDelta,
    DeltaModeMetrics,
    compute_delta,
    build_delta_prompt,
    detect_confusion,
    _content_hash,
    _estimate_tokens,
    _unified_diff,
)


# ── WorkingMemory model ────────────────────────────────────────────────


class TestWorkingMemory:
    def test_defaults(self):
        wm = WorkingMemory()
        assert wm.session_summary == ""
        assert wm.active_files == {}
        assert wm.turn_count == 0
        assert wm.last_turn_id == 0
        assert wm.total_tokens_saved == 0

    def test_estimate_tokens(self):
        wm = WorkingMemory(session_summary="a" * 400, active_files={"f.py": "x" * 800})
        tokens = wm.estimate_tokens()
        assert tokens == (400 // 4) + (800 // 4) # summary + file

    def test_roundtrip_dict(self):
        wm = WorkingMemory(
            session_summary="test session",
            key_decisions=["chose X over Y"],
            pending_tasks=["implement Z"],
            turn_count=5,
            last_turn_id=5,
            total_tokens_saved=1000,
        )
        d = wm.to_dict()
        assert d["session_summary"] == "test session"
        assert d["turn_count"] == 5
        assert d["total_tokens_saved"] == 1000
        wm2 = WorkingMemory.from_dict(d)
        assert wm2.session_summary == "test session"
        assert wm2.turn_count == 5
        assert wm2.key_decisions == ["chose X over Y"]

    def test_from_dict_missing_keys(self):
        wm = WorkingMemory.from_dict({})
        assert wm.session_summary == ""
        assert wm.turn_count == 0


# ── ContextDelta ───────────────────────────────────────────────────────


class TestContextDelta:
    def test_empty(self):
        delta = ContextDelta()
        assert delta.is_empty()

    def test_not_empty_with_message(self):
        delta = ContextDelta(new_user_message="hello")
        assert not delta.is_empty()

    def test_estimate_tokens(self):
        delta = ContextDelta(
            new_user_message="hello world",
            files_added={"a.py": "content" * 100},
        )
        assert delta.estimate_tokens() > 0


# ── compute_delta ──────────────────────────────────────────────────────


class TestComputeDelta:
    def test_no_changes(self):
        wm = WorkingMemory(active_files={"a.py": "hello"})
        delta = compute_delta(wm, {"a.py": "hello"}, "msg")
        assert delta.files_changed == {}
        assert delta.files_added == {}
        assert delta.files_removed == []
        assert delta.new_user_message == "msg"

    def test_file_added(self):
        wm = WorkingMemory(active_files={"a.py": "hello"})
        delta = compute_delta(wm, {"a.py": "hello", "b.py": "new"}, "msg")
        assert "b.py" in delta.files_added
        assert delta.files_added["b.py"] == "new"

    def test_file_removed(self):
        wm = WorkingMemory(active_files={"a.py": "hello", "b.py": "world"})
        delta = compute_delta(wm, {"a.py": "hello"}, "msg")
        assert "b.py" in delta.files_removed

    def test_file_changed(self):
        wm = WorkingMemory(active_files={"a.py": "hello"})
        delta = compute_delta(wm, {"a.py": "hello world"}, "msg")
        assert "a.py" in delta.files_changed
        assert "hello world" in delta.files_changed["a.py"] or "+" in delta.files_changed["a.py"]

    def test_tool_results_forwarded(self):
        wm = WorkingMemory()
        results = [{"tool": "bash", "output": "ok"}]
        delta = compute_delta(wm, {}, "msg", new_tool_results=results)
        assert len(delta.new_tool_results) == 1

    def test_hash_based_detection(self):
        """When active_files content unavailable but hashes exist, detect change via hash."""
        wm = WorkingMemory(
            active_files={},
            active_file_hashes={"a.py": _content_hash("old content")},
        )
        delta = compute_delta(wm, {"a.py": "new content"}, "msg")
        assert "a.py" in delta.files_added # treated as added since full content not in memory


# ── build_delta_prompt ─────────────────────────────────────────────────


class TestBuildDeltaPrompt:
    def test_basic_prompt(self):
        wm = WorkingMemory(
            session_summary="building feature X",
            key_decisions=["chose React"],
            pending_tasks=["write tests"],
            turn_count=7,
            active_files={"app.py": "code"},
        )
        delta = ContextDelta(
            new_user_message="now add auth",
            files_changed={"app.py": "--- diff ---"},
        )
        prompt = build_delta_prompt(wm, delta)
        assert "[Working Memory]" in prompt
        assert "turn 7" in prompt
        assert "building feature X" in prompt
        assert "chose React" in prompt
        assert "write tests" in prompt
        assert "[Since Last Turn]" in prompt
        assert "now add auth" in prompt
        assert "app.py" in prompt

    def test_empty_delta(self):
        wm = WorkingMemory(turn_count=1)
        delta = ContextDelta()
        prompt = build_delta_prompt(wm, delta)
        assert "[Working Memory]" in prompt
        assert "[Since Last Turn]" in prompt

    def test_tool_results_in_prompt(self):
        wm = WorkingMemory(turn_count=3)
        delta = ContextDelta(
            new_user_message="check output",
            new_tool_results=[{"tool": "bash", "output": "success"}],
        )
        prompt = build_delta_prompt(wm, delta)
        assert "bash" in prompt
        assert "success" in prompt

    def test_truncates_long_tool_output(self):
        wm = WorkingMemory(turn_count=3)
        delta = ContextDelta(
            new_user_message="check",
            new_tool_results=[{"tool": "bash", "output": "x" * 5000}],
        )
        prompt = build_delta_prompt(wm, delta)
        assert "[truncated]" in prompt


# ── detect_confusion ───────────────────────────────────────────────────


class TestDetectConfusion:
    @pytest.mark.parametrize("text", [
        "I don't have access to that file",
        "What file are you referring to?",
        "Could you share the file contents?",
        "I'm not sure which file you mean",
        "I don't see that file in the context",
        "I'm unable to access the code",
        "No file was provided",
    ])
    def test_detects_confusion(self, text):
        assert detect_confusion(text) is True

    @pytest.mark.parametrize("text", [
        "Here is the implementation",
        "I've updated the file",
        "The function works correctly",
        "Let me read the file for you",
    ])
    def test_no_false_positive(self, text):
        assert detect_confusion(text) is False


# ── WorkingMemoryManager ───────────────────────────────────────────────


class TestWorkingMemoryManager:
    @pytest.fixture
    def tmp_repo(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def mgr(self, tmp_repo):
        return WorkingMemoryManager(repo_root=tmp_repo, max_context_tokens=100_000)

    def test_init_session(self, mgr):
        mem = mgr.init_session()
        assert mem is not None
        assert mem.turn_count == 0
        assert mgr.memory is mem

    def test_reset(self, mgr):
        mgr.init_session()
        mgr.memory.turn_count = 10
        mgr.memory.key_decisions = ["a", "b"]
        mgr.reset(new_summary="fresh start")
        assert mgr.memory.turn_count == 0
        assert mgr.memory.session_summary == "fresh start"
        assert mgr.memory.key_decisions == []

    def test_should_switch_to_delta_by_turns(self, mgr):
        mgr.init_session()
        mgr.memory.turn_count = 4
        assert mgr.should_switch_to_delta(0.1) is False
        mgr.memory.turn_count = 5
        assert mgr.should_switch_to_delta(0.1) is True

    def test_should_switch_to_delta_by_pressure(self, mgr):
        mgr.init_session()
        mgr.memory.turn_count = 1
        assert mgr.should_switch_to_delta(0.49) is False
        assert mgr.should_switch_to_delta(0.50) is True

    def test_pre_turn_full_mode(self, mgr):
        mgr.init_session()
        prompt, metrics = mgr.pre_turn(
            user_message="hello",
            current_files={},
            context_pressure=0.1,
            full_history_tokens=5000,
        )
        assert prompt == "" # empty = use full history
        assert metrics.mode == "full"
        assert metrics.tokens_saved == 0

    def test_pre_turn_delta_mode(self, mgr):
        mgr.init_session()
        mgr.memory.turn_count = 4 # will become 5 on pre_turn → triggers switch
        mgr.memory.active_files = {"a.py": "old content"}
        prompt, metrics = mgr.pre_turn(
            user_message="update the file",
            current_files={"a.py": "new content"},
            context_pressure=0.1,
            full_history_tokens=10000,
        )
        assert prompt != ""
        assert metrics.mode == "delta"
        assert "[Working Memory]" in prompt
        assert "[Since Last Turn]" in prompt
        assert metrics.tokens_saved > 0

    def test_confusion_triggers_recovery(self, mgr):
        mgr.init_session()
        mgr._delta_mode_active = True
        mgr.memory.turn_count = 6
        # simulate a turn
        mgr.pre_turn("msg", {}, 0.6, 10000)
        # model responds with confusion
        mgr.post_turn("I don't have access to that file")
        assert mgr._recovery_turn is True
        # next pre_turn should use full history (recovery)
        prompt, metrics = mgr.pre_turn("try again", {}, 0.6, 10000)
        assert prompt == ""
        assert metrics.mode == "recovery"
        # recovery is one-shot — next turn resumes delta
        assert mgr._recovery_turn is False

    def test_persistence_roundtrip(self, mgr, tmp_repo):
        mgr.init_session()
        mgr.memory.session_summary = "test session"
        mgr.memory.turn_count = 7
        mgr.memory.key_decisions = ["decided X"]
        mgr._persist_to_disk()
        # create new manager, should load persisted state
        mgr2 = WorkingMemoryManager(repo_root=tmp_repo)
        mem = mgr2.init_session()
        assert mem.session_summary == "test session"
        assert mem.turn_count == 7
        assert "decided X" in mem.key_decisions

    def test_persistence_survives_restart(self, tmp_repo):
        """Working memory persists across manager instances (simulating server restart)."""
        mgr1 = WorkingMemoryManager(repo_root=tmp_repo)
        mgr1.init_session()
        mgr1.memory.session_summary = "important context"
        mgr1.memory.turn_count = 12
        mgr1.memory.total_tokens_saved = 5000
        mgr1._persist_to_disk()
        del mgr1
        mgr2 = WorkingMemoryManager(repo_root=tmp_repo)
        mem = mgr2.init_session()
        assert mem.session_summary == "important context"
        assert mem.turn_count == 12
        assert mem.total_tokens_saved == 5000

    def test_decision_extraction(self, mgr):
        mgr.init_session()
        mgr.post_turn("I decided to use SQLite for storage and switched to async IO")
        assert any("decided" in d.lower() for d in mgr.memory.key_decisions)
        assert any("switched" in d.lower() for d in mgr.memory.key_decisions)

    def test_decision_cap(self, mgr):
        mgr.init_session()
        for i in range(40):
            mgr.memory.key_decisions.append(f"decided item {i}")
        mgr.post_turn("decided another thing here for testing")
        assert len(mgr.memory.key_decisions) <= 21 # 20 kept + 1 new max

    def test_get_savings_report(self, mgr):
        mgr.init_session()
        # simulate several turns
        for i in range(3):
            mgr.pre_turn(f"msg {i}", {}, 0.1, 5000)
        mgr._delta_mode_active = True
        mgr.memory.active_files = {"a.py": "content"}
        for i in range(5):
            mgr.pre_turn(f"delta msg {i}", {"a.py": "content"}, 0.6, 10000)
        report = mgr.get_savings_report()
        assert report["turns"] == 8
        assert report["delta_turns"] > 0
        assert "avg_savings_pct" in report

    def test_compact_resets_working_memory(self, mgr):
        """Simulates /compact resetting working memory."""
        mgr.init_session()
        mgr._delta_mode_active = True
        mgr.memory.turn_count = 15
        mgr.memory.key_decisions = ["a", "b", "c"]
        mgr.memory.active_files = {"big.py": "x" * 10000}
        mem = mgr.reset(new_summary="compacted: user building auth feature")
        assert mem.turn_count == 0
        assert mem.key_decisions == []
        assert mem.active_files == {}
        assert "compacted" in mem.session_summary
        assert mgr._delta_mode_active is False


# ── token savings simulation ───────────────────────────────────────────


class TestTokenSavingsSimulation:
    """Simulate a 20-turn session and verify delta mode saves tokens."""

    def test_20_turn_session_savings(self, tmp_path):
        mgr = WorkingMemoryManager(
            repo_root=tmp_path,
            max_context_tokens=100_000,
            hybrid_turn_threshold=5,
        )
        mgr.init_session()
        # simulate growing file context
        base_file = "x" * 2000 # ~500 tokens
        files = {"main.py": base_file, "utils.py": base_file, "test.py": base_file}
        full_history_growth = 0
        for turn in range(20):
            full_history_growth += 500 # each turn adds ~500 tokens of history
            full_tokens = 1500 + full_history_growth # base files + accumulated history
            # small file change each turn
            files["main.py"] = base_file + f"\n# turn {turn}"
            prompt, metrics = mgr.pre_turn(
                user_message=f"turn {turn}: update main.py",
                current_files=files,
                context_pressure=full_tokens / 100_000,
                full_history_tokens=full_tokens,
            )
            mgr.post_turn(f"done with turn {turn}")
        report = mgr.get_savings_report()
        # turn 5 triggers switch (turn_count incremented then checked), so 4 full + 16 delta
        assert report["full_turns"] == 4
        assert report["delta_turns"] == 16
        assert report["total_tokens_saved"] > 0
        # with 15 delta turns saving tokens, average should be meaningful
        assert report["avg_savings_pct"] > 0

    def test_savings_report_format(self, tmp_path):
        mgr = WorkingMemoryManager(repo_root=tmp_path)
        mgr.init_session()
        report = mgr.get_savings_report()
        expected_keys = {"turns", "delta_turns", "full_turns", "recovery_turns",
                         "total_tokens_saved", "avg_savings_pct", "cumulative_saved"}
        assert set(report.keys()) == expected_keys


# ── helper function tests ──────────────────────────────────────────────


class TestHelpers:
    def test_content_hash_deterministic(self):
        assert _content_hash("hello") == _content_hash("hello")
        assert _content_hash("hello") != _content_hash("world")

    def test_estimate_tokens(self):
        assert _estimate_tokens("") == 1 # minimum
        assert _estimate_tokens("a" * 100) == 25

    def test_unified_diff(self):
        diff = _unified_diff("line1\nline2\n", "line1\nline3\n", "test.py")
        assert "-line2" in diff
        assert "+line3" in diff

    def test_unified_diff_no_change(self):
        diff = _unified_diff("same\n", "same\n", "test.py")
        assert diff == ""


# ── async re-summarization ─────────────────────────────────────────────


class TestResummarization:
    @pytest.mark.asyncio
    async def test_resummarize_with_llm(self, tmp_path):
        mgr = WorkingMemoryManager(repo_root=tmp_path)
        mgr.init_session()
        mgr.memory.session_summary = "old summary"
        callback = AsyncMock(return_value="new LLM summary")
        mgr.set_summary_callback(callback)
        result = await mgr.resummarize_with_llm("user: do X\nassistant: done")
        assert result == "new LLM summary"
        assert mgr.memory.session_summary == "new LLM summary"
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_resummarize_fallback_on_error(self, tmp_path):
        mgr = WorkingMemoryManager(repo_root=tmp_path)
        mgr.init_session()
        mgr.memory.session_summary = "original"
        callback = AsyncMock(side_effect=Exception("LLM down"))
        mgr.set_summary_callback(callback)
        result = await mgr.resummarize_with_llm("history")
        assert result == "original" # falls back to existing

    @pytest.mark.asyncio
    async def test_resummarize_no_callback(self, tmp_path):
        mgr = WorkingMemoryManager(repo_root=tmp_path)
        mgr.init_session()
        mgr.memory.session_summary = "current"
        result = await mgr.resummarize_with_llm("history")
        assert result == "current"
