# PRD 059 Outcome: Latent Communication

**Date:** 2026-04-14

## Decision

**Outcome:** (a) Ship, rescoped to `hf_local`.

Ship latent communication only for local HuggingFace Transformers models via the new `hf_local` provider. Ollama, vLLM, llama-server, SGLang, HF TGI, LM Studio, and closed APIs stay text-only because they do not expose the required hidden-state/KV-cache surfaces in poor-cli.

## Rationale

PRD 062 chose audience (A), cost-conscious hobbyists, with `median_usd_per_completion` as the north-star. PRD 062 says latent communication should ship only as local-provider cost reduction.

The first pass froze the module because the repo did not support a complete Ollama/vLLM ship:
- `poor-cli/research/latent_communication.py` is 402 LOC, plus an 11 LOC legacy shim in `poor-cli/latent_communication.py`.
- Test coverage is a benchmark script and a relocation loader test; no production integration test exists.
- `sub_agent.py` has no `LatentChannel` or hidden-state path.
- `parallel_agents.py` has no `communication_mode` field or latent hand-off.
- At that time, `ProviderCapability.LATENT_COMMUNICATION` existed, but no provider declared it.
- `OllamaProvider.attach_kv_cache()` documents that Ollama has no KV cache API and only supports stable-prefix prompt ordering.
- vLLM did not exist in `ProviderFactory`; it is now a text-only local provider.

Owner follow-up clarified that adding a local HF provider is in scope. That makes (a) feasible without pretending Ollama supports latent internals.

Second owner follow-up requested local text-provider expansion. That adds vLLM, llama-server, SGLang, HF TGI, and LM Studio as OpenAI-compatible local providers without declaring `LATENT_COMMUNICATION`.

No access: `LEARNING.md` is referenced by the PRD, but is absent in this checkout.

## Options

| Option | Cost | Benefit | Decision |
|---|---:|---|---|
| (a) Ship for `hf_local` | 3+ weeks if full vLLM/Ollama, smaller first slice for HF; provider plumbing, `LatentChannel`, sub-agent and parallel-agent integration, benchmark harness, docs | Lowers local multi-agent output tokens where hidden-state access exists | Chosen for HF only |
| (b) Archive | 1 day; delete prototype, benchmark cleanup, docs cleanup | Removes dead code | Not chosen; loses useful research context |
| (c) Freeze | 1 day; import guard, tests, docs | Keeps research value without production ambiguity | Reversed by owner follow-up |

## Implementation

- `poor-cli/providers/hf_local_provider.py` implements local HF text generation plus `run_latent_pipeline()`.
- `ProviderCapability.LATENT_COMMUNICATION` is declared only by `hf_local`.
- `poor-cli/latent_channel.py` gates latent execution behind provider capability and `research.latent_communication.enabled`.
- `sub_agent.py` accepts `communication_mode="latent"` and falls back to text when the channel or tool constraints make latent unavailable.
- `parallel_agents.py` records `communication_mode`; isolated worktree agents use text fallback.
- `vllm`, `llama_server`, `sglang`, `hf_tgi`, and `lmstudio` are local text providers only.
- The Neovim provider picker prompts users who switch to `hf_local` to enable experimental latent communication.
- Docs and tests describe the HF-only ship path.

## Rollback

Disable `research.latent_communication.enabled` or switch away from `hf_local`. Ollama, vLLM, llama-server, SGLang, HF TGI, LM Studio, and cloud providers continue using text communication.
