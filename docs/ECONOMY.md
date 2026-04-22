# Economy Mode Tuning

poor-cli's north-star is `median_usd_per_completion`. Economy mode is the single biggest lever you have over that number.

## The three presets

| Preset | What it optimizes | Typical workload |
|---|---|---|
| `frugal` | Lowest cost per completion. Aggressive compression, cheap-tier models, terse output, structured-output retries minimized. | Daily Q&A, single-file edits, exploratory chat. |
| `balanced` | Default. Mid-tier models, modest compression, ordinary output. | Most coding tasks. |
| `quality` | Best response quality regardless of cost. Top-tier models, no compression, verbose explanations welcome, advisory routing only. | Architecture decisions, debugging hard issues, code review of large diffs. |

Switch at runtime: `/economy frugal` (or `/broke`), `/economy quality` (or `/my-treat`), `/economy balanced`. Persists in `.poor-cli/preferences.json`.

## What changes per preset

### Provider routing (`model_router.py`)

Frugal picks the cheapest tier from `provider_catalog.json` — usually a flash/haiku/mini class model. Balanced picks the mid tier. Quality picks the top tier and never cascades up.

On a low-confidence response, frugal and balanced cascade one tier up (max one escalation per turn). Quality never cascades — it's already at the top.

### Compression ratios (`prompt_compressor.py`)

| Content type | Frugal | Balanced | Quality |
|---|---:|---:|---:|
| Tool output | 0.20 | 0.30 | 0.60 |
| File content | 0.35 | 0.50 | 0.80 |
| Conversation history | 0.30 | 0.40 | 0.70 |
| System prompt | 0.50 | 0.70 | 0.90 |

Lower ratio = more aggressive compression. Frugal also runs the aggressive filler-strip pass (CB-aggressive-filler) that removes hedges and softeners; quality never runs it.

### Thinking budgets (`thinking_budget.py`)

Frugal scales budgets ×0.6, quality ×1.5. Per-task-type bounds (`_TASK_BOUNDS`) clamp the result so trivial tasks stay tiny and complex tasks always get enough room.

### Output verbosity

Frugal injects a "be terse" directive into the system prompt (Phase 1D). Code blocks, error messages, and git prose are preserved regardless of preset.

## Reading the savings dashboard

`/savings` prints the savings dashboard in the active CLI session. Sources:

| Source | What's measured |
|---|---|
| Block / prefix cache | Anthropic `cache_read_input_tokens` |
| Semantic cache | Cache-hit responses that skipped the provider call |
| Prompt compression | Token delta before/after `prompt_compressor.compress` |
| Safe pre-tokenization | Code files compressed via Phase 12F |
| Diff-of-diff (CB1) | Repeat-file context replaced with collapsed diff |
| Model downshift | Frugal-mode tier downshift vs the user's default model |
| RTK-lite shell filter | Shell output trimmed by `shell_filters/*` |

The numbers are estimates — they assume a counterfactual "what would the full text have cost". Use them to compare presets over time, not as absolute spend predictions.

## Tuning tips

- **First check**: am I on the right preset? `/economy` shows the active one.
- **High cost on simple Q&A**: try `/broke` and `--terse`-style prompts; the model router should drop to flash/haiku.
- **Quality regressions in frugal**: bump `auto_compact_threshold` from 0.7 to 0.8 in `~/.poor-cli/config.yaml` so compression triggers later. Or move to balanced.
- **Repeated file reads dominate cost**: enable `context.diff_of_diff_cache: true` (CB1). Repeat-file context after the first read sends a collapsed diff instead of full content.
- **Tool output bloat**: tighten `output_truncation.max_output_chars` (default 32000). Or switch noisy tools to `format: "json"` mode and add a JSONPath `output_filter` (Phase 12E).

## Cost guardrails

Independent of economy mode, you can set hard limits in `~/.poor-cli/config.yaml`:

```yaml
cost_guardrails:
  daily_usd: 5.00
  monthly_usd: 50.00
  per_request_usd: 0.50
  warn_at_pct: 0.80
```

Triggered guardrails block further requests with a structured error. Use `/cost` to see current consumption and `/cost templates` to apply a preset.

## See also

- [PROVIDERS.md](./PROVIDERS.md) — model tiers per provider drive routing decisions.
- [HARNESS_PORTABILITY.md](./HARNESS_PORTABILITY.md) — why server-side caching alone isn't enough.
- [BENCHMARKS.md](./BENCHMARKS.md) — pending pass@1 will publish per-preset cost.
- `NORTH_STAR.md` — the metric all of this chases.
