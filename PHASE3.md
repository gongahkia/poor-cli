# PHASE3: Workflow Depth and Singapore Use-Case Expansion (Day 61 to Day 90)

## Intent

Phase 3 focuses on product depth, not superficial tool-count growth.
The goal is to make existing high-value workflows materially harder to replace.

## Objectives

1. Deepen best-performing workflows (`business`, `property`, `transport`, `environment`, `civic`).
2. Add high-demand Singapore use cases where public data supports deterministic outputs.
3. Improve artifact quality for real handoff into internal tools and enterprise processes.

## Scope

- Brief artifact quality and risk-oriented summarization.
- Workflow enrichments for diligence and operations.
- Selective expansion into high-value public-domain endpoints.

## Out of Scope

- General-purpose autonomous planner behavior.
- Subjective recommendations that cannot be defended by source evidence.

## Workstreams

### 1. Business Dossier Upgrade

- Add `riskFlags` with deterministic conditions.
- Add `matchConfidence` and source-level match rationale.
- Add `nextChecks` guidance to direct follow-up tools.
- Add markdown-friendly output block for due-diligence handoff.

### 2. Property Brief Upgrade

- Add clearer confidence markers for geospatial resolution.
- Add deterministic conflict warnings when source values diverge.
- Add threshold-style signals for transport and environment context.
- Improve provenance/freshness readability for non-technical stakeholders.

### 3. Operations Briefs Upgrade (Transport and Environment)

- Add alert-state heuristics for operational escalation tiers.
- Add follow-up action templates keyed by signal class.
- Add durable identifiers for recurring signals to enable diffing across runs.

### 4. Targeted Singapore Expansion

- Prioritize expansions with strong enterprise demand and stable public sourcing.
- Candidate areas:
  - legal/regulatory lookup surfaces where officially available
  - procurement intelligence extensions on GeBIZ data
  - education and healthcare discovery enrichments for planning workflows
- Every addition must ship with source-licensing and contract documentation.

## Deliverables

- Enhanced brief schemas with backward-compatible evolution notes.
- New regression tests for quality and consistency of brief envelopes.
- Expanded `sg_query` recipes and playbooks for new supported prompt shapes.
- Public-source and licensing notes for each newly added surface.

## Exit Criteria

1. Brief artifacts include deterministic risk and confidence signals.
2. Existing consumers can parse new outputs without breaking changes.
3. New workflows are reflected in `sg://recipes` and `sg://playbooks`.
4. Every expansion has explicit provenance, freshness, and limits metadata.
5. Product audit reflects measurable outcome value increase, not only more tools.

## KPIs

- Brief adoption ratio vs raw tool calls: +20 percent increase.
- Manual post-processing effort for common diligence tasks: -30 percent.
- Workflow completion without fallback for supported prompts: >= 90 percent.
- Source attribution completeness in generated artifacts: 100 percent.

## Risks and Mitigations

- Risk: richer summaries drift toward unverifiable synthesis.
  - Mitigation: enforce deterministic rule-based signals tied to evidence.
- Risk: expansion exceeds maintenance capacity.
  - Mitigation: require maintainer capacity check and test budget per addition.
- Risk: public dataset quality variance reduces output trust.
  - Mitigation: add source quality flags and gap-first rendering behavior.

