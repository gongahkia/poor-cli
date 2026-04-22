# Provider Setup

poor-cli supports **11 providers** across cloud and local surfaces. All BYOK — you control your keys, your data, your costs. Pick whichever fits your budget and latency needs.

## TL;DR per provider

| Provider | Env var | Default model | Cost tier | Notes |
|---|---|---|---|---|
| Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` | $$ | Best free tier; fast; vision |
| OpenAI | `OPENAI_API_KEY` | `gpt-5.1` | $$$ | GPT-5 family; strong tools |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | $$$$ | Best prompt caching; strongest reasoning |
| OpenRouter | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4-20250514` | varies | 200+ models through one key |
| Ollama | (none) | `llama3.1` | free | 100% local; needs `ollama serve` |
| HF Local | (none) | `Qwen/Qwen2.5-3B` | free | Transformers in-process; GPU helps |
| vLLM | (opt `VLLM_API_KEY`) | `Qwen/Qwen2.5-3B` | free | OpenAI-compatible local server |
| llama-server | (opt `LLAMA_SERVER_API_KEY`) | `local-model` | free | llama.cpp serve mode |
| SGLang | (opt `SGLANG_API_KEY`) | `Qwen/Qwen2.5-3B` | free | RadixAttention prefix cache |
| HF TGI | (opt `HF_TGI_API_KEY`) | `tgi` | free | HF Text Generation Inference |
| LM Studio | (opt `LMSTUDIO_API_KEY`) | `local-model` | free | GUI local runner |

Cost tiers are rough indicators relative to each other; see `poor-cli cost compare` for exact rates.

## Credential Lookup Order

For every provider:
1. OS keyring (preferred; install `poor-cli[keyring]`).
2. Environment variable.
3. `.poor-cli/api_keys.json` plaintext (last resort; CI/dev only).

Change keys with `poor-cli provider keys set` or env vars. Migration from env/plaintext into the keyring is offered on first setup.

## Cloud Providers

### Gemini

Cheapest cloud option; generous free tier; fast.

```bash
export GEMINI_API_KEY="$(pbpaste)"  # paste from https://aistudio.google.com/apikey
```

Models: `gemini-2.5-flash` (default, balanced), `gemini-2.5-pro` (quality), `gemini-2.5-flash-lite` (cheap).

Features: streaming, function calling, system instructions, vision, JSON mode. Prompt caching via `cachedContent` is available but not yet wired into poor-cli.

### OpenAI

Solid tool use; GPT-5 family.

```bash
export OPENAI_API_KEY="sk-..."
```

Models: `gpt-5.1` (quality), `gpt-5` (balanced), `gpt-5-mini` (cheap).

Features: streaming, function calling, system instructions, JSON mode, vision. Implicit server-side prefix caching — no explicit markers needed. poor-cli blocks stateful Responses API calls by default; see `HARNESS_PORTABILITY.md`.

### Anthropic

Strongest reasoning; best-in-class explicit prompt caching.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Models: `claude-sonnet-4-20250514` (quality), `claude-3-7-sonnet-20250219` (balanced), `claude-3-5-haiku-20241022` (cheap).

Features: streaming, function calling, system instructions, vision, explicit `cache_control` markers on static prefix (system + tool schemas + repo map). Cache hit rate shows up in `/cost`. No Managed Agents (blocked by portability gate).

### OpenRouter

Routes to 200+ models through one API key. Good for experimentation without juggling multiple provider signups.

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

Default route: `anthropic/claude-sonnet-4-20250514`. Configure per-tier models in `provider_catalog.json` → `openrouter.modelTiers`.

## Local Providers (Free)

All local providers are free to run; you pay in GPU/CPU time and cold-start latency. Pick the one that matches your runtime.

### Ollama

Easiest to set up on macOS and Linux.

```bash
brew install ollama
ollama serve &
ollama pull llama3.1
ollama pull qwen2.5-coder
# optionally pull llama3.1:70b for quality tier
```

No API key required. poor-cli auto-discovers installed models from `/api/tags`. Structured output via `format: "json"`. No KV cache API — prefix stability is automatic via model `num_keep`.

### HF Local (Transformers in-process)

For users with beefier GPU / Apple Silicon who want full Python integration and latent-space communication.

```bash
pip install 'poor-cli[hf-local]'
# first model load downloads weights into HF cache
```

Default: `Qwen/Qwen2.5-3B`. Supports in-process latent communication (PRD 059) — only provider that does. Larger models (Qwen2.5-7B, Qwen2.5-14B) map to balanced/quality tiers.

### vLLM

OpenAI-compatible local server with fast batching.

```bash
pip install vllm
vllm serve Qwen/Qwen2.5-3B
# poor-cli talks to http://localhost:8000/v1
```

Text-only in poor-cli; no hidden-state hand-off. Server-side prefix cache is automatic.

### llama-server

llama.cpp's OpenAI-compatible serve mode. Best for CPU-only or lightweight GPU.

```bash
# llama.cpp:
./llama-server -m <gguf-file> --port 8080
```

### SGLang

RadixAttention prefix cache; excellent for repeated prompts.

```bash
pip install sglang
python -m sglang.launch_server --model-path Qwen/Qwen2.5-3B --port 30000
```

### HF TGI

Production-ready HF server with Messages API.

```bash
docker run --gpus all --shm-size 1g -p 3000:80 -v $HOME/.cache/hf:/data ghcr.io/huggingface/text-generation-inference:latest --model-id Qwen/Qwen2.5-3B
```

### LM Studio

GUI local runner; easiest for Windows users.

Download from https://lmstudio.ai, start a local server in the app, then poor-cli points at `http://localhost:1234/v1`.

## Switching Providers

Three ways:

1. **Command:** `poor-cli provider switch <provider> [model]`, or `poor-cli provider list` from the shell.
2. **Config:** set `model.provider = "anthropic"` in `.poor-cli/config.yaml`.
3. **Per-request:** some economy modes re-route automatically (see "Model routing" below).

Swapping providers mid-session preserves local history — poor-cli replays accumulated context to the new provider. No state left stranded on the prior server. This is enforced by `tests/test_harness_portability.py`.

## Model Routing (Cost Cascade)

poor-cli has per-provider tier tables (cheap / balanced / quality) declared in `provider_catalog.json`. When economy mode is `frugal`, routing prefers the cheapest tier able to handle the task; on low-confidence responses it cascades up one tier. Flat providers (single-tier locals) stay single-tier.

Override tiers per-user by editing the `modelTiers` block in the catalog or via `~/.poor-cli/config.yaml`:

```yaml
providers:
  anthropic:
    modelTiers:
      cheap: claude-3-5-haiku-20241022
      balanced: claude-3-7-sonnet-20250219
      quality: claude-sonnet-4-20250514
```

See `poor_cli/model_router.py` for the full logic.

## Capabilities Matrix

Each provider declares capabilities via `ProviderCapabilities`. The picker UI and the cost dashboard read from this enum — it is the single source of truth.

| Capability | Gemini | OpenAI | Anthropic | OpenRouter | Ollama | HF Local | vLLM | llama-server | SGLang | HF TGI | LM Studio |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Streaming | ✅ | ✅ | ✅ | ✅ | ✅ | ⚪ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Function calling | ✅ | ✅ | ✅ | ✅ | opt | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| System instructions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Vision | ✅ | ✅ | ✅ | varies | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| JSON mode | ✅ | ✅ | ⚪ | varies | ✅ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| Structured output | ✅ | ✅ | ⚪ | via OpenAI | ✅ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| Explicit cache markers | ⚪ | ⚪ | ✅ | varies | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| Thinking / reasoning | ✅ | ✅ | ✅ | varies | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| Latent communication | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ✅ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |

Legend: ✅ supported, ⚪ not supported in poor-cli today, `opt` requires a function-calling-capable local model, `varies` depends on the underlying routed model.

## Troubleshooting

- **Missing provider in `provider switch`** — check `~/.poor-cli/api_keys.json` and env vars; run `poor-cli provider keys status` for the lookup chain.
- **Ollama not detected** — confirm `ollama serve` is running (`curl http://localhost:11434/api/tags`). poor-cli polls on each switch.
- **Anthropic cache hit rate stays 0%** — the static prefix must be stable across turns. Look for dynamic content (timestamps, random ordering) polluting the system prompt.
- **Keyring prompt on every request** — macOS gatekeeper can prevent background keyring access. `poor-cli provider keys migrate` re-prompts with a sticky approval.

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) — provider abstraction + adapter contract.
- [HARNESS_PORTABILITY.md](./HARNESS_PORTABILITY.md) — why poor-cli blocks stateful APIs by default.
- [MCP.md](./MCP.md) — adding MCP servers alongside a provider.
