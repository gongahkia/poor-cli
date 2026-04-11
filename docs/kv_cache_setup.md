# Position-Independent KV Cache — Setup Guide

## Overview

poor-cli can pre-compute KV caches for repository files and reuse them across prompts, reducing time-to-first-token (TTFT) by 2–3× on cache hits. This feature **only works with self-hosted inference** — it cannot be used with closed API providers (Anthropic, OpenAI, Gemini).

## Backend Support Matrix

| Backend | KV Precompute | Position-Independent Reuse | Notes |
|---------|--------------|---------------------------|-------|
| **vLLM + LMCache** | Yes | Yes (via CacheBlend) | Full support — recommended |
| **vLLM standalone** | Yes | Prefix-only | Use `--enable-prefix-caching` |
| **SGLang** | Yes | Yes (RadixAttention) | Similar to vLLM + LMCache |
| **Ollama** | No | No | No KV cache API; only prompt ordering optimization |

## Requirements

### vLLM + LMCache (recommended)

```bash
pip install vllm lmcache
```

Start vLLM with LMCache enabled:

```bash
# LMCache config (lmcache_config.yaml)
chunk_size: 256
local_device: "cpu"
storage_backend:
  type: "local"
  path: "/tmp/lmcache_storage"

# Start vLLM
vllm serve meta-llama/Llama-3.1-8B \
  --enable-prefix-caching \
  --kv-cache-dtype auto \
  --port 8000
```

### vLLM standalone

```bash
pip install vllm

vllm serve meta-llama/Llama-3.1-8B \
  --enable-prefix-caching \
  --port 8000
```

### Ollama (limited)

Ollama manages KV caching internally — no external API. poor-cli applies **cache-friendly prompt ordering** (stable file prefixes grouped first) to maximize Ollama's internal prefix cache hit rate. No extra setup needed.

## Configuration

In `~/.poor-cli/config.yaml` or `.poor-cli/config.yaml`:

```yaml
kv_cache:
  enabled: true            # default: false
  backend: "lmcache"       # "lmcache" or "vllm"
  cache_dir: ".poor-cli/kv_cache/"
  precompute_on_startup: false
  max_cache_size_mb: 5000  # 5 GB cap
  ttl_seconds: 86400       # 24 hours
  vllm_api_base: "http://localhost:8000"
```

Also ensure your model config points to the local provider:

```yaml
model:
  provider: "ollama"       # or configure vLLM as custom provider
  model_name: "llama3.1:8b"
```

## Disk Space Requirements

KV cache metadata stored by poor-cli is minimal (JSON manifests, ~1KB per file). The actual KV cache data lives in the inference backend:

- **LMCache disk backend**: ~10–100 MB per cached file, depending on model size and file length
- **vLLM in-memory**: KV caches live in GPU/CPU memory, no disk overhead
- **Recommended**: 5–10 GB free disk for LMCache with a medium-sized repo (~100 files)

The `max_cache_size_mb` config controls poor-cli's metadata cap. LMCache's storage is managed separately via its own config.

## How It Works

1. **Precompute**: For each repo file, poor-cli sends a prefill-only request (`max_tokens=1`) to vLLM, which computes and caches the KV state for that file's tokens.

2. **Cache key**: `sha256(filepath + content_hash + model_name)` — changes to file content automatically invalidate the cache.

3. **Assembly**: When building a prompt, cached file segments are ordered first (maximizing prefix cache hits), followed by uncached files, then the user query.

4. **TTL**: Cache entries expire after `ttl_seconds` (default 24h). Expired entries are evicted on next access.

5. **Size enforcement**: Oldest entries evicted when total metadata exceeds `max_cache_size_mb`.

## Measuring Impact

Use the built-in TTFT measurement to verify cache effectiveness:

```python
from poor_cli.kv_cache_store import KVCacheStore

store = KVCacheStore(cache_dir=Path(".poor-cli/kv_cache"), model="llama3.1:8b")
measurement = await store.measure_ttft("your prompt here")
print(f"Cold: {measurement.cold_ms:.0f}ms, Cached: {measurement.cached_ms:.0f}ms, Speedup: {measurement.speedup:.1f}x")
```

Expected results:
- **Cache hit**: 2–3× TTFT reduction
- **Cache miss**: No difference (falls back to normal prefill)

## Limitations

- **Ollama**: No KV cache API. Only gets prompt ordering optimization.
- **Position-independent reuse**: Only available with LMCache (CacheBlend) or SGLang (RadixAttention). vLLM standalone only supports prefix caching.
- **Model changes**: Cache invalidated when switching models (different model = different KV representations).
- **Memory pressure**: Large repos with many cached files can consume significant GPU/CPU memory on the inference server.
- **Feature is OFF by default**: Must be explicitly enabled in config.

## References

- [CacheBlend (EuroSys 2025)](https://arxiv.org/abs/2405.16444)
- [LMCache GitHub](https://github.com/LMCache/LMCache)
- [EPIC paper](https://arxiv.org/abs/2410.15332)
- [Prompt Cache paper](https://arxiv.org/abs/2311.04934)
