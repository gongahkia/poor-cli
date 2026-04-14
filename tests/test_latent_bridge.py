"""Tests for M5 latent bridge research prototype."""

from __future__ import annotations

import asyncio
import unittest

from poor_cli.research.latent_bridge import (
    LatentBridgeConfig,
    LatentIncompatibility,
    LatentTensorSpec,
    VLLMLatentBackend,
    benchmark_note_for_backend,
    build_backend,
    compatibility_check,
    supported_backends,
)


def _config(**overrides) -> LatentBridgeConfig:
    base = dict(
        model_id="Qwen/Qwen2.5-7B",
        tokenizer_id="Qwen/Qwen2.5-7B",
        hidden_dim=4096,
        num_layers=32,
        num_heads=32,
        head_dim=128,
        dtype="bfloat16",
        vocab_size=152064,
        backend="vllm",
    )
    base.update(overrides)
    return LatentBridgeConfig(**base)


class LatentTensorSpecTests(unittest.TestCase):
    def test_header_roundtrip(self):
        spec = LatentTensorSpec(
            name="hidden_states", dtype="bfloat16", shape=[1, 32, 4096],
            checksum="abc", metadata={"step": 0},
        )
        header = spec.to_header()
        back = LatentTensorSpec.from_header(header)
        self.assertEqual(back.name, spec.name)
        self.assertEqual(back.shape, spec.shape)
        self.assertEqual(back.checksum, spec.checksum)

    def test_checksum_compute_and_verify(self):
        payload = b"tensor bytes here"
        checksum = LatentTensorSpec.compute_checksum(payload)
        self.assertEqual(len(checksum), 64)  # sha256 hex
        spec = LatentTensorSpec(name="h", dtype="float32", shape=[1, 4], checksum=checksum)
        self.assertTrue(spec.verify_checksum(payload))
        self.assertFalse(spec.verify_checksum(b"tampered"))

    def test_empty_checksum_skips_verification(self):
        spec = LatentTensorSpec(name="h", dtype="float32", shape=[1, 4])
        self.assertTrue(spec.verify_checksum(b"anything"))


class LatentBridgeConfigTests(unittest.TestCase):
    def test_identity_hash_stable(self):
        cfg_a = _config()
        cfg_b = _config()
        self.assertEqual(cfg_a.identity_hash(), cfg_b.identity_hash())
        self.assertEqual(len(cfg_a.identity_hash()), 16)

    def test_identity_hash_changes_on_dim_change(self):
        self.assertNotEqual(_config().identity_hash(), _config(hidden_dim=5120).identity_hash())


class CompatibilityCheckTests(unittest.TestCase):
    def test_matching_configs_empty_errors(self):
        self.assertEqual(compatibility_check(_config(), _config()), [])

    def test_model_mismatch_detected(self):
        errors = compatibility_check(_config(), _config(model_id="meta-llama/Llama-3.1-8B"))
        self.assertTrue(any("model_id" in e for e in errors))

    def test_dtype_mismatch_detected(self):
        errors = compatibility_check(_config(), _config(dtype="float16"))
        self.assertTrue(any("dtype" in e for e in errors))

    def test_multiple_mismatches_reported(self):
        errors = compatibility_check(_config(), _config(model_id="other", hidden_dim=2048))
        self.assertGreaterEqual(len(errors), 2)


class BackendFactoryTests(unittest.TestCase):
    def test_supported_backends_includes_vllm(self):
        self.assertIn("vllm", supported_backends())

    def test_build_vllm_backend(self):
        backend = build_backend("vllm", _config())
        self.assertIsInstance(backend, VLLMLatentBackend)
        self.assertEqual(backend.backend_name, "vllm")

    def test_build_unknown_backend_raises(self):
        with self.assertRaises(NotImplementedError) as ctx:
            build_backend("ollama", _config(backend="ollama"))
        self.assertIn("Feasibility", str(ctx.exception))

    def test_feasibility_notes_for_every_backend(self):
        for name in ("vllm", "sglang", "hf_tgi", "llama_server", "ollama", "lmstudio", "hf_local"):
            note = benchmark_note_for_backend(name)
            self.assertTrue(note.strip())
            self.assertGreater(len(note), 20)

    def test_unknown_backend_note(self):
        self.assertIn("unknown", benchmark_note_for_backend("mystery-backend").lower())


class VLLMBackendStubTests(unittest.TestCase):
    def test_encode_not_implemented(self):
        backend = VLLMLatentBackend(_config())
        with self.assertRaises(NotImplementedError) as ctx:
            asyncio.run(backend.encode("prompt"))
        self.assertIn("M5_LATENT_BRIDGE.md", str(ctx.exception))

    def test_generate_not_implemented(self):
        backend = VLLMLatentBackend(_config())
        from poor_cli.research.latent_bridge import LatentEncodeResult, LatentTensorSpec
        fake = LatentEncodeResult(
            hidden_states=LatentTensorSpec(name="hs", dtype="bfloat16", shape=[1, 1, 4096])
        )
        with self.assertRaises(NotImplementedError):
            asyncio.run(backend.generate_from_latent(fake))

    def test_health_check_returns_dict(self):
        backend = VLLMLatentBackend(_config(), base_url="http://localhost:65432")
        # unreachable URL → available=False + reason
        result = asyncio.run(backend.health_check())
        self.assertFalse(result["available"])
        self.assertIn("reason", result)


if __name__ == "__main__":
    unittest.main()
