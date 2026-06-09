# Swee Shield × Splunk — Agentic Ops Hackathon Build Brief

**Status:** Architecture locked. Ready to implement.
**Audience:** The coding agent (has repository access; does *not* have our planning conversation — this document is that context).
**Repository:** Swee SG (Node 20 / TypeScript npm workspace).
**Submission deadline:** Jun 15, 2026, 09:00 PDT (submission period opened May 18, 2026).

> A note on honesty before anything else. This brief deliberately constrains what we are allowed to *claim*, because the value of this project to a security audience depends on every claim being true and verifiable. Several capabilities that sound impressive (deterministic replay; "Splunk can't sanitize this") are **not** true of this codebase or are misleading, and the brief calls each one out. Do not let scope creep reintroduce a claim this document has retired.

---

## 1. What this hackathon is

The **Splunk Agentic Ops Hackathon** asks entrants to build an AI-powered solution that improves how teams monitor systems, secure environments, or build on the Splunk platform, using Splunk's current AI capabilities to solve real operational problems. Entrants pick **one of three tracks**:

- **Observability** — help engineering/IT/network teams understand system behaviour, detect anomalies earlier, automate operational responses.
- **Security** — help security teams detect threats faster, investigate incidents more efficiently, automate security workflows using AI and Splunk data. **← this is our track.**
- **Platform & Developer Experience** — improve developer experience, automate workflows, simplify how apps interact with Splunk data/APIs.

**Relevant Splunk surfaces (verified, as of early–mid 2026):**

- **Splunk MCP Server** — GA since Feb 4, 2026. Exposes Splunk functionality *exclusively as callable MCP tools* (capabilities advertise `tools` only — no resources, no prompts). Speaks JSON-RPC 2.0 over **streamable HTTP** (also SSE/stdio). Endpoint shape: `https://<host>:8089/services/mcp`. Auth via **Bearer token** (encrypted Splunk token); honours Splunk native RBAC; v1.1 adds OAuth 2.1. Tools are namespaced: core tools `splunk_*`, AI Assistant tools `saia_*`. Core capabilities: explore data, discover knowledge objects (saved searches, lookups), run SPL searches.
- **Splunk Hosted Models** — zero-infrastructure access to **Foundation-sec** (security-tuned) and **Cisco Deep Time Series** (time-series/forecasting/anomaly).
- **Splunk AI Assistant 1.5** — natural-language SPL editing.

**Submission artifacts required:**
- Working project, newly created **or significantly updated after the start of the submission period** (May 18, 2026) — and we must *explain* what was updated.
- Public, open-source code repo with detectable license (visible in the repo "About" section), clear README, setup/run instructions, dependencies, example configs/datasets.
- **`architecture_diagram.(md|pdf|png)` at the repo root** showing: how the app interacts with Splunk; how AI models/agents are integrated; data flow between services, APIs, and components.
- Demo video **< 3 minutes**, public on YouTube/Vimeo/Youku, showing the project working, the problem, where AI is used, and the value.
- All materials in English.

**Judging:** Stage One is pass/fail (does it fit the theme and reasonably use the required Splunk APIs/SDKs). Stage Two scores four **equally weighted** criteria — Technological Implementation, Design, Potential Impact, Quality of the Idea.

**Prizes we are targeting:** the **Security track** prize ($3,000) and the **"Best Use of Splunk MCP Server"** bonus ($1,000). A project can win one overall/track prize and one bonus prize. Note the bonus rewards solutions that *connect AI agents to Splunk data and orchestrate meaningful actions* — which is exactly the proxy-governance design below.

---

## 2. Why this project, and why this shape

**The product.** Swee SG already contains **Swee Shield**, a layer that wraps tool calls with pre-flight policy decisions, local SQLite audit metadata, catalog scanner findings, trace IDs, and request IDs. Shield is, in effect, a governance/security layer for agent tool calls. The Security track and the "Best Use of MCP Server" bonus both reward exactly this kind of layer — and Splunk itself is publicly evangelising the problem (their security blog "When AI Tools Turn Against You" argues agentic MCP usage *needs* enforced auth, mandatory logging/monitoring of access + operations metadata + semantic data, and least-privilege restriction of what MCP servers and tools can reach). We are building the defense for the problem the sponsor is actively raising.

**The pivot.** Swee was historically a Pulse/Observability-first product. For this hackathon we lead with **Shield (Security)** and treat Pulse/observability signals as secondary. Shield governs an AI agent's access to Splunk.

**The core idea (one sentence):** *A security layer that sits in front of the Splunk MCP Server and actively governs an AI agent's access to Splunk — pre-flight allow/deny policy on every Splunk tool call, a tamper-evident hash-verified audit trail of every action, and runtime defense of the agent's context by redacting secrets/PII out of Splunk results and neutralizing prompt-injection payloads hiding in returned log data before they reach the model.*

This is differentiated because most entrants will build "an agent that queries Splunk." We are building "the thing that makes it *safe* for an agent to query Splunk" — which moves us on Quality of Idea and Potential Impact, not just Technological Implementation.

---

## 3. Current repository facts (verified by repo recon — treat as ground truth)

These were confirmed by inspecting the repo. File:line references are from that recon; re-verify if the tree has shifted.

**Enforcement.** Pre-flight decision, then post-call audit. **No modify path** (policy can allow or deny, not rewrite). Decision point `packages/mcp-server/src/shield/enforcement.ts:30` (`evaluateShieldPolicy(...)`); denied tools do not execute (`enforcement.ts:35`). Policy form is JSON config + env override + TS evaluator: policy type `packages/mcp-server/src/shield/policy.ts:11`; decision type `packages/shared/src/types/index.ts:56`; config `config/shield.policy.json`; overrides `SWEE_SHIELD_POLICY_PATH`, `SWEE_SHIELD_MODE` (`policy.ts:50`).

**Audit store (SQLite).** Table at `packages/mcp-server/src/shield/audit-store.ts:89`. Fields: `audit_id, trace_id, request_id, tool_name, decision_json, status, started_at, finished_at, duration_ms, input_hash, output_hash, sanitized_input_json, error_json`. Inputs are sanitized before storage (raw input not stored, `audit-store.ts:36`); **outputs are not stored — only `output_hash`** (`audit-store.ts:127`). "Which policy fired" = `decision.reasonCodes` (`types/index.ts:61`). Returned record type `types/index.ts:77`.

**Replay.** **Inspection-only. No deterministic re-execution.** `getReplay` returns `auditId, toolName, sanitizedInput, decision, status, outputHash, durationMs` (`audit-store.ts:185`); REST entry `rest-gateway.ts:218`; tool entry `tools/shield-tools.ts:21`. No raw input/output, no upstream response body, no source snapshot, no time/random seed is persisted — so deterministic replay is **not possible** and must not be claimed.

**Scanner.** **Catalog-only.** Inspects tool *title/description* for prompt-override / secret-exfiltration / unbounded-remote-fetch wording (`scanner.ts:9`); finding schema `types/index.ts:93`; run only at explicit Shield tool (`tools/shield-tools.ts:37`) and explicit REST route (`rest-gateway.ts:225`). **It does NOT inspect inputs, outputs, payloads, PII, or runtime policy violations, and it is NOT in `invokeShieldedTool`.** Building runtime content scanning is therefore *new* code (Stage 4 below).

**Wrapping is generic.** Shield wraps any `RegisteredToolDefinition`, not only Pulse. Path: country-pack defs `country-packs/sg.ts:44` → hydrated tool set `tools/tool-set.ts:5` → registry `tools/registry.ts:24` → wrapper `tools/tool-definition.ts:70`. Minimum new tool = a `RegisteredToolDefinition` with `name, description, inputSchema, handler`, included in `sg.ts`, in an enabled toolset; then MCP + REST calls flow through `invokeShieldedTool`.

**Handler contract.** `handler: (input: unknown) => Promise<ToolResult>` (`tools/tool-definition.ts:26`). `ToolResult` = `content`, optional `isError, structuredContent, _meta` (`shared/src/types/index.ts:35`). **Success:** return `ToolResult` with `isError` absent/false. **To record `error_json` in the audit row you must THROW** — returning `{isError:true}` records `status:"error"` but no `error_json` (`enforcement.ts:60` vs `enforcement.ts:84`). *Implication: a denied or blocked Splunk call should throw through the proxy handler so the forensic trail captures the reason.*

**Runtime seam (decisive).** Call path: MCP wrapper `tools/tool-definition.ts:70` → `invokeShieldedTool` → tool handler `enforcement.ts:58` → audit `enforcement.ts:60` → return `enforcement.ts:72`. REST path enters the same seam (`rest-gateway.ts:127`). **The exact hook for runtime output scanning is immediately after `const result = await tool.handler(input);` and before `getShieldAuditStore().record(...)`** (`enforcement.ts:58–60`). Everything new converges on this one seam: output redaction, injection scan, finding production, and the post-redaction hash.

**MCP client status.** Runtime is **MCP-server-only today.** The official client SDK (`@modelcontextprotocol/sdk` `^1.29.0`, lock 1.29.0) is present but imported **only in tests** (`packages/mcp-server/src/__tests__/mcp-surface.test.ts:3`, importing `Client` from `@modelcontextprotocol/sdk/client/index.js` and `StreamableHTTPClientTransport` from `.../client/streamableHttp.js`). The npm tarball includes `client/streamableHttp` and `client/sse`; streamable transport supports `requestInit` headers. **Use the official SDK — no hand-rolled JSON-RPC needed.** SDK `callTool` today is REST-to-Swee (`packages/sdk/src/index.ts:239`), *not* MCP-to-MCP.

**Config & secrets.** Pattern is env-first then keystore fallback, matching LTA/URA clients (`apis/lta/client.ts:31`, `apis/ura/client.ts:17`). Keystore env fallback `SG_API_${API}_KEY/_EMAIL` (`shared/src/keystore.ts:36`); key tools `tools/keystore-tools.ts:7`; state dir `shared/src/state-dir.ts:6`. Config utils cover only cache/rate/timeouts/format/log (`shared/src/config/index.ts:10`). Existing OAuth/OIDC verifies *inbound* callers to this server (`index.ts:129`, `http-auth.ts:300`) — **not** upstream auth. OneMap token acquisition (`apis/onemap/auth.ts:15`) is the shape to mirror *if* full upstream OAuth is ever needed.

**Dashboard.** Existing Shield Audit panel in `apps/web/src/pages/DashboardPage.tsx`: fetches `/api/v1/shield/audits?limit=12` (`:94`), renders "Ops: Shield Audit" (`:253`), table rows show tool/decision/status/duration (`:361`). Extend this panel — no new page needed.

**Guardrails that must survive the pivot.** Never invent public-data values; never turn missing evidence into clearance/safety; surface provenance/freshness/gaps; keep recommendations operational/non-advisory. These extend naturally to the Splunk work: never fabricate Splunk results, never present a redacted/blocked result as "clean," always surface in the audit trail *that* redaction/blocking happened.

**Useful commands:** `npm run build`, `npm test`, `npm run verify`, `npm run dev`, `npm run diagnostics`, `npm run test:smoke:web`. REST defaults to `http://localhost:3000`; Vite web to `localhost:5173`.

---

## 4. Locked decisions (do not relitigate without explicit instruction)

1. **Track:** Security, Shield-led.
2. **Headline architecture:** Shield-as-proxy in front of the Splunk MCP Server (Option A), feasible because Shield's wrapping is generic and the enforcement+audit seam is reusable — a Splunk-backed proxy tool's handler calls the upstream Splunk MCP client, and the existing wrapper audits the result for free.
3. **Fallback (only if the proxy seam fails):** Option B — Shield wraps a few purpose-built Splunk-backed tools that call Splunk's REST/search API directly. Weaker novelty; keep in reserve, don't build unless A is blocked.
4. **Auth for local trial:** Bearer token via `requestInit` headers is sufficient for a local Splunk Enterprise trial. Full OAuth 2.1 authorization-code flow is out of scope unless time permits and it materially helps the demo.
5. **Audit/replay framing:** "**Tamper-evident, hash-verified audit trail**" (forensic integrity). **Never** claim deterministic replay.
6. **Runtime scanner:** **In scope** — it is the novelty that separates placing from winning, and it's the cheap part of the build (the one new hook, at the single seam in §3).
7. **Hash order:** hash the **post-redaction** payload as `output_hash` (preserves current audit semantics). Add a **separate** `raw_output_hash` over the pre-redaction upstream bytes so we can prove *both* that redaction occurred and that neither payload was tampered with. Do not overload the existing `output_hash`.
8. **Models:** **Foundation-sec** primary (triage/classification of what the agent surfaces). **Cisco Deep Time Series** optional secondary (anomaly flag). Existing Anthropic/OpenAI routing remains available.
9. **Scanner framing:** active **agent-context defense at the proxy boundary**, *layered on top of* Splunk's own sanitization — never framed as "Splunk can't do this."

---

## 5. Staged build plan

Build strictly in dependency order. Stages 1–3 deliver the governed proxy (enforcement + hash-verified audit come for free through the existing wrapper). Stage 4 is the novelty. Stages 5–7 persist, surface, and prove it. Stage 8 is the optional multi-agent layer. Stage 9 is submission prep.

After each stage: `npm run build && npm test && npm run verify` must pass before moving on.

### Stage 1 — Upstream Splunk MCP client
**New:** `packages/mcp-server/src/upstreams/splunk/mcp-client.ts`.
- Use the official `@modelcontextprotocol/sdk` `Client` + `StreamableHTTPClientTransport` (already a dependency; see test import for the exact module paths).
- Implement only what we need: `initialize`, `tools/list`, `tools/call`. Pass the Bearer token through `requestInit` headers.
- Connection config from Stage 2. Sensible timeouts (reuse `shared/src/config` timeout util). Surface upstream transport errors as thrown errors (so they reach Shield's `error_json` path).
- Expose a small typed surface: `listSplunkTools()`, `callSplunkTool(name, args)`.
- **Tests:** unit test the client against a mocked transport (mirror the style in `__tests__/mcp-surface.test.ts`). Do not require a live Splunk for unit tests.

### Stage 2 — Config & secrets plumbing
- `SPLUNK_MCP_URL` from env.
- `SPLUNK_MCP_TOKEN` from env, falling back to `keystore.getKey("splunk_mcp")` — mirror the LTA/URA env-first-then-keystore pattern (`apis/lta/client.ts:31`). `sg_key_set {apiName:"splunk_mcp"}` already works through the keystore (`tools/keystore-tools.ts:7`).
- `NODE_TLS_REJECT_UNAUTHORIZED=0` for self-signed local-trial certs — **env-direct only, keep it out of any config JSON**, and document it as local-trial-only in the README.
- Document all three in `.env.example` / README.

### Stage 3 — Splunk proxy tools (the governed surface)
**New:** `packages/mcp-server/src/tools/splunk-tools.ts`. Register in `country-packs/sg.ts` (import + spread), in an enabled toolset.
- Expose an **allowlist** of Splunk tools as `RegisteredToolDefinition`s (start with: run SPL search, list indexes, discover knowledge objects/saved searches). Allowlisting *is* part of the security story (least privilege — exactly what Splunk's security guidance asks for).
- Each handler: `async (input) => ToolResult`. It (a) checks the allowlist, (b) calls `callSplunkTool(...)` from Stage 1, (c) returns a `ToolResult`. **On deny/block/disallowed-tool, THROW** so `error_json` is captured (see §3 handler contract).
- These tools flow through the existing wrapper → `invokeShieldedTool` → pre-flight policy + post-call audit, with **no new enforcement code**. Add Splunk-relevant policy entries to `config/shield.policy.json` (e.g. deny destructive SPL, cap result size, deny disallowed indexes).
- **Milestone check:** at the end of Stage 3 you have a working Shield-governed proxy to Splunk with hash-verified audit. This is the minimum viable winning core. If time runs out, you still have a complete, honest submission.

### Stage 4 — Runtime content scanner (the novelty) ⭐
**New:** `packages/mcp-server/src/shield/runtime-scanner.ts`. Hook at `enforcement.ts:58–60`, immediately after `const result = await tool.handler(input)` and before `record(...)`.
- **Redaction:** detect and mask secrets/PII in tool output (API keys, tokens, credentials, SSN/NRIC-style IDs, emails, credit-card-shaped numbers). Produce a redacted copy of the output that is what gets returned to the caller.
- **Injection defense:** scan returned *data* (Splunk log/event content) for prompt-injection patterns (e.g. "ignore previous instructions", tool-override wording, exfiltration directives embedded in log fields). On detection, neutralize (e.g. defang/escape) and **produce a finding**; configurable to either neutralize-and-flag or block-and-throw for high-severity patterns.
- Emit `findings: RuntimeFinding[]` (define the type in `shared/src/types`; align with existing finding schema at `types/index.ts:93` where sensible).
- **Scope guard:** this scanner runs on tool *output* at the seam. Keep it deterministic and fast; no network calls in the scanner itself.
- **Tests:** feed fixtures with a planted credential (asserts redaction) and a planted injection string (asserts neutralization + finding).

### Stage 5 — Persist findings + dual hash
- Migrate the audit table (constructor migration via `PRAGMA table_info` + `ALTER TABLE`, per recon): add nullable `runtime_findings_json TEXT` and nullable `raw_output_hash TEXT`. `rowToRecord` must treat null/missing as absent / `[]` so existing reads keep working.
- Wire Stage 4 output: store findings JSON; set `output_hash` over the **post-redaction** payload (unchanged semantics) and `raw_output_hash` over the **pre-redaction** upstream bytes.
- Extend the returned record type and `getReplay` to include findings (inspection-only — still no re-execution).

### Stage 6 — Dashboard surface
- Extend the existing Shield Audit panel in `DashboardPage.tsx` (`:253`/`:361`): add findings to `ShieldAuditRow`, show finding count + reason codes per row, and surface `auditId`/timestamp. One component + a test/CSS touch. Enough to make the audit trail and the redaction/injection events *visible in the demo video*.

### Stage 7 — Demo fixtures & end-to-end on the local trial
- Stand up the local Splunk Enterprise trial + Splunk MCP Server app; create a Bearer token; point `SPLUNK_MCP_URL`/`SPLUNK_MCP_TOKEN` at it.
- Seed demo data: (a) an event/index containing a **planted fake credential** that the scanner redacts; (b) a log line carrying a **prompt-injection string** that the scanner neutralizes + flags; (c) ordinary security-relevant events for a believable investigation (e.g. failed logins, suspicious process names) so the agent has something real to find.
- Script the end-to-end: agent asks a natural-language security question → Shield-governed `splunk_search` runs → policy allows → result comes back → scanner redacts the credential and flags the injection → model receives the *defended* result → audit row shows decision, both hashes, and findings → dashboard shows it.

### Stage 8 — Multi-agent layer (OPTIONAL stretch — see §6)
Only after Stages 1–7 are solid and green. Details in §6.

### Stage 9 — Submission prep
See §7.

---

## 6. Multi-agent direction (PROPOSED, optional — not yet locked)

> This was discussed only at the level of "Foundation-sec for triage, Deep Time Series for anomaly." It is **not** a locked design. Treat this section as a proposal to confirm before building, and as a *stretch* that must not jeopardise Stages 1–7.

A natural multi-agent shape that strengthens the Security narrative without diluting the governance core:

- **Investigator agent** — drives the natural-language → SPL investigation loop through the Shield-governed Splunk proxy. Reasoning model: Foundation-sec (security-tuned) where available, else existing Anthropic/OpenAI routing.
- **Triage/classifier agent** — Foundation-sec classifies findings/events surfaced by the investigator (severity, category, likely benign vs. worth escalating). Operates only on *already-defended* (post-scanner) data.
- **Anomaly agent (optional flourish)** — Cisco Deep Time Series flags anomalous spikes in a metric/event series; its output becomes another governed signal the investigator can act on. This is where Pulse's existing time-series strength can quietly resurface as a secondary capability.

**Hard constraint:** every agent's access to Splunk goes through the Shield proxy. No agent gets a direct, ungoverned path. The multi-agent story is *"multiple specialized agents, one governed boundary"* — which reinforces, rather than competes with, the core idea. Orchestration should be thin (a coordinator that routes between agents); do not build a heavyweight framework under time pressure.

**Decision needed from the user before Stage 8:** confirm this shape, or supply the intended multi-agent design. Do not build Stage 8 on assumption.

---

## 7. Submission preparation checklist

- [ ] **Significant-update narrative.** Write a short, honest account of what was built/changed *after May 18, 2026* (the upstream client, the Splunk proxy tools, the runtime scanner, dual-hash audit, dashboard surface, multi-agent layer if built). The rules require this and judges check it.
- [ ] **Open-source license** present and **detectable in the repo "About" section** (top of repo page).
- [ ] **README:** what it is, the security problem it solves, setup + run instructions, dependencies, env vars (`SPLUNK_MCP_URL`, `SPLUNK_MCP_TOKEN`, the local-trial TLS note), how to reproduce the demo (including seeding the fixtures).
- [ ] **`architecture_diagram.(md|pdf|png)` at repo root** showing: agent(s) → Shield proxy (pre-flight policy → handler → upstream Splunk MCP client → runtime scanner → audit) → Splunk MCP Server → Splunk; where Foundation-sec / Deep Time Series plug in; data flow + where redaction/hashing/findings happen.
- [ ] **Identify the track** on the submission form: **Security**. Consider noting the **"Best Use of Splunk MCP Server"** bonus eligibility.
- [ ] **Demo video < 3 min**, public on YouTube/Vimeo/Youku, link on the submission form. Must show the project functioning, state the problem, show where AI is used, highlight the value. Suggested beat sheet: (1) the threat — an agent querying Splunk can leak secrets and be hijacked by injection in log data; (2) the agent runs a real investigation through the Shield proxy; (3) on screen: a credential gets redacted, an injection gets neutralized + flagged, the audit row shows decision + dual hashes + findings; (4) the value line — *least-privilege, tamper-evident, context-defended agent access to Splunk.* No third-party trademarks or copyrighted music without permission.
- [ ] **Public repo** with all source, assets, instructions; project installable and runnable; available free for judge testing until judging ends.
- [ ] **All materials in English.**
- [ ] **Feedback Submission (optional bonus):** one actionable feedback form on the Splunk SDKs/docs during the feedback period can qualify for a Most Valuable Feedback prize ($200). Low effort; consider it.
- [ ] **Claims audit (do this last).** Re-read every claim in README/video/diagram against §3 and §4. Specifically confirm: no "deterministic replay" claim anywhere; the scanner is described as *layered on top of* Splunk's own sanitization, not a replacement; nothing fabricates Splunk data; redaction/blocking is always visible in the audit trail.

---

## 8. Risk register

- **Proxy seam (Option A) proves heavier than estimated.** Mitigation: Stage 3 milestone is the MVP; Option B fallback (§4.3) is pre-decided. Don't discover this late — validate the upstream client (Stage 1) against the live local trial early.
- **Live Splunk flakiness in the demo.** Mitigation: unit tests use mocked transport; record the demo against a known-good seeded state; keep fixtures deterministic.
- **Scanner over-redaction / false positives** making the demo confusing. Mitigation: tune patterns against the seeded fixtures; show one clean redaction and one clean injection-neutralization rather than a noisy firehose.
- **Scope creep into Stage 8** at the expense of a polished core. Mitigation: Stages 1–7 are the submission; Stage 8 is explicitly optional and gated on user confirmation.
- **Hash-integrity claim accidentally broken** by hashing the wrong payload. Mitigation: §4.7 is explicit — post-redaction → `output_hash`, pre-redaction → `raw_output_hash`; covered by a Stage 5 test.

---

## 9. Immediate next actions for the coding agent

1. Re-verify the §3 file:line anchors against the current tree (note any drift).
2. Implement **Stage 1** (upstream Splunk MCP client) and its mocked-transport unit test.
3. Implement **Stage 2** (config/secrets) and update `.env.example` + README.
4. Implement **Stage 3** (Splunk proxy tools + policy entries) and confirm an end-to-end governed call with hash-verified audit. **Stop here and report** — this is the MVP checkpoint and the right moment to confirm Option A is healthy before building the novelty.
5. Await confirmation, then proceed to **Stage 4+**.

Report blockers early, especially anything that would push us from Option A to the Option B fallback.
