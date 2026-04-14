# Latent-Space Inter-Agent Communication

**Status:** Shipping for `hf_local` only (PRD 059, 2026-04-14)
**Feasibility:** Local HuggingFace Transformers models only
**Primary reference:** [LatentMAS](https://arxiv.org/abs/2511.20639) (training-free)

---

## Executive Summary

Latent communication replaces text round-trips between agents with direct hidden-state passing through the model's KV cache. Instead of Agent A generating text that Agent B re-tokenizes and reads, Agent A's last-layer hidden states are injected directly into Agent B's context.

**Result:** 70–84% output token reduction, 4× speedup, up to 14.6% accuracy gains (LatentMAS benchmarks). Only the final agent in a pipeline decodes text — all intermediate agents "reason" entirely in latent space.

**Verdict:** Use only with `hf_local` and `research.latent_communication.enabled = true`. Ollama has no hidden-state or KV cache API, and closed API providers do not expose model internals.

---

## 1. Literature Review

### 1.1 LatentMAS (Princeton/UIUC/Stanford, 2025)

**Paper:** https://arxiv.org/abs/2511.20639
**Code:** https://github.com/Gen-Verse/LatentMAS

**Mechanism:**
- 4-agent sequential pipeline: Planner → Critic → Refiner → Judger
- First 3 agents run forward passes but **never decode tokens**
- Each agent's "output" = last-layer hidden state at final sequence position: `outputs.hidden_states[-1][:, -1, :]` — shape `[B, D]`
- Hidden state is realigned to input embedding space via analytical matrix, then fed as `inputs_embeds` for latent reasoning steps
- Accumulated KV cache (`past_key_values`) passed to next agent
- Only the Judger decodes text

**Realignment matrix** (closed-form, no training):
```
R = (W_out^T @ W_out + λI)^{-1} @ W_out^T @ W_in
```
Where `W_in` = input embedding weights, `W_out` = lm_head weights. Computed once from model weights.

**Key properties:**
- **Training-free** — no fine-tuning, no gradient computation
- **Model-agnostic** — requires standard HF API: `output_hidden_states`, `past_key_values`, `inputs_embeds`
- Validated on Qwen3-4B and Qwen3-14B
- 9 benchmarks: GSM8K, AIME2024/2025, GPQA, ARC, MBPP+, HumanEval+, MedQA

**Results:**
| Metric | Value |
|--------|-------|
| Output token reduction | 70.8–83.7% |
| Wall-clock speedup | 4–4.3× |
| Accuracy improvement | up to +14.6% vs text MAS |

**Infrastructure:**
- HF-only mode: single GPU, model in bf16 (e.g., 28GB for 14B)
- vLLM hybrid mode: 2 GPUs (one for latent rollout, one for text generation)
- Dependencies: `torch`, `transformers`, `accelerate`

### 1.2 Interlat (Zhejiang/Alibaba, 2025)

**Paper:** https://arxiv.org/abs/2511.09149

**Mechanism:**
- Transmits **full sequence of last-layer hidden states** `H = [h_1, ..., h_L]` between agents
- Communication adapter (multi-head self-attention + LayerNorm) helps receiver interpret latent representations
- Can compress to K latent tokens (K << L) via learned autoregressive latent-space reasoning

**Key differences from LatentMAS:**
| Aspect | LatentMAS | Interlat |
|--------|-----------|----------|
| Training | None | 2-stage SFT required |
| What's passed | Single hidden state + KV cache | Full hidden state sequence |
| Compression | Implicit (via latent steps) | Explicit learned compression |
| Infrastructure | 1 GPU | 8–64× A100-80GB for training |
| Models tested | Qwen3-4B/14B | Qwen2.5-0.5B/7B |

**Compression results:**
- Full-length latent: 9.19s → 8 tokens compressed: 0.39s (~24× speedup)
- With trained compression bridge: 0.20s (~46× speedup)
- Accuracy trade-off: ~5% drop when compressing to 8 tokens

**Assessment:** Interlat achieves better compression but requires significant training infrastructure (64× A100-80GB). **Not practical for poor-cli.** LatentMAS's training-free approach is the viable path.

---

## 2. Feasibility Assessment

### 2.1 What Works

| Requirement | Status | Notes |
|-------------|--------|-------|
| Open-weights model | Required | Qwen2.5, Qwen3, LLaMA, Mistral |
| HF Transformers | Required | `output_hidden_states`, `past_key_values`, `inputs_embeds` |
| GPU (CUDA) | Required | 8GB+ VRAM for 3B model, 16GB+ for 7B, 28GB+ for 14B |
| Training | Not needed | LatentMAS is fully training-free |
| vLLM | Text-only local provider | Does not expose the required hidden-state hand-off |

### 2.2 What Doesn't Work

| Provider | Latent Support | Why |
|----------|---------------|-----|
| Anthropic (Claude) | No | Closed API, no hidden-state access |
| OpenAI (GPT) | No | Closed API |
| Google (Gemini) | No | Closed API |
| OpenRouter | No | Proxy to closed APIs |
| **Ollama** | **No** | No hidden-state or KV cache API exposed. Only supports prompt ordering optimization |
| **vLLM / llama-server / SGLang / HF TGI / LM Studio** | **No** | OpenAI-compatible local text APIs only in poor-cli |

### 2.3 Minimum Viable Setup

```
GPU:     NVIDIA with 8GB+ VRAM (or Apple Silicon with MPS)
Model:   Qwen/Qwen2.5-3B or meta-llama/Llama-3.2-3B
Python:  torch, transformers, accelerate
VRAM:    ~6–8GB for 3B model in bf16
```

For meaningful multi-agent tasks, recommend 7B+ model (16GB+ VRAM).

### 2.4 Integration with poor-cli

The shipped HF-local path contains:

1. **`LatentAgent`** — agent that reasons in latent space (no text output)
2. **`LatentAgentOrchestrator`** — full Planner→Critic→Refiner→Judger pipeline
3. **`ArchitectLatentBridge`** — drop-in for poor-cli's architect→editor flow
4. **`is_latent_compatible()`** — runtime environment check
5. **`HFLocalProvider`** — local HF provider that declares `ProviderCapability.LATENT_COMMUNICATION`
6. **`LatentChannel`** — provider-capability gate for latent sub-agent execution

`parallel_agents.py` accepts `communication_mode: "latent" | "text"` but isolated worktree agents use text fallback. In-process `delegate_task(..., communication_mode="latent", tools="none")` can use the latent channel when the active provider is `hf_local`.

---

## 3. Usage

Install local HF dependencies:

```bash
pip install 'poor-cli[hf-local]'
```

Configure:

```yaml
model:
  provider: hf_local
  model_name: Qwen/Qwen2.5-3B
research:
  latent_communication:
    enabled: true
```

Optional runtime overrides:

```bash
export POOR_CLI_HF_DEVICE=mps
export POOR_CLI_HF_DTYPE=float32
```

---

## 4. Benchmark Plan

### 4.1 Metrics

| Metric | How measured |
|--------|-------------|
| Output tokens | Count of decoded tokens across all agents |
| Wall-clock time | `time.monotonic()` end-to-end |
| Task success | Manual eval or automated check (math/code tasks) |
| VRAM usage | `torch.cuda.max_memory_allocated()` |

### 4.2 Test Tasks

Run `tests/bench_latent_communication.py` with 20 tasks across categories:
- Math reasoning (GSM8K-style)
- Code generation (simple functions)
- Planning tasks (multi-step instructions)
- Q&A (factual questions)

### 4.3 Expected Results (from LatentMAS paper)

| Mode | Output tokens (4-agent pipeline) | Speedup |
|------|----------------------------------|---------|
| Text | ~2000 (all 4 agents decode) | 1× |
| Latent | ~400 (only Judger decodes) | 4× |

Token reduction = (2000 - 400) / 2000 = **80%** for a 4-agent pipeline.

---

## 5. Limitations & Risks

### 5.1 Hard Limitations

1. **Closed APIs excluded** — Anthropic, OpenAI, Gemini, OpenRouter cannot expose hidden states. This feature is exclusively for local open-weights inference.

2. **Ollama excluded** — despite being local, Ollama's API does not expose hidden states or KV cache. Would need raw HF Transformers or vLLM.

3. **Same-model requirement** — LatentMAS requires all agents in a pipeline to use the **same model instance** (shared embedding space). Cross-model latent communication requires training (Interlat approach).

4. **No tool use in latent agents** — latent agents cannot invoke tools since they don't decode tokens. Only the final Judger can use tools.

### 5.2 Open Questions

1. **LLaMA/Mistral compatibility** — LatentMAS only validated on Qwen3. The mechanism is architecturally generic (standard HF API), but actual quality on non-Qwen models is unverified. [Inference] Should work since `output_hidden_states`, `past_key_values`, `inputs_embeds` are standard across all HF causal LM architectures.

2. **MPS (Apple Silicon)** — torch MPS backend supports the required ops but may have numerical differences vs CUDA. Untested.

3. **Latent step count** — the `latent_steps` hyperparameter (0–80 in LatentMAS) significantly affects quality. Optimal values are task- and model-dependent. Paper uses grid search.

4. **Scaling to more agents** — LatentMAS tests 4 agents. KV cache grows linearly with agents and latent steps. Memory could become a bottleneck with many agents.

### 5.3 When to Use This

| Scenario | Recommendation |
|----------|---------------|
| Cloud API (Anthropic/OpenAI) | Use text communication (no alternative) |
| Ollama local | Use text communication (API limitation) |
| HF Transformers + GPU | Use `hf_local` |
| vLLM / llama-server / SGLang / HF TGI / LM Studio local | Use text communication |
| Single-agent tasks | Not applicable (no inter-agent communication) |
| Cross-model pipelines | Use text communication (different embedding spaces) |

---

## 6. Future Work

### 6.1 Future Work

1. **Custom local latent bridge** — add hidden-state return / input-embedding hand-off for local servers if a backend exposes it
2. **Latent step auto-tuning** — learn optimal `latent_steps` per task type from historical data
3. **Provider abstraction** — add `LatentProvider` alongside existing `BaseProvider` for models that support hidden-state access
4. **Hierarchical pipelines** — LatentMAS also supports hierarchical (specialist agents → summarizer) architectures

### 6.2 If Shelving

The research value remains: this documents *why* closed-API multi-agent communication is fundamentally more expensive than local open-weights, and quantifies the gap (~4× cost, ~80% more tokens). This informs poor-cli's positioning and pricing guidance for users choosing between providers.

---

## 7. References

1. LatentMAS — Zou et al. (2025). "Latent Collaboration in Multi-Agent Systems." https://arxiv.org/abs/2511.20639
2. Interlat — Du et al. (2025). "Enabling Agents to Communicate Entirely in Latent Space." https://arxiv.org/abs/2511.09149
3. LatentMAS GitHub — https://github.com/Gen-Verse/LatentMAS
4. Coconut — Hao et al. (2024). "Training Large Language Models to Reason in a Continuous Latent Space." https://arxiv.org/abs/2412.06769
