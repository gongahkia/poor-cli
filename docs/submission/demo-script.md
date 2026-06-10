# Demo Script

Target runtime: under 3 minutes.

## 0:00-0:25 Problem

Show the threat: an agent querying Splunk can receive log data that includes fake secrets or embedded prompt-injection text. State that the project is a governed boundary in front of Splunk MCP, not another direct Splunk-querying agent.

## 0:25-0:55 Architecture

Show `architecture_diagram.md`.

Key line: agent -> Swee Shield policy -> Splunk proxy -> runtime scanner -> audit -> dashboard.

Say: Splunk RBAC still applies upstream; Shield adds least-privilege proxying, local audit, output defense, and hash evidence at the agent boundary.

## 0:55-1:35 Token-Independent Fixture Proof

Run:

```bash
npx vitest run packages/mcp-server/src/shield/__tests__/runtime-demo-fixtures.test.ts
```

Show the synthetic fixture file:

```text
packages/mcp-server/src/upstreams/splunk/__tests__/fixtures/demo-events.json
```

Say explicitly: these are fake demo events, not live Splunk output.

Point out:

- fake credential/token is redacted
- fake email/ID/card-shaped values are redacted
- prompt-injection text is neutralized
- audit stores runtime findings and raw/post hashes

## 1:35-2:20 Live Path Or Mocked Gateway

If live Splunk token exists:

```bash
curl -X POST http://localhost:3000/api/v1/splunk_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"index=security failed login","limit":10}'
```

If token does not exist, show the mocked test as the honest fallback and explain live E2E is gated on `SPLUNK_MCP_URL` and `SPLUNK_MCP_TOKEN`.

## 2:20-2:50 Dashboard + Value

Show the dashboard Shield audit panel:

- tool decision
- reason codes
- finding count
- severity/action
- audit ID
- raw/post hash short IDs

Value line: least-privilege, tamper-evident, context-defended agent access to Splunk.

## Forbidden Lines

- Do not say deterministic replay.
- Do not say Splunk cannot sanitize this.
- Do not imply synthetic fixture data came from Splunk.
- Do not claim live auth or live Splunk behavior without actually showing it.

