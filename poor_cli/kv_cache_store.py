"""
Position-independent KV cache store for local inference (vLLM + LMCache).

Pre-computes KV caches for repo files and reuses them across prompts.
Only works with self-hosted inference — NOT with closed API providers.

Backend support:
  - vLLM + LMCache: full KV cache precompute/reuse via LMCache's disk backend
  - vLLM standalone: prefix caching via --enable-prefix-caching
  - Ollama: no KV cache API; only cache-friendly prompt ordering applied
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    filepath: str
    content_hash: str
    model: str
    created_at: float
    size_bytes: int = 0
    token_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CacheEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CacheStats:
    total_entries: int = 0
    total_size_bytes: int = 0
    hit_count: int = 0
    miss_count: int = 0
    precompute_duration_ms: float = 0
    last_ttft_cached_ms: float = 0
    last_ttft_cold_ms: float = 0


@dataclass
class TTFTMeasurement:
    cached_ms: float
    cold_ms: float
    speedup: float # cold / cached


# ---------------------------------------------------------------------------
# KVCacheStore
# ---------------------------------------------------------------------------

class KVCacheStore:
    """Manages pre-computed KV caches for local inference backends."""

    MANIFEST_FILE = "manifest.json"

    def __init__(self, cache_dir: Path, model: str, *,
                 max_size_mb: int = 5000, ttl_seconds: int = 86400,
                 backend: str = "lmcache",
                 vllm_api_base: str = "http://localhost:8000"):
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.ttl_seconds = ttl_seconds
        self.backend = backend
        self.vllm_api_base = vllm_api_base.rstrip("/")
        self._manifest: Dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._ensure_dirs()
        self._load_manifest()

    # -- dir / manifest --

    def _ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self) -> Path:
        return self.cache_dir / self.MANIFEST_FILE

    def _load_manifest(self) -> None:
        mp = self._manifest_path()
        if mp.exists():
            try:
                data = json.loads(mp.read_text())
                self._manifest = {k: CacheEntry.from_dict(v) for k, v in data.items()}
                self._stats.total_entries = len(self._manifest)
                self._stats.total_size_bytes = sum(e.size_bytes for e in self._manifest.values())
            except Exception as exc:
                logger.warning("corrupt kv cache manifest, resetting: %s", exc)
                self._manifest = {}

    def _save_manifest(self) -> None:
        data = {k: v.to_dict() for k, v in self._manifest.items()}
        self._manifest_path().write_text(json.dumps(data, indent=2))

    # -- hashing --

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def cache_key(self, filepath: str, content: str) -> str:
        return hashlib.sha256(f"{filepath}:{self.content_hash(content)}:{self.model}".encode()).hexdigest()

    # -- cache entry path --

    def _entry_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.kvcache"

    # -- public API --

    def has(self, filepath: str, content: str) -> bool:
        key = self.cache_key(filepath, content)
        entry = self._manifest.get(key)
        if entry is None:
            return False
        if time.time() - entry.created_at > self.ttl_seconds: # expired
            self._evict(key)
            return False
        return True

    def get(self, filepath: str, content: str) -> Optional[CacheEntry]:
        key = self.cache_key(filepath, content)
        entry = self._manifest.get(key)
        if entry and time.time() - entry.created_at <= self.ttl_seconds:
            self._stats.hit_count += 1
            return entry
        self._stats.miss_count += 1
        return None

    async def precompute(self, filepath: str, content: str) -> CacheEntry:
        """Pre-compute KV cache for a file via the configured backend."""
        key = self.cache_key(filepath, content)
        if key in self._manifest:
            return self._manifest[key]
        self._enforce_size_limit()
        start = time.monotonic()
        if self.backend == "lmcache":
            entry = await self._precompute_lmcache(key, filepath, content)
        elif self.backend == "vllm":
            entry = await self._precompute_vllm(key, filepath, content)
        else:
            raise ValueError(f"unknown kv_cache backend: {self.backend}")
        elapsed = (time.monotonic() - start) * 1000
        self._stats.precompute_duration_ms += elapsed
        self._manifest[key] = entry
        self._stats.total_entries = len(self._manifest)
        self._stats.total_size_bytes += entry.size_bytes
        self._save_manifest()
        logger.info("precomputed kv cache for %s (%.0fms, %d bytes)", filepath, elapsed, entry.size_bytes)
        return entry

    async def precompute_batch(self, files: List[Tuple[str, str]], *, concurrency: int = 4) -> List[CacheEntry]:
        """Pre-compute KV caches for multiple files with bounded concurrency."""
        sem = asyncio.Semaphore(concurrency)
        async def _bounded(fp: str, content: str) -> CacheEntry:
            async with sem:
                return await self.precompute(fp, content)
        return await asyncio.gather(*[_bounded(fp, c) for fp, c in files])

    def invalidate(self, filepath: str, content: str) -> bool:
        key = self.cache_key(filepath, content)
        return self._evict(key)

    def invalidate_file(self, filepath: str) -> int:
        """Invalidate all cache entries for a given filepath (any content hash)."""
        to_remove = [k for k, e in self._manifest.items() if e.filepath == filepath]
        for k in to_remove:
            self._evict(k)
        return len(to_remove)

    def clear(self) -> None:
        """Wipe entire cache."""
        for key in list(self._manifest):
            self._evict(key)
        self._save_manifest()

    def stats(self) -> CacheStats:
        return self._stats

    def disk_usage_mb(self) -> float:
        return self._stats.total_size_bytes / (1024 * 1024)

    # -- TTFT measurement --

    async def measure_ttft(self, prompt: str) -> TTFTMeasurement:
        """Measure time-to-first-token with and without cache warming.

        Sends a short completion request to the vLLM endpoint twice:
        once cold (unique prefix to bust cache), once with the same prompt
        (cache-warm). Returns the ratio.
        """
        if not _AIOHTTP:
            raise RuntimeError("aiohttp required for TTFT measurement")
        cold_prompt = f"[cold-{time.monotonic_ns()}] {prompt}"
        cold_ms = await self._ttft_single(cold_prompt)
        warm_ms = await self._ttft_single(prompt)
        speedup = cold_ms / warm_ms if warm_ms > 0 else 0
        self._stats.last_ttft_cold_ms = cold_ms
        self._stats.last_ttft_cached_ms = warm_ms
        return TTFTMeasurement(cached_ms=warm_ms, cold_ms=cold_ms, speedup=speedup)

    async def _ttft_single(self, prompt: str) -> float:
        """Time-to-first-token for one request against vLLM."""
        url = f"{self.vllm_api_base}/v1/completions"
        payload = {"model": self.model, "prompt": prompt, "max_tokens": 1, "stream": True}
        t0 = time.monotonic()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                async for line in resp.content:
                    if line.strip(): # first non-empty line = first token
                        return (time.monotonic() - t0) * 1000
        return (time.monotonic() - t0) * 1000

    # -- eviction --

    def _evict(self, key: str) -> bool:
        entry = self._manifest.pop(key, None)
        if entry is None:
            return False
        ep = self._entry_path(key)
        if ep.exists():
            ep.unlink()
        self._stats.total_entries = len(self._manifest)
        self._stats.total_size_bytes -= entry.size_bytes
        self._save_manifest()
        return True

    def _enforce_size_limit(self) -> None:
        """Evict oldest entries until under max_size_bytes."""
        if self._stats.total_size_bytes <= self.max_size_bytes:
            return
        by_age = sorted(self._manifest.items(), key=lambda kv: kv[1].created_at)
        for key, _ in by_age:
            self._evict(key)
            if self._stats.total_size_bytes <= self.max_size_bytes:
                break

    # -- backend implementations --

    async def _precompute_lmcache(self, key: str, filepath: str, content: str) -> CacheEntry:
        """Pre-compute via vLLM + LMCache.

        LMCache intercepts vLLM's KV computation transparently.
        We trigger a prefill-only request (max_tokens=1) which causes
        LMCache to cache the KV for this prefix. The actual KV data
        lives in LMCache's configured store (disk/redis) — we only
        track metadata here.
        """
        token_count = await self._prefill_vllm(content)
        entry_path = self._entry_path(key)
        metadata = {"filepath": filepath, "model": self.model, "tokens": token_count,
                    "content_hash": self.content_hash(content), "backend": "lmcache"}
        entry_path.write_text(json.dumps(metadata))
        size = entry_path.stat().st_size
        return CacheEntry(filepath=filepath, content_hash=self.content_hash(content),
                          model=self.model, created_at=time.time(),
                          size_bytes=size, token_count=token_count)

    async def _precompute_vllm(self, key: str, filepath: str, content: str) -> CacheEntry:
        """Pre-compute via vLLM's native prefix caching (--enable-prefix-caching).

        Same mechanism as LMCache path: trigger prefill, vLLM caches internally.
        Metadata-only tracking on our side.
        """
        token_count = await self._prefill_vllm(content)
        entry_path = self._entry_path(key)
        metadata = {"filepath": filepath, "model": self.model, "tokens": token_count,
                    "content_hash": self.content_hash(content), "backend": "vllm"}
        entry_path.write_text(json.dumps(metadata))
        size = entry_path.stat().st_size
        return CacheEntry(filepath=filepath, content_hash=self.content_hash(content),
                          model=self.model, created_at=time.time(),
                          size_bytes=size, token_count=token_count)

    async def _prefill_vllm(self, content: str) -> int:
        """Send a prefill-only request to vLLM (max_tokens=1) to warm the KV cache."""
        if not _AIOHTTP:
            raise RuntimeError("aiohttp required for vLLM KV cache precompute")
        url = f"{self.vllm_api_base}/v1/completions"
        payload = {"model": self.model, "prompt": content, "max_tokens": 1}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"vLLM prefill failed ({resp.status}): {text}")
                data = await resp.json()
                usage = data.get("usage", {})
                return usage.get("prompt_tokens", len(content) // 4) # estimate fallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_local_inference(provider_name: str) -> bool:
    """Check whether the active provider supports KV cache manipulation."""
    return provider_name.lower() in ("ollama", "vllm", "sglang")


def build_cache_friendly_prompt(files: List[Tuple[str, str]], query: str, *,
                                store: Optional[KVCacheStore] = None) -> str:
    """Order file segments so cached prefixes are grouped first.

    For Ollama (no KV API), this maximizes internal prefix-cache hits
    by putting stable/cached files before volatile ones.
    """
    cached, uncached = [], []
    for filepath, content in files:
        if store and store.has(filepath, content):
            cached.append((filepath, content))
        else:
            uncached.append((filepath, content))
    parts = []
    for fp, c in cached + uncached:
        parts.append(f"### {fp}\n{c}")
    parts.append(f"\n### Query\n{query}")
    return "\n\n".join(parts)


async def maybe_init_kv_cache(config: Any) -> Optional[KVCacheStore]:
    """Initialize KV cache store if enabled and local inference detected.

    Args:
        config: poor_cli.config.Config instance

    Returns:
        KVCacheStore or None if feature disabled / not applicable
    """
    kv_cfg = getattr(config, "kv_cache", None)
    if kv_cfg is None or not kv_cfg.enabled:
        return None
    if not is_local_inference(config.model.provider):
        logger.info("kv_cache enabled but provider '%s' is not local inference — skipping", config.model.provider)
        return None
    store = KVCacheStore(
        cache_dir=Path(kv_cfg.cache_dir),
        model=config.model.model_name,
        max_size_mb=kv_cfg.max_cache_size_mb,
        ttl_seconds=kv_cfg.ttl_seconds,
        backend=kv_cfg.backend,
        vllm_api_base=kv_cfg.vllm_api_base,
    )
    logger.info("kv cache store initialized (backend=%s, dir=%s)", kv_cfg.backend, kv_cfg.cache_dir)
    return store
