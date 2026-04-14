# North Star

## Audience

(A) Cost-conscious hobbyists.

## Metric

`median_usd_per_completion`

Median estimated USD spend per completed AI coding request.

## Measurement Plan

Count a completion when an AI coding request reaches a terminal success state and produces a response or accepted inline completion. Exclude canceled, failed, and dry-run requests.

Use existing telemetry first:

- `poor-cli/costSummary`
- `cost.snapshot`
- `cost.history`
- `poor-cli/getSessionCost`
- persisted cost history under `.poor-cli`

Required event fields:

- `completion_id`
- `timestamp`
- `surface` (`chat`, `exec`, `inline`)
- `provider`
- `model`
- `input_tokens`
- `output_tokens`
- `estimated_cost_usd`
- `status`

Weekly reporting:

- compute the median `estimated_cost_usd` over completed requests
- segment by provider/model and surface
- report p25/p75 as guardrails
- keep SWE-bench pass@1 and p95 latency as non-north-star guardrails

Baseline:

- pending PRD 060/Phase 21 benchmark data

## Not Chosen

- SWE-bench Lite pass@1: trust benchmark.
- Turn latency p95: performance guardrail.
- Contributors / month: project health.
- Active sessions / week: adoption indicator.
- Pair-programming sessions / week: multiplayer support metric, not the north-star.
