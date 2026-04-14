# M5 Latent Bridge for Local Inference Servers — Research Study

Status: **feasibility study + client protocol shipped**. Server-side patches are **not** shipped by default.

## Thesis

`poor_cli/research/latent_communication.py` does in-process latent hand-off between architect and editor agents when both run as HF Transformers objects in the same Python process. That works for `hf_local` only. For vLLM, SGLang, HF TGI, llama-server, LM Studio, and Ollama, the models live behind a network boundary (OpenAI-compatible REST), and their hidden states never leave the server. M5 investigates what it would take to bridge this gap.

## TL;DR

- **vLLM** is the most feasible v1 target. Ship path: 1-2 weeks of server-side patching + client integration.
- **SGLang** is close behind.
- **HF TGI, llama-server, Ollama, LM Studio** are not practical today.
- `poor_cli/research/latent_bridge.py` ships the client-side protocol (LatentTensorSpec + LatentBackend + compatibility checks + a vLLM stub backend).
- **Nothing runs out of the box.** Enabling M5 requires a patched vLLM server. The spec for that patch is below.

## Architecture

```
architect agent (poor-cli)               editor agent (poor-cli)
       |                                          |
       | POST /latent/encode                      | POST /latent/generate
       |    {prompt}                              |    {hidden_states, kv_cache, max_tokens}
       v                                          v
+-------------------+                     +-------------------+
|   vLLM server     |                     |   vLLM server     |
|   (patched)       |                     |   (patched)       |
|                   |                     |                   |
|  returns          |                     |  returns          |
|  hidden_states +  |  safetensors over   |  text tokens +    |
|  kv_cache         |  ───────HTTP───────>|  usage stats      |
+-------------------+                     +-------------------+
```

Both servers must serve the **same model** with the **same tokenizer** and **same vocab size**. The `LatentBridgeConfig.identity_hash()` check rejects any mismatch before transfer.

## Client Protocol

Shipped in `poor_cli/research/latent_bridge.py`:

| Type | Role |
|---|---|
| `LatentBridgeConfig` | model_id + tokenizer_id + hidden_dim + dtype + backend — must match across endpoints |
| `LatentTensorSpec` | wire format header: name, dtype, shape, byte_order, sha256 checksum |
| `LatentEncodeResult` | hidden_states + optional kv_cache payload |
| `LatentGenerateResult` | completed text + token savings |
| `LatentBackend` | abstract interface (encode / generate_from_latent / health_check) |
| `VLLMLatentBackend` | concrete stub for vLLM |
| `compatibility_check` | returns list of mismatches (empty = OK) |
| `build_backend(name, config)` | factory; raises NotImplementedError with a feasibility note if not vLLM |
| `benchmark_note_for_backend(name)` | per-backend feasibility TL;DR |

## Server-side Patch Spec (vLLM)

The vLLM patch is **out of scope to land in poor-cli**. It's documented here so a motivated contributor can implement it upstream.

### New endpoints

#### `POST /latent/health`

```json
{
  "request": {},
  "response": {
    "available": true,
    "model_id": "Qwen/Qwen2.5-7B",
    "hidden_dim": 4096,
    "num_layers": 32,
    "dtype": "bfloat16",
    "identity_hash": "abc123def456"
  }
}
```

Quick ping. `identity_hash` is the same 16-char prefix used by `LatentBridgeConfig.identity_hash()`. Client rejects the bridge if identity hashes differ.

#### `POST /latent/encode`

```json
{
  "request": {
    "prompt": "Refactor the auth module to use session tokens",
    "return_kv": true,
    "latent_steps": 0
  },
  "response": {
    "headers": [
      { "name": "hidden_states", "dtype": "bfloat16", "shape": [1, 32, 4096], "checksum": "..." },
      { "name": "kv_cache", "dtype": "bfloat16", "shape": [32, 2, 1, 32, 32, 128], "checksum": "..." }
    ],
    "payload": "<multipart safetensors>",
    "prompt_tokens": 32,
    "latency_ms": 12.4
  }
}
```

Returns the last-layer hidden state at the final token position plus the full KV cache. Payload is concatenated safetensors blobs.

#### `POST /latent/generate`

```json
{
  "request": {
    "headers": [
      { "name": "hidden_states", "dtype": "bfloat16", "shape": [1, 32, 4096], "checksum": "..." },
      { "name": "kv_cache", "dtype": "bfloat16", "shape": [32, 2, 1, 32, 32, 128], "checksum": "..." }
    ],
    "payload": "<multipart safetensors>",
    "max_new_tokens": 512,
    "temperature": 0.1
  },
  "response": {
    "text": "Extracted helper in src/auth.py...",
    "output_tokens": 184,
    "input_tokens_equivalent": 32,
    "latency_ms": 420.7
  }
}
```

Server prepends the provided KV cache to a fresh generation pass, using the hidden_state as the initial logit projection start. This bypasses re-tokenizing and re-running the architect's prompt on the editor side.

### Implementation notes for upstream

1. **KV extraction.** vLLM's PagedAttention stores KV in block tables. Need to walk the request's block list, concatenate blocks into a contiguous tensor, and serialize. Reference: `vllm/attention/backends/` — look for block_manager + kv_cache layout.
2. **KV injection.** Mirror: allocate blocks, load tensors, point the request's block table at the loaded blocks, then generate normally with `sampling_params`.
3. **Safetensors over HTTP.** Use `safetensors.torch.save` for serialization, `multipart/form-data` transport.
4. **Version pinning.** Include vLLM version in the health response. Client rejects transfer if server_version differs from its own client_version (major.minor only).
5. **Auth.** Latent endpoints carry real model state; secure with `--latent-api-token` CLI flag + bearer auth.
6. **Rate limiting.** KV tensors are large (10s of MB for 7B model, 32 seq). Expose a concurrency limit for `/latent/*` endpoints separate from `/v1/*`.

## Compatibility Rules

`compatibility_check(architect_config, editor_config)` must return an empty list before any transfer. It checks:

- `model_id` identical
- `tokenizer_id` identical
- `hidden_dim`, `num_layers`, `num_heads`, `head_dim` identical
- `dtype` identical
- `vocab_size` identical
- `identity_hash()` identical (summary catch-all)

Any mismatch aborts the transfer — the caller decides whether to fall back to text.

## Portability Gate

M5 does NOT introduce stateful server-side memory. Each `/latent/encode` → `/latent/generate` pair is a single stateless round-trip; no session IDs persist on the server. This means `MH9 providers_portability.strict = True` does NOT block the latent bridge by default.

If a future extension added server-side session tracking (e.g. "stash this KV cache for reuse later"), `STATEFUL_FEATURES` gains a new code and the portability gate activates.

## Benchmarks

Target benchmarks (not yet run):

- **Tokens saved.** Architect generates 300-token plan → editor normally re-tokenizes plan + runs. Latent path skips re-tokenization. Expected 300 input tokens saved per architect→editor hop.
- **Latency.** Latent hop wall time should be dominated by network transfer (10-50 MB safetensors) rather than forward pass. Target: ≤ 100 ms extra vs pure text hand-off for 7B model on LAN.
- **Quality.** Editor's latent-conditioned completion quality must match or exceed text hand-off quality on a 50-task edit benchmark. Any drop >2% aborts the ship.

Benchmark harness stubbed in `latent_bridge.LatentBenchmarkRun` — fill in once the server patch lands.

## Safety

- **No silent fallback.** If compatibility_check fails, we raise `LatentIncompatibility` — never silently fall back to text. Caller decides.
- **Checksum verification.** Every tensor has a sha256 header; receiver verifies before tensor allocation.
- **Explicit feature flag.** Even with a patched server, latent mode is off unless `ProviderCapability.LATENT_COMMUNICATION` is declared by the adapter AND `config.research.latent_communication.enabled` is True.

## What's Shipped vs What's Blocked

| Component | Status |
|---|---|
| LatentTensorSpec wire format | ✅ shipped |
| LatentBridgeConfig + compatibility_check | ✅ shipped |
| LatentBackend abstract interface | ✅ shipped |
| VLLMLatentBackend client stub + health_check | ✅ shipped |
| Test suite (protocol + compat + factory) | ✅ shipped |
| vLLM server-side /latent/* extension | ⛔ out of scope |
| End-to-end benchmarks | ⛔ blocked on server patch |
| SGLang / TGI adapters | ⛔ lower priority |

## Next Steps

1. Contributor lands the vLLM server extension (upstream or a fork).
2. poor-cli's `VLLMLatentBackend.encode` / `generate_from_latent` are un-stubbed with real HTTP calls.
3. Run the benchmark harness on a 50-task edit benchmark to gate promotion.
4. If quality holds, declare `ProviderCapability.LATENT_COMMUNICATION` for vLLM and wire into `sub_agent.py` + `parallel_agents.py` (mirroring the HF Local integration).

## Related

- `poor_cli/research/latent_communication.py` — in-process HF Transformers implementation (PRD 059).
- `docs/LATENT_COMMUNICATION.md` — original feasibility study.
- `docs/phase_06_memory_architecture.md` Agent 6B — KV cache reuse, adjacent work.
- `docs/phase_08_research_frontier.md` Agent 8A — original latent-space research mandate.
