# Market Conventions Audit

Observed on 2026-03-30.

This note benchmarks `sg-apis-mcp` against current MCP ecosystem conventions so expansion decisions stay grounded in real developer adoption patterns, not internal assumptions.

## Primary Sources Used

- MCP tools concept/spec documentation:
  - https://modelcontextprotocol.io/docs/concepts/tools
  - https://modelcontextprotocol.io/specification/draft/server/tools
- Official reference-server positioning and install conventions:
  - https://github.com/modelcontextprotocol/servers
- GitHub MCP operational conventions (toolsets and least-privilege surface control):
  - https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/configure-toolsets
- Smithery ecosystem/distribution expectations (discoverability, analytics, hosted connection lifecycle):
  - https://smithery.ai/docs
  - https://smithery.ai/docs/build
  - https://smithery.ai/docs/use/connect
- Production-grade MCP server observability/error posture examples:
  - https://docs.firecrawl.dev/mcp-server

## What The Market Expects

1. Installation must be low-friction and explicit.
The reference MCP server repository emphasizes runnable package entrypoints (`npx`, `uvx`) and concrete client config snippets.

2. Error semantics must be explicit and machine-actionable.
MCP tools docs distinguish protocol errors from tool execution errors (`isError: true`) and call out validation, rate limiting, and logging as baseline behavior.

3. Surface area control improves quality.
GitHub MCP guidance recommends toolset-level control because fewer enabled capabilities improves tool selection accuracy, reduces errors, and tightens security.

4. Distribution alone is not enough; observability matters.
Smithery positions analytics, metadata extraction, and managed auth/credentials as adoption levers, not optional extras.

5. Runtime transparency is a first-class value signal.
Production-facing MCP servers such as Firecrawl explicitly market logging coverage, retry behavior, and error handling as core product features.

## Current Repo Position (Before This Expansion)

`sg-apis-mcp` was already strong on deterministic contracts and bounded workflows, but still had adoption risks:

- runtime error pathways could complete without enough structured logs for fast triage
- verify flow had an avoidable network dependency in restricted environments
- diagnostics workflow existed across multiple tools/docs but not as one fast local sanity command
- market convention alignment was implicit in docs, not explicitly benchmarked

## Expansion Implemented In This Pass

- Structured, safer logging in shared logger (redaction + resilient serialization + context inheritance).
- Step-level `sg_query` execution logging and richer failure telemetry for blocked/failed triage.
- Brief-source failure logging so partial artifacts no longer fail silently from an operator perspective.
- Universal tool error logging in middleware for handled failures.
- REST gateway request-scoped logging and CLI argument-validation hardening.
- Verify script hardening to remove unnecessary `npm exec` network resolution.
- New `npm run diagnostics` local contract sanity check (`scripts/dev-diagnostics.mjs`).

## Breadth + Depth Roadmap Recommended Next

1. Depth: expose request or trace IDs in selected tool responses.
Keep external schemas stable but include optional debug metadata for operators running production agents.

2. Depth: publish a small, versioned operations schema.
Export machine-readable logging/error taxonomy (codes, severities, retryability) to simplify downstream alerting.

3. Breadth: add opinionated integration templates beyond TypeScript/Python baseline.
Target one backend worker pattern and one UI-facing pattern for blocked/unsupported/failed handling.

4. Breadth: publish recurring benchmark snapshots.
Keep `sg://benchmarks` tied to CI-generated evidence so credibility and freshness claims remain auditable.

5. Depth: tighten toolset-level segmentation.
Add profile-based subsets (for example: `diligence`, `property`, `ops`) so agent builders can intentionally minimize enabled capabilities.
