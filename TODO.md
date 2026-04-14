# TODO

Genuinely open items that still need owner or maintainer attention. `LONGTERM-TODO.md` holds the full historical roadmap with shipped items marked DONE; this file is the short punch list of what remains.

Last audit: **2026-04-14**

## Blocked on owner intervention

These can't be shipped by an agent — they need real hardware, human recording, or API budget approval.

### 1. C1 — pip install end-to-end validation
Clean-environment QA: `pip install poor-cli && poor-cli server --stdio` on fresh Python 3.11, 3.12, 3.13, 3.14 across macOS, Linux, Windows. CI smoke tests exist but full-stack install has never been verified on a clean machine.
Action: owner spins up a clean VM / container per OS, runs the install + ran first chat round-trip.

### 2. C2 / M1 / SBP4 — Multiplayer 2-minute demo video
Gating deliverable for PRD 063 (multiplayer Commit). Must show: host opens `:PoorCLIChat`, presses `S`, invite copies, joiner runs `:PoorCLICollab join <invite>`, room panel shows both members + roles, host passes driver, joiner sends a suggestion, both sides see the room event stream.
Action: record a 2-minute asciinema or screencast; embed in README above the fold.

### 3. H3 / SBP5 — SWE-bench Lite citable number
Harness, runner, Makefile target, per-task results format are all shipped. Only what's missing is the actual $4–12 API-cost run + publish.
Action: `make bench-swe ARGS="--model <primary>"` then update `docs/BENCHMARKS.md` with pass@1 + cost + date. Owner decides primary model (probably Anthropic Sonnet 4 for headline, Gemini 2.5 Flash for cost-conscious comparison).

## Needs external upstream work

### 4. M5 — vLLM server-side latent extension
Client protocol, compatibility checks, and vLLM backend stub are shipped (`poor_cli/research/latent_bridge.py`, `docs/M5_LATENT_BRIDGE.md`). Blocker is the server-side `/latent/encode` + `/latent/generate` endpoints in vLLM itself. Spec is in the doc; estimated 1-2 weeks of upstream work.
Action: land the patch upstream (or on a fork), then un-stub `VLLMLatentBackend.encode` and promote `ProviderCapability.LATENT_COMMUNICATION` for the vllm adapter.

## Pure code/doc work (ship-ready)

All five tracks from the previous TODO sweep landed 2026-04-14. See `LONGTERM-TODO.md` for per-item details. Summary:

- **Track 1 — MH/CB last-mile wiring** ✅ — CB3 tool-success recording, CB1 diff-of-diff in orchestrator, MH5 instruction-stack injection, MH4 review command (Neovim + CLI), MH3 expiring-memories surface (Neovim + CLI).
- **Track 2 — H4 remaining docs** ✅ — `ECONOMY.md`, `SANDBOX.md`, `AUTOMATIONS.md`, `COMMANDS.md` (generated from `command_manifest.json`).
- **Track 3 — M2 cost dashboard verification** ✅ — `:PoorCLICostDashboard` confirmed matches PRD 016 spec (sparkline, top-10 tools, cache stats, projection, export).
- **Track 4 — Latent follow-ups** ✅ — `LatentProvider` abstraction (`research/latent_provider.py`), step auto-tuning (`research/latent_autotune.py`), hierarchical pipelines (`research/latent_pipeline.py`).

## Explicit non-goals

- **LLMLingua-2** (CB6): evaluated and rejected. 110 MB BERT download for <5% quality delta vs heuristic doesn't fit the cost-conscious hobbyist audience. Archaeological note only.
- **Thompson-sampling bandit for budget**: evaluated and deferred in CB4. Moving-average adaptation is cheap, bounded, and explainable — the right choice for the audience.
- **Rename project to something other than `poor-cli`** (L5 / PRD 061): owner rejected on 2026-04-14. Joke is on-brand for the audience. Don't re-open.

## Non-actionable tracking docs

These docs describe still-open work but the work itself is captured above, not in the doc.

- `docs/BENCHMARKS.md` — "pass@1 pending" line; becomes live reference after item 3 ships.
- `docs/archive/phase_21_testing_benchmarks.md` — Agent 21A acceptance criteria; same dependency as item 3.
- `docs/archive/phase_20_strategic_decisions.md` + `docs/phase_20/063_outcome.md` — demo-video gating deliverable; same dependency as item 2.

## Completed items moved from LONGTERM-TODO

See `LONGTERM-TODO.md` "Done (recent)" + tagged `— DONE 2026-04-14` sections for the full record. Summary: all MH1–9, CB1–5, SBP1–3, M3, M4, L1, L2, L3, L4, L6, H2, H5, C3, C4, and the Phase 20 strategic decisions shipped in this sweep.
