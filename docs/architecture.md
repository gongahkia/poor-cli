# Architecture Decision Record

## Title

Tool-first MCP server for Singapore government data

## Status

Accepted for the current product shape.

## Context

This repo is not trying to be a general Singapore analyst copilot. It is a pragmatic MCP server for agent builders who need reliable, explicit tools over official Singapore public data.

The product has to balance two competing forces:

- agent users want convenience
- production integrations need predictable contracts, stable inputs, and failure modes that are easy to explain

The current design chooses contract honesty over broad-but-fragile abstraction.

## Decisions

### 1. Direct `sg_*` tools are the stable low-level product surface

The main contract is the direct tool layer.

Why:

- direct tools have explicit schemas and predictable outputs
- they are easier to test, document, and defend
- they let agent builders compose workflows intentionally instead of relying on hidden server logic

Consequence:

- product depth is added by improving the existing direct tools and recipes
- breadth is added with explicit curated tools, not by hiding more orchestration behind `sg_query`

### 2. The product currently goes deep on 11 official data families

The current families are:

- SingStat
- MAS
- OneMap
- URA
- LTA DataMall
- NEA
- HDB
- CEA
- BCA
- ACRA
- data.gov.sg

Why:

- the mix covers macro, finance, location, property, transport, environment, housing, dataset discovery, and business diligence
- HDB, CEA, BCA, and ACRA add practical business-diligence depth without adding new credential surfaces
- each additional upstream still multiplies auth, rate-limit, schema, caching, and support complexity

Consequence:

- the routed surface still stays narrower than the total parameter surface, even though every family now has an honest `sg_query` entrypoint
- ACRA is included through an explicit shard-aware client over the official alphabetically split public entity datasets

### 3. `sg_query` is the bounded preferred interface

`sg_query` is the bounded preferred interface across 11 routed families. It plans or executes transparent deterministic workflows, but it is not a general planner.

Why:

- natural-language entry is useful for open-source users and less technical teams
- transparent step metadata keeps the convenience layer honest
- keeping the workflow set bounded prevents the router from pretending to support arbitrary composition

Consequence:

- `sg_query` supports bounded workflow planning and execution for covered families
- single-step direct execution through `sg_query` is supported where there is an explicit executor
- business-registry workflows can route to ACRA, CEA, and BCA when the query carries an explicit identifier
- comparisons, arbitrary fan-out, and hidden multi-API synthesis still belong in explicit direct-tool composition

### 4. Runtime behavior is centralized around bounded operational controls

The server runtime combines:

- config-driven timeouts
- config-driven TTLs
- rate limiting per upstream
- cache and dedup layers
- structured error handling

Why:

- upstream Singapore APIs vary widely in latency, auth, and rate-limit behavior
- production callers need consistent operational behavior even when upstreams differ

Consequence:

- config accessors, not scattered constants, drive runtime behavior
- health checks report reachability separately from credential presence
- the server favors explicit failure over silent fallback when a request is unsupported

### 5. Auth and config precedence is explicit

Credential/config precedence is:

1. environment variables
2. local keystore or config file
3. code defaults

Why:

- environment variables are the safest operational path for CI and production
- local storage is still useful for development and demos
- precedence must be simple enough to explain without ambiguity

Consequence:

- OneMap requires both email and password
- URA requires an API key
- LTA DataMall requires an API key
- HDB, CEA, BCA, and ACRA reuse public data.gov.sg access and do not introduce separate credentials

## Runtime Model

At a high level:

- MCP stdio requests enter the server
- tool handlers validate inputs at the boundary
- direct handlers call the upstream-specific clients
- clients apply cache, dedup, timeout, and rate-limit behavior
- responses are formatted back into MCP `text` content

The warm-cache path is intentionally best-effort and non-blocking. MCP startup should not wait on prefetch work.

## Interview Defense

If asked why the system is built this way, the shortest defensible answer is:

"I optimized for explicit contracts first, then added a bounded preferred interface on top. The direct tools stay stable and composable. `sg_query` improves usability without pretending to be a general planner."

Key tradeoffs:

- chose explicit direct tools over hidden orchestration
- chose a bounded preferred interface over a free-form planner
- chose curated business-diligence breadth over low-signal surface area
- chose config-driven operational controls over ad hoc constants
- chose truthful docs and schemas over aspirational parameters

Known intentional limits:

- `sg_query` is not a general planner
- data.gov metadata lookup is not row retrieval
- MAS support is intentionally narrower than the full source surface
- ACRA registry support is exact-match and limited to the fields exposed in the official public collection

## Implications

This architecture is a good fit when:

- the caller is an agent or engineer who can compose tools explicitly
- correctness and explainability matter more than conversational magic
- the team wants a truthful blend of low-level contracts and a bounded natural-language entrypoint

It is a weaker fit when:

- the product goal is a broad end-user analytics assistant
- hidden multi-step synthesis is the main differentiator
- the repository is expected to mirror every Singapore public API quickly without curation

Those goals would require a different product boundary, not just more helper logic in the current repo.
