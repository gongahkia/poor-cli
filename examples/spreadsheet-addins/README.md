# Spreadsheet Add-In Prototypes

This directory contains prototype integrations for Google Sheets and Excel. They are designed to prove the function/API shape for spreadsheet-based CDD workflows, not to serve as final Marketplace or AppSource packages.

## Success Definition

- Spreadsheet function names and return shapes are defined.
- A Google Sheets Apps Script prototype can call the Dude REST gateway.
- An Excel custom-functions prototype and packaging scope are documented.
- Auth, rate limits, export behavior, and production blockers are explicit.

## Function Shape

| Function | Inputs | Return |
| --- | --- | --- |
| `DUDE_DOSSIER(identifier, gatewayUrl, token)` | Company name or UEN, REST gateway URL, optional browser-safe token. | JSON string containing title, summary, gaps, freshness, provenance, and limits. |
| `DUDE_DOSSIER_SUMMARY(identifier, gatewayUrl, token)` | Same as above. | Two-column table: label, value. |
| `DUDE_DOSSIER_FRESHNESS(identifier, gatewayUrl, token)` | Same as above. | Four-column table: source, observedAt, upstreamTimestamp, records. |

The prototypes call:

```http
POST /api/v1/dude/cdd-orchestrator
Content-Type: application/json

{ "uen": "201900001A" }
```

If the identifier does not look like a UEN, the payload uses `entityName`.

## Google Sheets Prototype

File: [`google-sheets/Code.gs`](./google-sheets/Code.gs)

Setup:

1. Create a Google Sheet.
2. Open Extensions -> Apps Script.
3. Paste `Code.gs`.
4. Use a formula:

```text
=DUDE_DOSSIER_SUMMARY("201900001A", "https://dude.example", "short-lived-token")
```

For internal gateways with no browser token, omit the third argument.

## Excel Prototype

File: [`excel/functions.js`](./excel/functions.js)

This is the custom-functions source for an Office.js add-in. A production Excel add-in still needs:

- Office manifest with allowed domains and function metadata;
- task pane for gateway URL/token settings;
- secure token storage strategy;
- AppSource validation pass if distributed publicly;
- enterprise deployment documentation for Microsoft 365 admins.

## Auth

Best production pattern:

- keep the spreadsheet talking to a customer-controlled proxy;
- let the proxy inject Dude credentials server-side;
- if direct browser/script auth is unavoidable, use a short-lived token scoped to the CDD orchestrator, workspace, allowed origin, and low rate limits.

Avoid putting long-lived Dude tokens, upstream API keys, AI provider keys, or admin tokens in cells. Spreadsheet files are copied and exported often, so treat cell-visible secrets as compromised.

## Rate Limits

Spreadsheet recalculation can trigger many repeated calls. Production add-ins should implement:

- per-workspace rate limits on the Dude gateway;
- spreadsheet-side cache with a short TTL;
- batch APIs for columns of UENs before enabling large sheets;
- backoff for 429/5xx responses;
- user-visible stale/freshness metadata instead of silent retries.

Prototype guidance:

- keep test sheets below 50 rows;
- prefer `DUDE_DOSSIER_SUMMARY` for analyst views;
- use bulk CSV or future batch endpoints for 200-row diligence workspaces.

## Export Behavior

Spreadsheet exports must preserve:

- source names;
- observed timestamps;
- upstream timestamps where returned;
- gaps and limits;
- non-advice language.

Do not export a single pass/fail cell without the supporting provenance and freshness columns.

## Smoke Check

```bash
npm run spreadsheet-addins:check
```

The smoke check verifies that both prototype surfaces expose the expected functions, endpoint, auth header behavior, and documentation sections.
