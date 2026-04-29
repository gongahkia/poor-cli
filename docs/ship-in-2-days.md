# Ship In 2 Days

The fastest concrete path from `git clone` to a UI-ready Singapore-data artifact, using one of the repo's strongest workflows (property brief). Total active time: ~2 hours; calendar window: 2 days because step 4 needs OneMap and URA credentials with manual approval.

The point of this doc is not feature inventory. It is to prove the repo is shippable end-to-end before you commit to deeper integration.

## Day 1 (~45 min)

### 1. Boot the server (no credentials)

```bash
git clone https://github.com/<org>/sg-skills && cd sg-skills
npm install
npm run try
```

`npm run try` builds and runs the no-credential public smoke. If it fails, run `npm run diagnostics` and fix that first — do not skip ahead.

### 2. Cache the discovery resources

Read these once and persist them in your app/agent state — they describe the contract you are about to depend on:

- `sg://recipes` — natural-language goal → preferred tool routing
- `sg://runtime` — auth, cache, health coverage, blocked-state semantics
- `sg://benchmarks` — per-workflow latency, cache tier, freshness expectations

```ts
// pseudo-code
const recipes = await client.readResource("sg://recipes");
const runtime = await client.readResource("sg://runtime");
const benchmarks = await client.readResource("sg://benchmarks");
persist({ recipes, runtime, benchmarks });
```

The runnable form lives at [`examples/integration/basic-client.ts`](../examples/integration/basic-client.ts) (Node) and [`examples/integration/basic-client.py`](../examples/integration/basic-client.py) (Python).

### 3. Run a brief end-to-end (no credentials required for civic)

```bash
node packages/mcp-server/dist/index.js
# in your client, call:
# sg_civic_brief { postalCode: "560123", radiusKm: 1.5 }
```

You should see the bounded brief envelope: `summary`, `evidence`, `records`, `gaps`, `provenance`, `freshness`, `limits`. Confirm `gaps` and `freshness` are present even when one source 0-fills — that is the partial-failure contract.

## Day 2 (~75 min, after credentials arrive)

### 4. Wire credentials and run the live smoke

```bash
export SG_API_ONEMAP_EMAIL=...
export SG_API_ONEMAP_PASSWORD=...
export SG_API_URA_KEY=...
export SG_API_LTA_KEY=...
npm run quick-start
```

If any upstream fails, `sg_health_check` is the first stop, then [`docs/troubleshooting.md`](./troubleshooting.md). Do not attempt to bypass auth — the runtime intentionally fails fast.

### 5. Generate the UI-ready property brief

This is the stickiest cross-source artifact in the repo. Pick a real address and run:

```jsonc
// sg_property_brief
{
  "postalCode": "560123",
  "includeTransport": true,
  "includeEnvironment": true,
  "format": "markdown"
}
```

You get back a brief that already includes `summary`, `riskFlags`, `nextChecks`, transaction rollups, and source-linked freshness. The `markdown` form is intended to be pasted directly into a UI panel, ticket, or agent message — not post-processed.

### 6. Render the artifact in your app

Three ship-it patterns:

- **Agent reply**: drop the markdown straight into the assistant message.
- **Internal tool**: render `summary[]` as a card, `riskFlags[]` as colored chips, `nextChecks[]` as actionable buttons backed by direct `sg_*` tool calls.
- **Background job**: see [`examples/integration/scheduled-monitor-template.ts`](../examples/integration/scheduled-monitor-template.ts) for delta-aware monitoring with blocked-state recovery.

If the brief returns `verdict: insufficient_data` or non-empty `gaps[]`, follow the brief's own `nextChecks` rather than synthesizing around it.

## Acceptance Checklist

Before declaring "shipped":

- [ ] `npm run try` succeeds on a fresh checkout.
- [ ] You have read and persisted `sg://recipes`, `sg://runtime`, and `sg://benchmarks` in app state.
- [ ] One brief is rendered end-to-end with `gaps`, `freshness`, and `provenance` visible to the user.
- [ ] Blocked / unsupported / failed responses each have a UI/log path that does not crash your app.
- [ ] Credentials are loaded from env or the keystore, not hard-coded.
- [ ] `npm run test:smoke:live` passes with your credentials.

## Where To Go Next

- [Operating expectations](./operating-expectations.md) for cache TTL, SLO posture, partial-failure semantics.
- [Compatibility matrix](./compatibility-matrix.md) for client/transport support tiers.
- [Agent builder quickstart](./agent-builder-quickstart.md) for `sg_query` vs direct-tool routing.
- [Examples](../examples/integration/) for runnable patterns (basic client, backend worker, queue consumer, scheduled monitor, UI state).
