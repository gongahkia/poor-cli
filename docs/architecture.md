# Architecture Decision Record

## Title

Tool-first MCP server for Singapore government data

## Status

Accepted for the current production-pilot shape.

## Context

This repo is not trying to be a general Singapore analyst copilot. It is a pragmatic MCP server for agent builders who need a small number of reliable, explicit tools over official Singapore data sources.

The product has to balance two competing forces:
- agent users want convenience
- production integrations need predictable contracts, stable inputs, and failure modes that are easy to explain

The current design chooses contract honesty over broad-but-fragile abstraction.

## Decisions

### 1. Direct `sg_*` tools are the canonical product surface

The main contract is the direct tool layer, not natural-language orchestration.

Why:
- direct tools have explicit schemas and predictable outputs
- they are easier to test, document, and defend in interviews
- they let agent builders compose workflows intentionally instead of relying on hidden server logic

Consequence:
- product depth is added by improving the existing direct tools and recipes, not by hiding more orchestration behind `sg_query`

### 2. Scope is intentionally limited to 5 API families

The product currently goes deep on:
- SingStat
- MAS
- OneMap
- URA
- data.gov.sg

Why:
- these five sources cover macro, finance, location, property, and broad dataset discovery
- each additional upstream would multiply auth, rate-limit, schema, caching, and support complexity
- a narrow, honest pilot is stronger than a wide but inconsistent connector

Consequence:
- adjacent Singapore APIs are out of scope until there is a clear product reason to add them

### 3. `sg_query` remains experimental

`sg_query` exists as a convenience router for supported single-step requests, but it is not the product contract.

Why:
- natural-language routing is useful for demos and light usage
- hidden multi-step orchestration caused drift between documentation and real behavior
- experimental status lets the repo keep the helper without pretending it is deterministic enough for production composition

Consequence:
- `sg_query` only routes supported single-step requests
- comparisons, chained workflows, and multi-API synthesis are done explicitly by the caller with direct tools

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
- local keystore support exists for convenience, not as a secret-management solution

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

"I optimized for explicit contracts over ambitious orchestration. The direct tools are stable, testable, and composable. `sg_query` exists for convenience, but I kept it experimental because hidden orchestration was the biggest source of drift and ambiguity."

Key tradeoffs:
- chose a narrow API set over broad coverage
- chose explicit workflows over hidden fan-out
- chose config-driven operational controls over ad hoc constants
- chose truthful docs and schemas over aspirational parameters

Known intentional limits:
- `sg_query` is not a general planner
- data.gov metadata lookup is not row retrieval
- MAS support is intentionally narrower than the full source surface
- local verification still depends on Node 20 being available in the environment

## Implications

This architecture is a good fit when:
- the caller is an agent or engineer who can compose tools explicitly
- correctness and explainability matter more than conversational magic

It is a weaker fit when:
- the product goal is a broad end-user analytics assistant
- hidden multi-step synthesis is the main differentiator

Those goals would require a different product boundary, not just more helper logic in the current repo.
