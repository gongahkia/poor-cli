# Developer Adoption Audit

Observed on 2026-03-27 from the perspective of a developer deciding whether to integrate this repository into a real product.

## Executive Verdict

There is an actual value prop here.

It is not "Singapore data for everyone." It is narrower and more defensible than that: one deterministic MCP server for Singapore public data with stable `sg_*` contracts, bounded workflow routing, additive brief artifacts, and enough runtime discipline to save a developer from wiring dozens of separate public-data surfaces by hand.

That is real value for the right buyer.

The current problem is not emptiness. The current problem is adoption depth. The repo feels credible as infrastructure, but not yet obvious as a default dependency for developers who need repeatable business, property, macro, transport, or environment workflows in production.

## Implementation Update (2026-03-30)

This pass tightened adoption-critical runtime behavior:

- structured request/workflow logging now spans query planning, query execution steps, brief-source partial failures, REST gateway invocations, and CLI commands
- internal verification removed avoidable network dependence from parity stages
- `npm run diagnostics` now provides a fast local contract check before full verification
- troubleshooting and market-convention guidance now live in dedicated docs for faster onboarding and incident triage

## Evidence That The Repo Is Real

- The codebase now exposes 38 catalog families and 105 registered `sg_*` tools.
- `npm run verify` is the repo-wide gate for lint, build, docs parity, tests, and packaging smoke.
- The repo exposes machine-readable discovery resources through `sg://apis`, `sg://tools`, `sg://workflows`, `sg://recipes`, and `sg://runtime`.
- The server has centralized cache, timeout, retry, rate-limit, and packaging checks instead of leaving those concerns to downstream consumers.
- The repo now includes a credential-gated live smoke path plus package and registry smoke checks for end-to-end MCP validation.

That means this is already beyond a concept repo or README-only pitch.

## Actual Value Prop

For a developer, the strongest current value is:

1. One honest integration point for fragmented Singapore public-data APIs.
2. Stable, explicit tool contracts instead of brittle prompt glue.
3. Bounded, inspectable workflows instead of fake planner magic.
4. Brief artifacts with provenance, freshness, gaps, and limits already surfaced.
5. Runtime concerns already handled: auth, cache, retries, rate limits, smoke checks, packaging checks.

If a team is building an agent, assistant, internal tool, or workflow that needs Singapore-specific public data and wants deterministic traces, this repo saves meaningful integration time.

## Who Gets Value Today

### Agent Builders

Best fit today.

They benefit from the bounded `sg_query` layer, resource catalogs, direct tool fallbacks, and traceable workflow steps. This repo is strongest when plugged into an MCP-aware agent stack that needs Singapore-specific capabilities quickly without pretending to solve arbitrary research.

### Business And Property Workflow Builders

Also a strong fit.

The repo is especially credible where cross-source composition matters:

- business diligence across ACRA, BCA, CEA, BOA, HSA, HLB, and GeBIZ
- property diligence across URA, HDB, OneMap, and optional live context
- geospatial resolution and routing for Singapore-specific addresses and postal codes

### Internal Ops Or Monitoring Use Cases

Moderate fit.

Transport and environment snapshots are useful, but they currently feel more like bounded status reads than fully operational products. They are useful building blocks, not yet sticky workflows.

## Where The Repo Still Feels Thin To A Real Developer

### 1. The Repo Sells Infrastructure Better Than Outcomes

The documentation is strong on honesty, scope, and tool inventory. It is weaker on "what would I ship with this in the next two days?"

Most examples are still MCP payload snippets rather than full product integration patterns. The new `examples/integration/basic-client.ts` closes the most obvious gap, but the repo still needs more opinionated client patterns showing:

- how to connect a client in more than one runtime
- how to read discovery resources once and cache them
- how to route between `sg_query` and direct tools in app code
- how to recover from blocked, unsupported, and failed states in a UI or backend job

That gap matters because real developers adopt runnable patterns, not just tool catalogs.

### 2. Trust Can Drop Fast When A Headline Brief Looks Wrong

During this audit, the macro brief still surfaced credibility problems:

- the CPI entrypoint resolved to a GDP dataset
- the interest-rate and banking records mirrored the exchange-rate shape
- summary metrics such as `SORA metric` and `Banking metric` were not persuasive developer-facing outputs

Even if this is partly an output-shaping issue, it is still a product issue because first-run artifacts are part of the developer trust surface. Developers will judge the repo by the first convincing output they see.

### 3. The Best Features Are Narrower Than The Surface Count Suggests

The repo has 68 tools, but the truly differentiated user stories are concentrated in a smaller set:

- business dossier
- architecture firm diligence
- healthcare supplier diligence
- hotel operator lookup
- property brief
- civic discovery
- route planning
- transport brief
- environment brief
- data.gov discovery fallback

That is fine, but it means user retention depends on making those few workflows excellent. Tool-count growth alone will not create adoption.

### 4. The Install Story Is Truthful But Still Frictional

The README is honest that the default path is local build plus local MCP wiring until the public npm release exists. That honesty is good.

But a real developer still sees:

- no public package proof in the default path
- credential setup for key live workflows
- credential-gated validation still depends on live upstream credentials

This makes the repo feel more evaluable than immediately adoptable.

### 5. The Repo Lacks Product-Level Signals For Production Buyers

A developer considering real use wants to know:

- expected latency by tool family
- cache behavior by workflow
- what freshness means operationally
- how often upstream schemas change
- what partial-failure behavior looks like in practice

The code handles many of these concerns, but the repo does not yet package them as adoption-grade guidance.

## Pain Points, Desires, And Gain Creators

### Persona: Agent Application Developer

Pain points:

- Too many entrypoints before they know the safe default.
- Not enough code-level examples for routing and recovery behavior.
- Hard to tell where `sg_query` is genuinely better than calling a direct tool.

Desires:

- one default entrypoint
- obvious fallback path
- explainable routing
- payloads stable enough for logging, evaluation, and testing

Gain creators already present:

- `sg_query` plus `sg://recipes`
- explicit blocked and unsupported outcomes
- direct `sg_*` contracts when exact parameters are known

### Persona: Diligence Or Ops Workflow Builder

Pain points:

- Briefs are useful, but not yet rich enough to become end-user outputs without extra post-processing.
- Live surfaces still require developers to design their own thresholding, change detection, and follow-up actions.
- The current examples stop at data retrieval rather than opinionated workflow completion.

Desires:

- one artifact they can send to a user or ticketing system
- richer status summaries and flags
- enough normalization that the app layer stays thin

Gain creators already present:

- provenance, freshness, gaps, and limits
- additive briefs instead of raw payload dumps
- business and property cross-source composition

### Persona: Platform Or Infra-Conscious Developer

Pain points:

- No short production guidance for cache, rate-limit, credential, and failure handling.
- No published benchmark-style expectations.
- The repo proves correctness better than reliability characteristics.

Desires:

- predictable runtime behavior
- install confidence
- easy rollback
- clear contract boundaries

Gain creators already present:

- centralized runtime utilities
- packaging smoke
- docs parity checks
- stable tool names

## How To Deepen Existing Features Before Expanding Breadth

### `sg_business_dossier`

This is already one of the strongest features. Make it much harder to replace by deepening the artifact:

- add a first-class `riskFlags` section with deterministic rules such as missing registry matches, entity-status mismatches, or missing workhead coverage
- add `matchConfidence` and explicit exact-match vs fuzzy-match labeling for each source
- add a compact `nextChecks` section that tells the caller which direct tools to run next
- add a markdown output optimized for due-diligence handoff, not just structured storage

Why this helps:

Developers will keep the feature if it becomes a near-ready diligence artifact rather than a payload they still have to interpret.

### `sg_property_brief`

This is the most commercially interesting workflow in the repo and deserves more depth than breadth right now.

Improve it with:

- transaction rollups: median, range, latest month, transaction count
- HDB vs URA context summaries that are easy to compare
- explicit geospatial context such as resolved address confidence and planning-area resolution path
- optional "deal checklist" fields for missing context, stale coverage, and unsupported recommendation boundaries
- tighter transport and environment summaries when those toggles are enabled

Why this helps:

Property workflows can become one of the repo's stickiest reasons to exist, but only if the artifact is useful without significant downstream summarization.

### `sg_macro_brief`

This is currently the weakest additive brief from a product perspective.

Deepen it by:

- replacing generic "first numeric field" summaries with named metrics
- surfacing period-over-period deltas for supported metrics
- pulling one or two actual SingStat tables rather than stopping at dataset discovery
- separating starter discovery mode from "tracked KPI bundle" mode
- adding stronger tests and output checks so the headline macro path never looks incorrect

Why this helps:

Macro is a trust-sensitive workflow. If the output looks vague or wrong, developers will doubt the rest of the repo.

### `sg_transport_brief`

The current shape is a useful snapshot. To become retention-worthy, it should help developers answer "what changed and what matters?"

Improve it with:

- explicit service-status summaries per transport mode
- better stop-level drilldown summaries when a bus stop is supplied
- delta-aware fields such as newly active incidents or cleared alerts when historical cache exists
- optional area or corridor scoping built on current inputs rather than new broad families

Why this helps:

Ops teams care less about raw status and more about whether action is needed.

### `sg_environment_brief`

The opportunity is similar to transport: make it operational, not merely descriptive.

Improve it with:

- threshold-based flags for rain, air quality, and forecast conditions
- automatic region or station fallback logic when only one environmental hint is supplied
- concise "outdoor conditions" or "monitoring status" summaries that remain bounded and source-backed
- short direct-tool continuation recommendations for follow-up reads

Why this helps:

The feature becomes easier to plug into alerts, dashboards, and field-ops workflows.

### `sg_query`

`sg_query` already has the right philosophy. The next depth step is not broader intelligence. It is better developer ergonomics.

Improve it with:

- stronger workflow explanation in successful results: why this route was chosen and when to drop to direct tools
- more polished blocked-state guidance with exact missing parameters
- continuation hints after completion, for example "call `sg_datagov_rows` next with this datasetId"
- more live-smoke-backed prompt coverage for the recipes already claimed

Why this helps:

Developers will trust a bounded router more when it behaves like a disciplined coordinator instead of a thin intent matcher.

## Adoption Improvements Outside The Core Tools

These are not feature breadth requests. They are leverage improvements for the existing product.

### Add More Integration Examples Beyond TypeScript

One or two additional client examples showing:

- how to use the same routing pattern from Python or a backend worker
- how to persist `sg://recipes`, `sg://runtime`, and `sg://benchmarks` across process restarts
- how to render business-diligence blockers and continuation hints in a real UI or job log

This would make the repo feel more production-adoptable outside a TypeScript-first audience.

### Keep Live Example Outputs Believable Across New Sector Workflows

Keep the architecture, healthcare-supplier, and hotel-operator live examples believable, because these are now first-contact diligence workflows. Developers need to see what "good" looks like before they commit to an integration.

### Strengthen First-Run Trust

If a first-run workflow cannot tell a believable story, fix the artifact or simplify the workflow. First impressions matter more than tool count.

### Keep Benchmarks And Production Notes Current

The repo now has `sg://benchmarks` and a production-notes doc. The next step is keeping those aligned with the new sector-specific diligence workflows so latency, cache-tier, and credibility expectations stay current.

## Priority Order

1. Deepen the six additive brief artifacts, especially property and macro.
2. Improve first-run credibility and live example coverage for the new sector-specific diligence workflows.
3. Add more integration paths for non-TypeScript application developers.
4. Make `sg_query` continuation guidance more useful.
5. Only then expand breadth beyond the current business and compliance wedge.

## Bottom Line

This repository already has real developer value.

Its strongest promise is not breadth. Its strongest promise is disciplined Singapore public-data access with deterministic contracts and bounded artifacts.

To attract actual users, the project should resist chasing more agencies too early. The better move is to turn the current best workflows into outputs developers would feel comfortable shipping with minimal additional interpretation.
