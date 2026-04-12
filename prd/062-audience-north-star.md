# PRD 062: Pick target audience + single north-star metric — DECISION

- **Wave:** 4
- **Status:** decision
- **Owner (human):** @gongahkia
- **Estimated effort:** small (decision doc)
- **Blocks:** 059 (informs latent-communication decision)
- **Blocked by:** —

## 1. Problem

The project is simultaneously pitched at cost-conscious hobbyists, research-minded engineers, and enterprise teams. Three different products. No single north-star metric. LEARNING.md §6.

## 2. Current state

Marketing, docs, and roadmap implicitly span all three audiences. Different feature requests pull in different directions (multiplayer is enterprise-ish, latent communication is research-ish, economy / BYOK is hobbyist-ish).

## 3. Decisions required

> **DECISION 1:** pick a primary audience.
> - (A) Cost-conscious hobbyists (BYOK individuals, Ollama users, budget-sensitive freelancers).
> - (B) Research-minded engineers (evaluating agents, prompt engineering, local-model enthusiasts).
> - (C) Small engineering teams (multiplayer pair programming, shared sessions, shared history).
> - (D) Enterprise (sandboxing, audit, policy enforcement, procurement).

> **DECISION 2:** pick a north-star metric.
> - (i) SWE-bench Lite pass@1 (quality).
> - (ii) Median $/completion (cost).
> - (iii) Turn latency p95 (speed).
> - (iv) Contributors / month (community).
> - (v) Active sessions / week (adoption).

> **DECISION 3:** what gets **cut** if it doesn't serve the chosen audience?
> Examples: multiplayer is (C)-only. Latent communication is (B)/(A). Deep sandbox is (D).

**Recommended:** (A) + (ii). (A) matches the name and existing code bias; (ii) is tractable and differentiates.

## 4. Follow-up

Once decided, update:
- README top-line hook.
- LONGTERM-TODO priorities (re-order around audience).
- LEARNING.md §6 answer.
- Metric dashboard in `docs/METRICS.md` (new).

## 5. Files to modify

Docs only.

## 6. Implementation plan

1. Owner decides.
2. Update README hook (1 sentence).
3. Create `docs/METRICS.md` with the metric + how it's measured + current baseline (from PRD 060).
4. Tag PRDs with audience relevance.

## 7. Testing & acceptance criteria

- README reflects single audience.
- Metric tracked in a way that's reproducible.

**Done criterion**
- [ ] Decision recorded in this PRD's `## Outcome` section.
- [ ] Docs updated.

## 8. Rollback / risk

None. A decision can be revised.

## 9. Out-of-scope & boundary

- 🚫 Do not silently cut features. Any cut driven by this decision needs its own PRD.

## 10. Related PRDs & references

- PRD 059, 060, 063.
- LEARNING.md §6.
