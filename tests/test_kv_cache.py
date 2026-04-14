"""Tests for poor-cli.kv_cache_store — position-independent KV cache."""

import asyncio
import json
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from poor_cli.kv_cache_store import (
    KVCacheStore,
    CacheEntry,
    CacheStats,
    TTFTMeasurement,
    is_local_inference,
    build_cache_friendly_prompt,
    maybe_init_kv_cache,
)

def _run(coro):
    """Run async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "kv_cache"


@pytest.fixture
def store(cache_dir):
    return KVCacheStore(cache_dir=cache_dir, model="llama3.1:8b", max_size_mb=100, ttl_seconds=3600)


# -- hashing & keys --

class TestHashing:
    def test_content_hash_deterministic(self):
        h1 = KVCacheStore.content_hash("hello world")
        h2 = KVCacheStore.content_hash("hello world")
        assert h1 == h2

    def test_content_hash_differs(self):
        assert KVCacheStore.content_hash("a") != KVCacheStore.content_hash("b")

    def test_cache_key_includes_model(self, store):
        k1 = store.cache_key("f.py", "code")
        store2 = KVCacheStore(cache_dir=store.cache_dir, model="qwen2.5:7b")
        k2 = store2.cache_key("f.py", "code")
        assert k1 != k2 # different model → different key


# -- has / get --

class TestLookup:
    def test_has_miss(self, store):
        assert store.has("missing.py", "content") is False

    def test_get_miss_increments_stat(self, store):
        assert store.get("missing.py", "content") is None
        assert store._stats.miss_count == 1

    def test_has_after_manual_insert(self, store):
        key = store.cache_key("a.py", "code")
        entry = CacheEntry(filepath="a.py", content_hash=store.content_hash("code"),
                           model="llama3.1:8b", created_at=time.time(), size_bytes=10)
        store._manifest[key] = entry
        assert store.has("a.py", "code") is True

    def test_ttl_expiry(self, store):
        key = store.cache_key("old.py", "x")
        entry = CacheEntry(filepath="old.py", content_hash=store.content_hash("x"),
                           model="llama3.1:8b", created_at=time.time() - 7200, size_bytes=10)
        store._manifest[key] = entry
        assert store.has("old.py", "x") is False # expired (ttl=3600)


# -- invalidation --

class TestInvalidation:
    def test_invalidate_specific(self, store):
        key = store.cache_key("f.py", "v1")
        entry = CacheEntry(filepath="f.py", content_hash=store.content_hash("v1"),
                           model="llama3.1:8b", created_at=time.time(), size_bytes=50)
        store._manifest[key] = entry
        store._stats.total_size_bytes = 50
        store._stats.total_entries = 1
        assert store.invalidate("f.py", "v1") is True
        assert store.has("f.py", "v1") is False

    def test_invalidate_file_all_versions(self, store):
        for i, content in enumerate(["v1", "v2", "v3"]):
            key = store.cache_key("f.py", content)
            store._manifest[key] = CacheEntry(
                filepath="f.py", content_hash=store.content_hash(content),
                model="llama3.1:8b", created_at=time.time(), size_bytes=10)
        store._stats.total_entries = 3
        store._stats.total_size_bytes = 30
        removed = store.invalidate_file("f.py")
        assert removed == 3
        assert len(store._manifest) == 0

    def test_clear(self, store):
        for i in range(5):
            key = store.cache_key(f"f{i}.py", "x")
            store._manifest[key] = CacheEntry(
                filepath=f"f{i}.py", content_hash=store.content_hash("x"),
                model="llama3.1:8b", created_at=time.time(), size_bytes=10)
        store._stats.total_entries = 5
        store._stats.total_size_bytes = 50
        store.clear()
        assert len(store._manifest) == 0
        assert store._stats.total_size_bytes <= 0


# -- size enforcement --

class TestSizeLimit:
    def test_evicts_oldest_when_over_limit(self):
        store = KVCacheStore(cache_dir=Path("/tmp/test_kv_limit"), model="m", max_size_mb=0) # 0 MB limit
        old_key = store.cache_key("old.py", "old")
        store._manifest[old_key] = CacheEntry(
            filepath="old.py", content_hash=store.content_hash("old"),
            model="m", created_at=time.time() - 100, size_bytes=1000)
        store._stats.total_size_bytes = 1000
        store._stats.total_entries = 1
        store._enforce_size_limit()
        assert len(store._manifest) == 0


# -- manifest persistence --

class TestManifest:
    def test_save_and_reload(self, cache_dir):
        store = KVCacheStore(cache_dir=cache_dir, model="m")
        key = store.cache_key("f.py", "c")
        store._manifest[key] = CacheEntry(
            filepath="f.py", content_hash=store.content_hash("c"),
            model="m", created_at=time.time(), size_bytes=42)
        store._save_manifest()
        store2 = KVCacheStore(cache_dir=cache_dir, model="m")
        assert key in store2._manifest
        assert store2._manifest[key].size_bytes == 42


# -- precompute (mocked vLLM) --

def _mock_vllm_session(prompt_tokens=100):
    """Build a mock aiohttp session that mimics vLLM /v1/completions."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"usage": {"prompt_tokens": prompt_tokens}})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


class TestPrecompute:
    def test_precompute_lmcache(self, store):
        async def _go():
            with patch("poor_cli.kv_cache_store.aiohttp.ClientSession", return_value=_mock_vllm_session(100)):
                return await store.precompute("test.py", "def hello(): pass")
        entry = _run(_go())
        assert entry.filepath == "test.py"
        assert entry.token_count == 100
        assert store.has("test.py", "def hello(): pass")

    def test_precompute_idempotent(self, store):
        key = store.cache_key("f.py", "code")
        existing = CacheEntry(filepath="f.py", content_hash=store.content_hash("code"),
                              model="llama3.1:8b", created_at=time.time(), size_bytes=10, token_count=50)
        store._manifest[key] = existing
        result = _run(store.precompute("f.py", "code"))
        assert result.token_count == 50 # returned existing, no new request

    def test_precompute_batch(self, store):
        files = [("a.py", "aaa"), ("b.py", "bbb"), ("c.py", "ccc")]
        async def _go():
            with patch("poor_cli.kv_cache_store.aiohttp.ClientSession", return_value=_mock_vllm_session(10)):
                return await store.precompute_batch(files, concurrency=2)
        entries = _run(_go())
        assert len(entries) == 3
        assert all(e.token_count == 10 for e in entries)


# -- cache-friendly prompt builder --

class TestPromptBuilder:
    def test_cached_files_ordered_first(self, store):
        key = store.cache_key("cached.py", "cached_content")
        store._manifest[key] = CacheEntry(
            filepath="cached.py", content_hash=store.content_hash("cached_content"),
            model="llama3.1:8b", created_at=time.time(), size_bytes=10)
        files = [("uncached.py", "uc"), ("cached.py", "cached_content")]
        prompt = build_cache_friendly_prompt(files, "explain this", store=store)
        cached_pos = prompt.index("cached.py")
        uncached_pos = prompt.index("uncached.py")
        assert cached_pos < uncached_pos # cached file comes first

    def test_no_store_passthrough(self):
        files = [("a.py", "aaa"), ("b.py", "bbb")]
        prompt = build_cache_friendly_prompt(files, "query", store=None)
        assert "### a.py" in prompt
        assert "### Query" in prompt


# -- is_local_inference --

class TestLocalDetection:
    @pytest.mark.parametrize("provider,expected", [
        ("ollama", True), ("vllm", True), ("sglang", True), ("llama_server", True),
        ("hf_tgi", True), ("lmstudio", True), ("hf_local", True),
        ("openai", False), ("anthropic", False), ("gemini", False),
    ])
    def test_detection(self, provider, expected):
        assert is_local_inference(provider) == expected


# -- maybe_init_kv_cache gating --

class TestGating:
    def test_disabled_returns_none(self):
        cfg = MagicMock()
        cfg.kv_cache.enabled = False
        assert _run(maybe_init_kv_cache(cfg)) is None

    def test_non_local_provider_returns_none(self):
        cfg = MagicMock()
        cfg.kv_cache.enabled = True
        cfg.model.provider = "openai"
        assert _run(maybe_init_kv_cache(cfg)) is None

    def test_local_provider_returns_store(self, tmp_path):
        cfg = MagicMock()
        cfg.kv_cache.enabled = True
        cfg.kv_cache.backend = "vllm"
        cfg.kv_cache.cache_dir = str(tmp_path / "kv")
        cfg.kv_cache.max_cache_size_mb = 100
        cfg.kv_cache.ttl_seconds = 3600
        cfg.kv_cache.vllm_api_base = "http://localhost:8000"
        cfg.model.provider = "vllm"
        cfg.model.model_name = "llama3.1:8b"
        store = _run(maybe_init_kv_cache(cfg))
        assert store is not None
        assert isinstance(store, KVCacheStore)


# -- CacheEntry serialization --

class TestCacheEntry:
    def test_roundtrip(self):
        e = CacheEntry(filepath="f.py", content_hash="abc", model="m",
                       created_at=1000.0, size_bytes=42, token_count=10)
        d = e.to_dict()
        e2 = CacheEntry.from_dict(d)
        assert e2.filepath == e.filepath
        assert e2.size_bytes == e.size_bytes

    def test_from_dict_ignores_extra_keys(self):
        d = {"filepath": "f.py", "content_hash": "h", "model": "m",
             "created_at": 0.0, "size_bytes": 0, "token_count": 0, "extra": "ignored"}
        e = CacheEntry.from_dict(d)
        assert e.filepath == "f.py"
