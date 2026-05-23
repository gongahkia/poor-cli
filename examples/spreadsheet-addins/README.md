# Spreadsheet Add-In Prototypes

This directory contains prototype integrations for Google Sheets and Excel. They prove the function/API shape for spreadsheet-based Swee Pulse monitoring, not final Marketplace or AppSource packages.

## Success Definition

- Spreadsheet function names and return shapes are defined.
- A Google Sheets Apps Script prototype can call the Swee SG REST gateway.
- An Excel custom-functions prototype and packaging scope are documented.
- Auth, rate limits, export behavior, and production blockers are explicit.

## Function Shape

| Function | Inputs | Return |
| --- | --- | --- |
| `SWEE_PULSE_SNAPSHOT(focus, area, gatewayUrl, token)` | Optional focus (`all`, `mobility`, `weather`), optional area, REST gateway URL, optional browser-safe token. | JSON string containing signals, source health, gaps, freshness, and provenance. |
| `SWEE_PULSE_SIGNALS(focus, area, gatewayUrl, token)` | Same as above. | Six-column table: severity, category, title, summary, source, observed at. |
| `SWEE_PULSE_SOURCES(focus, area, gatewayUrl, token)` | Same as above. | Five-column table: source, status, rows, observed at, message. |

The prototypes call:

```http
GET /api/v1/pulse/snapshot?focus=weather&area=Bedok
```

## Google Sheets Prototype

File: [`google-sheets/Code.gs`](./google-sheets/Code.gs)

Setup:

1. Create a Google Sheet.
2. Open Extensions -> Apps Script.
3. Paste `Code.gs`.
4. Use a formula:

```text
=SWEE_PULSE_SIGNALS("weather", "Bedok", "https://swee.example", "short-lived-token")
```

For internal gateways with no browser token, omit the fourth argument.

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
- let the proxy inject Swee SG credentials server-side;
- if direct browser/script auth is unavoidable, use a short-lived token scoped to Pulse read endpoints, workspace, allowed origin, and low rate limits.

Avoid putting long-lived Swee SG tokens, upstream API keys, AI provider keys, or admin tokens in cells. Spreadsheet files are copied and exported often, so treat cell-visible secrets as compromised.

## Rate Limits

Spreadsheet recalculation can trigger many repeated calls. Production add-ins should implement:

- per-workspace rate limits on the Swee SG gateway;
- spreadsheet-side cache with a short TTL;
- batch APIs before enabling large sheets;
- backoff for 429/5xx responses;
- user-visible stale/freshness metadata instead of silent retries.

Prototype guidance:

- keep test sheets below 50 rows;
- prefer `SWEE_PULSE_SIGNALS` for operator views;
- use exported Pulse snapshots for larger monitoring workbooks.

## Export Behavior

Spreadsheet exports must preserve:

- source names;
- observed timestamps;
- upstream timestamps where returned;
- gaps and limits;
- non-advice language.

Do not export a single pass/fail cell without the supporting source health and freshness columns.

## Smoke Check

```bash
npm run spreadsheet-addins:check
```

The smoke check verifies that both prototype surfaces expose the expected functions, endpoint, auth header behavior, and documentation sections.
