# PRD 062 Outcome: Audience + North-Star Metric

**Date:** 2026-04-14

## Decision

**Audience:** (A) Cost-conscious hobbyists.

**North-star:** `median_usd_per_completion` - median estimated USD spend per completed AI coding request.

This is the single product lens for marketing, docs, and roadmap priority.

## Rationale

Repository evidence favors hobbyist cost control:

- `poor-cli/economy.py` has economy presets, prompt distillation, context dedup, response caching, routing savings, downshift savings, and persisted savings history.
- `poor-cli/config.py` has cost guardrail templates and cheaper-model preference.
- `poor-cli/server/handlers/cost.py` exposes session cost, savings, cost history, budget templates, estimates, model comparison, and cost export RPCs.
- `nvim-poor-cli/lua/poor-cli/cost.lua` and `nvim-poor-cli/lua/poor-cli/panels/savings_dashboard.lua` expose cost and savings UX in Neovim.
- `README.md` and `pyproject.toml` already lead with BYOK and provider plurality, including Ollama.

No access: `LEARNING.md` was referenced by the phase PRD but is absent in this checkout.

## What Was Not Chosen

- (B) Research-minded engineers: latent communication has a 402-line research prototype plus an 11-line compatibility shim, but it is not wired into the main agent loop and requires HF/vLLM hidden-state access.
- (C) Small engineering teams: multiplayer has large server, state, invite, and Neovim surfaces; that is a different product center than individual cost control.
- (D) Enterprise: sandbox, permission, trust, and audit features exist, but they should stay support features.
- SWE-bench Lite pass@1: trust benchmark.
- Turn latency p95: performance guardrail.
- Contributors / month: project health.
- Active sessions / week: adoption indicator.

## Feature Audit

Matches:

- BYOK provider setup.
- Provider switching across Gemini, OpenAI, Anthropic, OpenRouter, and Ollama.
- Economy mode and model downshift.
- Cost guardrails and budget templates.
- Session cost, savings, and history surfaces.
- Local-provider/Ollama support.
- Inline completion, chat, plan review, checkpoints, and context panels as individual workflows.

Mismatches:

- Multiplayer/WebRTC/RBAC/signed invites: small-team product center, heavy code and docs footprint, and formerly top-level README positioning.
- Enterprise-first trust/audit/sandbox positioning: useful support surface, but not the lead.
- Research-first latent communication positioning: relevant only when it lowers local-provider cost; otherwise roadmap pull toward researchers.
- SWE-bench-first positioning: useful for credibility, but not the product target.

## Downstream

- PRD 059: ship latent communication only as local-provider cost reduction; do not promote it as the main product.
- PRD 063: initially pointed to cut/freeze from this audience decision; owner later overrode that on 2026-04-14 and chose (A) Commit for multiplayer.
- Marketing/docs: lead with cost per completion for BYOK/local hobbyists and include multiplayer as a first-class differentiator.
- Roadmap: prioritize instrumentation, budgets, savings dashboards, model routing, local-provider cost reductions, and the committed multiplayer path.

## Follow-up Issues

- https://github.com/gongahkia/poor-cli/issues/16 - multiplayer commit/demo follow-up
- https://github.com/gongahkia/poor-cli/issues/17 - latent cost-reduction scope
- https://github.com/gongahkia/poor-cli/issues/18 - enterprise-first demotion

## Measurement

See `NORTH_STAR.md`.
