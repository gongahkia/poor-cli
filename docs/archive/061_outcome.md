# PRD 061 Outcome: Project Rename

**Date:** 2026-04-14

## Decision

**Outcome:** (b) Keep `poor-cli`.

Owner rejected the rename on 2026-04-14. The "poor-cli" name is kept deliberately — the joke about being frugal/cost-conscious is on-brand for audience (A) cost-conscious hobbyists (PRD 062).

## Rationale

- Audience + north-star (PRD 062) centers on `median_usd_per_completion`. The name "poor-cli" telegraphs that pitch at first contact. A neutral/enterprise name would dilute the positioning.
- Rename cost estimate: migrate pip package, GitHub repo, Neovim plugin slug, ~10K LoC references + redirect aliases for one release cycle. Real engineering + docs drag for zero marketing lift in the hobbyist segment.
- No evidence the current name blocks adoption in the target segment.

## Options

| Option | Cost | Benefit | Decision |
|---|---:|---|---|
| (a) Rename | Weeks; pip/github/nvim migration, ~10K LoC refs, legacy alias package | Cleaner brand for enterprise | Rejected |
| (b) Keep | Zero | On-brand for hobbyist audience; stops re-opening the question | **Chosen** |

## Follow-ups

- Treat further rename requests as out-of-scope unless audience (PRD 062) is re-litigated.
- Any marketing rewrites should lean into the "poor" framing, not away from it.

## Boundary

No half-rename: "poor-cli" is the only canonical name. Legacy aliases from any prior rename attempts were never shipped, so none need retirement.
