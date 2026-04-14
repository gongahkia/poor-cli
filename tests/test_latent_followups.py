"""Tests for the latent follow-ups: provider abstraction, autotuner, pipeline."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from poor_cli.research.latent_autotune import (
    DEFAULT_STEPS,
    MIN_SAMPLES_FOR_TUNING,
    STEP_BOUNDS,
    LatentStepAutotuner,
)
from poor_cli.research.latent_pipeline import (
    LatentPipeline,
    PipelineStage,
    fall_back_to_text,
)
from poor_cli.research.latent_provider import (
    BridgeLatentProvider,
    InProcessLatentProvider,
    LatentSpec,
    build_latent_provider,
)


# ──────────────────────────────────────────────────────────────────────────
# LatentProvider abstraction
# ──────────────────────────────────────────────────────────────────────────

class _FakeBackendCfg:
    def __init__(self, model_id="Qwen/Qwen2.5-7B", hidden_dim=4096, dtype="bfloat16"):
        self.model_id = model_id
        self.hidden_dim = hidden_dim
        self.dtype = dtype
        self.server_version = "0.1.0"


class _FakeBackend:
    backend_name = "vllm"

    def __init__(self, cfg=None, encode_result="hidden", generate_text="generated text"):
        self.config = cfg or _FakeBackendCfg()
        self._encode_result = encode_result
        self._generate_text = generate_text

    async def encode(self, prompt):
        return MagicMock(prompt=prompt, hidden=self._encode_result)

    async def generate_from_latent(self, latent_msg, *, max_new_tokens=512):
        result = MagicMock()
        result.text = self._generate_text
        return result


class _FakeAgent:
    def __init__(self, model_id="Qwen/Qwen2.5-7B", hidden_dim=4096, dtype="bfloat16"):
        cfg = MagicMock()
        cfg._name_or_path = model_id
        cfg.hidden_size = hidden_dim
        model = MagicMock()
        model.config = cfg
        model.dtype = dtype
        self.model = model

    def encode(self, prompt):
        return f"latent({prompt})"

    def decode_from_latent(self, latent_msg, *, max_new_tokens=512):
        return f"decoded:{latent_msg}"


class LatentProviderTests(unittest.TestCase):
    def test_inprocess_spec_extracted_from_agent(self):
        provider = InProcessLatentProvider(_FakeAgent())
        self.assertEqual(provider.spec.backend, "hf_local")
        self.assertEqual(provider.spec.transport, "in_process")
        self.assertEqual(provider.spec.hidden_dim, 4096)

    def test_bridge_spec_extracted_from_backend(self):
        provider = BridgeLatentProvider(_FakeBackend())
        self.assertEqual(provider.spec.backend, "vllm")
        self.assertEqual(provider.spec.transport, "http")
        self.assertEqual(provider.spec.hidden_dim, 4096)

    def test_compatible_when_specs_match(self):
        a = InProcessLatentProvider(_FakeAgent(model_id="Qwen/Qwen2.5-7B"))
        b = BridgeLatentProvider(_FakeBackend(_FakeBackendCfg(model_id="Qwen/Qwen2.5-7B")))
        self.assertTrue(a.compatible_with(b))

    def test_incompatible_on_model_mismatch(self):
        a = InProcessLatentProvider(_FakeAgent(model_id="Qwen/Qwen2.5-7B"))
        b = BridgeLatentProvider(_FakeBackend(_FakeBackendCfg(model_id="other/model")))
        self.assertFalse(a.compatible_with(b))

    def test_incompatible_on_hidden_dim_mismatch(self):
        a = InProcessLatentProvider(_FakeAgent(hidden_dim=4096))
        b = BridgeLatentProvider(_FakeBackend(_FakeBackendCfg(hidden_dim=5120)))
        self.assertFalse(a.compatible_with(b))

    def test_async_encode_decode_roundtrip(self):
        provider = InProcessLatentProvider(_FakeAgent())
        latent = asyncio.run(provider.encode("hello"))
        text = asyncio.run(provider.generate_from_latent(latent))
        self.assertIn("hello", latent)
        self.assertIn("decoded", text)

    def test_factory_hf_local_requires_agent(self):
        with self.assertRaises(ValueError):
            build_latent_provider(backend="hf_local")
        provider = build_latent_provider(backend="hf_local", agent=_FakeAgent())
        self.assertIsInstance(provider, InProcessLatentProvider)

    def test_factory_other_backend_requires_backend_obj(self):
        with self.assertRaises(ValueError):
            build_latent_provider(backend="vllm")
        provider = build_latent_provider(backend="vllm", backend_obj=_FakeBackend())
        self.assertIsInstance(provider, BridgeLatentProvider)


# ──────────────────────────────────────────────────────────────────────────
# Latent step autotuner
# ──────────────────────────────────────────────────────────────────────────

class LatentAutotunerTests(unittest.TestCase):
    def test_default_when_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            tuner = LatentStepAutotuner(Path(tmp))
            report = tuner.recommend_steps("trivial")
            self.assertEqual(report.recommended_steps, DEFAULT_STEPS["trivial"])
            self.assertTrue(report.fell_back_to_default)

    def test_default_until_min_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            tuner = LatentStepAutotuner(Path(tmp))
            for _ in range(MIN_SAMPLES_FOR_TUNING - 1):
                tuner.record("simple", 4, 0.5)
            report = tuner.recommend_steps("simple")
            self.assertTrue(report.fell_back_to_default)

    def test_recommends_best_reward_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            tuner = LatentStepAutotuner(Path(tmp))
            for _ in range(5):
                tuner.record("moderate", 8, 0.2)
                tuner.record("moderate", 16, 0.9)
                tuner.record("moderate", 32, 0.4)
            report = tuner.recommend_steps("moderate")
            self.assertFalse(report.fell_back_to_default)
            self.assertEqual(report.recommended_steps, 16)

    def test_clamps_to_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            tuner = LatentStepAutotuner(Path(tmp))
            # log a step value above the trivial ceiling
            for _ in range(10):
                tuner.record("trivial", 100, 0.95)
            report = tuner.recommend_steps("trivial")
            lo, hi = STEP_BOUNDS["trivial"]
            self.assertLessEqual(report.recommended_steps, hi)

    def test_unknown_task_type_falls_back_to_moderate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tuner = LatentStepAutotuner(Path(tmp))
            report = tuner.recommend_steps("mystery")
            self.assertEqual(report.task_type, "moderate")
            self.assertEqual(report.recommended_steps, DEFAULT_STEPS["moderate"])

    def test_explore_grid_returns_candidates(self):
        tuner = LatentStepAutotuner()
        grid = tuner.explore_grid("simple")
        self.assertGreater(len(grid), 1)
        self.assertEqual(grid, sorted(grid))

    def test_records_persist_across_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            t1 = LatentStepAutotuner(Path(tmp))
            for _ in range(5):
                t1.record("complex", 32, 0.8)
                t1.record("complex", 48, 0.9)
            t2 = LatentStepAutotuner(Path(tmp))
            report = t2.recommend_steps("complex")
            self.assertFalse(report.fell_back_to_default)
            self.assertIn(report.recommended_steps, (32, 48))


# ──────────────────────────────────────────────────────────────────────────
# Hierarchical pipeline
# ──────────────────────────────────────────────────────────────────────────

class LatentPipelineTests(unittest.TestCase):
    def _stage(self, name, model_id="Qwen/Qwen2.5-7B"):
        provider = InProcessLatentProvider(_FakeAgent(model_id=model_id))
        return PipelineStage(name=name, provider=provider)

    def test_requires_at_least_two_stages(self):
        with self.assertRaises(ValueError):
            LatentPipeline([])
        with self.assertRaises(ValueError):
            LatentPipeline([self._stage("a")])

    def test_rejects_incompatible_stages(self):
        s1 = self._stage("a", model_id="Qwen/Qwen2.5-7B")
        s2 = self._stage("b", model_id="meta-llama/Llama-3-8B")
        with self.assertRaises(ValueError):
            LatentPipeline([s1, s2])

    def test_two_stage_pipeline_executes(self):
        pipeline = LatentPipeline([self._stage("architect"), self._stage("editor")])
        result = asyncio.run(pipeline.run("solve x=1+1"))
        self.assertEqual(result.stages_executed, 2)
        self.assertIn("decoded", result.text)
        self.assertIsNone(result.error)

    def test_three_stage_pipeline_executes(self):
        pipeline = LatentPipeline([
            self._stage("planner"),
            self._stage("reviewer"),
            self._stage("editor"),
        ])
        result = asyncio.run(pipeline.run("refactor auth"))
        self.assertEqual(result.stages_executed, 3)
        self.assertEqual(pipeline.stages[1].role, "intermediate")

    def test_stage_failure_aborts_pipeline(self):
        class _BrokenAgent(_FakeAgent):
            def encode(self, prompt):
                raise RuntimeError("nope")

        s1 = PipelineStage(name="bad", provider=InProcessLatentProvider(_BrokenAgent()))
        s2 = self._stage("editor")
        pipeline = LatentPipeline([s1, s2])
        result = asyncio.run(pipeline.run("hi"))
        self.assertIsNotNone(result.error)
        self.assertEqual(result.aborted_at, "bad")

    def test_fall_back_to_text_helper(self):
        stages = [self._stage("plan"), self._stage("review"), self._stage("edit")]
        text = fall_back_to_text(stages, "do the work")
        self.assertIn("plan → review → edit", text)
        self.assertIn("do the work", text)

    def test_role_normalization(self):
        s1 = self._stage("a")
        s2 = self._stage("b")
        s3 = self._stage("c")
        # input roles are wrong; constructor must normalize
        s1.role = "intermediate"
        s2.role = "architect"
        s3.role = "intermediate"
        pipeline = LatentPipeline([s1, s2, s3])
        self.assertEqual(pipeline.stages[0].role, "architect")
        self.assertEqual(pipeline.stages[1].role, "intermediate")
        self.assertEqual(pipeline.stages[2].role, "editor")


if __name__ == "__main__":
    unittest.main()
