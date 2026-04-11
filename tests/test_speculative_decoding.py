"""Tests for speculative decoding integration."""

import pytest
from dataclasses import dataclass
from poor_cli.speculative_decoding import (
    DRAFT_MODEL_PAIRS,
    resolve_draft_model,
    is_local_provider,
    is_spec_decode_available,
    SpeculativeMetrics,
    SpeculativeDecodingManager,
    build_vllm_launch_args,
    vllm_launch_command,
    get_metrics,
)


class TestDraftModelPairing:
    def test_known_pair(self):
        assert resolve_draft_model("llama3.1:70b") == "llama3.1:8b"

    def test_qwen_pair(self):
        assert resolve_draft_model("qwen2.5-coder:32b") == "qwen2.5-coder:1.5b"

    def test_codellama_pair(self):
        assert resolve_draft_model("codellama:34b") == "codellama:7b"

    def test_unknown_model_returns_none(self):
        assert resolve_draft_model("some-random-model:99b") is None

    def test_case_insensitive(self):
        assert resolve_draft_model("Llama3.1:70b") == "llama3.1:8b"

    def test_all_pairs_have_values(self):
        for main, draft in DRAFT_MODEL_PAIRS.items():
            assert main, "empty main model key"
            assert draft, f"empty draft model for {main}"


class TestProviderDetection:
    def test_ollama_is_local(self):
        assert is_local_provider("ollama") is True

    def test_vllm_is_local(self):
        assert is_local_provider("vllm") is True

    def test_openai_not_local(self):
        assert is_local_provider("openai") is False

    def test_anthropic_not_local(self):
        assert is_local_provider("anthropic") is False

    def test_gemini_not_local(self):
        assert is_local_provider("gemini") is False

    def test_case_insensitive(self):
        assert is_local_provider("VLLM") is True

    def test_spec_decode_vllm_only(self):
        assert is_spec_decode_available("vllm", "vllm") is True
        assert is_spec_decode_available("ollama", "vllm") is True
        assert is_spec_decode_available("ollama", "ollama") is False
        assert is_spec_decode_available("openai", "vllm") is False


class TestSpeculativeMetrics:
    def test_initial_state(self):
        m = SpeculativeMetrics()
        assert m.acceptance_rate == 0.0
        assert m.speedup_factor == 1.0
        assert m.total_requests == 0

    def test_record(self):
        m = SpeculativeMetrics()
        m.record(draft_tokens=10, accepted=8)
        assert m.total_draft_tokens == 10
        assert m.accepted_tokens == 8
        assert m.rejected_tokens == 2
        assert m.total_requests == 1
        assert m.acceptance_rate == 0.8

    def test_multiple_records(self):
        m = SpeculativeMetrics()
        m.record(5, 4)
        m.record(5, 3)
        assert m.total_draft_tokens == 10
        assert m.accepted_tokens == 7
        assert m.acceptance_rate == 0.7

    def test_speedup_factor(self):
        m = SpeculativeMetrics()
        m.record(10, 9) # 90% acceptance
        # k=5, speedup = 5 * 0.9 + 1 = 5.5
        assert m.speedup_factor == 5.5

    def test_perfect_acceptance(self):
        m = SpeculativeMetrics()
        m.record(100, 100)
        assert m.acceptance_rate == 1.0
        assert m.speedup_factor == 6.0 # k=5, 5*1+1

    def test_zero_acceptance(self):
        m = SpeculativeMetrics()
        m.record(10, 0)
        assert m.acceptance_rate == 0.0
        assert m.speedup_factor == 1.0

    def test_summary(self):
        m = SpeculativeMetrics()
        m.record(10, 7)
        s = m.summary()
        assert s["total_draft_tokens"] == 10
        assert s["accepted_tokens"] == 7
        assert s["rejected_tokens"] == 3
        assert s["acceptance_rate"] == 0.7
        assert s["total_requests"] == 1

    def test_reset(self):
        m = SpeculativeMetrics()
        m.record(10, 7)
        m.reset()
        assert m.total_draft_tokens == 0
        assert m.total_requests == 0

    def test_singleton(self):
        m = get_metrics()
        assert isinstance(m, SpeculativeMetrics)


class TestVLLMLaunchArgs:
    def test_known_model(self):
        args = build_vllm_launch_args("llama3.1:70b")
        assert "--speculative-model" in args
        assert "llama3.1:8b" in args
        assert "--num-speculative-tokens" in args
        assert "5" in args

    def test_custom_draft(self):
        args = build_vllm_launch_args("custom:big", draft_model="custom:small", num_speculative_tokens=3)
        assert args == ["--speculative-model", "custom:small", "--num-speculative-tokens", "3"]

    def test_unknown_model_empty(self):
        args = build_vllm_launch_args("unknown-model:99b")
        assert args == []

    def test_launch_command(self):
        cmd = vllm_launch_command("llama3.1:70b")
        assert "vllm serve llama3.1:70b" in cmd
        assert "--speculative-model llama3.1:8b" in cmd
        assert "--num-speculative-tokens 5" in cmd

    def test_launch_command_no_pair(self):
        cmd = vllm_launch_command("unknown:99b")
        assert "vllm serve unknown:99b" in cmd
        assert "--speculative-model" not in cmd


@dataclass
class _FakeSpecDecodeConfig:
    enabled: bool = True
    backend: str = "vllm"
    draft_model: str = "auto"
    num_speculative_tokens: int = 5
    vllm_api_base: str = "http://localhost:8000"

@dataclass
class _FakeConfig:
    speculative_decoding: _FakeSpecDecodeConfig = None
    def __post_init__(self):
        if self.speculative_decoding is None:
            self.speculative_decoding = _FakeSpecDecodeConfig()


class TestSpeculativeDecodingManager:
    def test_disabled_by_default(self):
        cfg = _FakeConfig(speculative_decoding=_FakeSpecDecodeConfig(enabled=False))
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "llama3.1:70b")
        assert mgr.enabled is False

    def test_enabled_vllm_known_model(self):
        cfg = _FakeConfig()
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "llama3.1:70b")
        assert mgr.enabled is True
        assert mgr.draft_model == "llama3.1:8b"

    def test_disabled_for_closed_api(self):
        cfg = _FakeConfig()
        mgr = SpeculativeDecodingManager.from_config(cfg, "openai", "gpt-4")
        assert mgr.enabled is False

    def test_disabled_for_ollama_backend(self):
        cfg = _FakeConfig(speculative_decoding=_FakeSpecDecodeConfig(backend="ollama"))
        mgr = SpeculativeDecodingManager.from_config(cfg, "ollama", "llama3.1:70b")
        assert mgr.enabled is False

    def test_no_draft_model_disables(self):
        cfg = _FakeConfig()
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "unknown-model:99b")
        assert mgr.enabled is False

    def test_explicit_draft_model(self):
        cfg = _FakeConfig(speculative_decoding=_FakeSpecDecodeConfig(draft_model="tiny:0.5b"))
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "big:70b")
        assert mgr.enabled is True
        assert mgr.draft_model == "tiny:0.5b"

    def test_status_dict(self):
        cfg = _FakeConfig()
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "llama3.1:70b")
        s = mgr.status()
        assert s["enabled"] is True
        assert s["draft_model"] == "llama3.1:8b"
        assert "metrics" in s

    def test_launch_command(self):
        cfg = _FakeConfig()
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "llama3.1:70b")
        cmd = mgr.get_launch_command()
        assert "vllm serve" in cmd
        assert "--speculative-model" in cmd

    def test_no_config_attr(self):
        mgr = SpeculativeDecodingManager.from_config(object(), "vllm", "llama3.1:70b")
        assert mgr.enabled is False

    def test_custom_num_tokens(self):
        cfg = _FakeConfig(speculative_decoding=_FakeSpecDecodeConfig(num_speculative_tokens=8))
        mgr = SpeculativeDecodingManager.from_config(cfg, "vllm", "llama3.1:70b")
        assert mgr.num_speculative_tokens == 8
